from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.csrf import create_csrf_token
from app.core.security import create_access_token
from app.core.rate_limit import rate_limit_dependency
from app.schemas.auth import (
    AuthResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.user import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserRepositoryUnavailableError,
    authenticate_user,
    register_user,
)

router = APIRouter()


def _set_auth_cookies(response: Response, token: str) -> None:
    cookie_options = {
        "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "path": "/",
        "secure": settings.auth_cookie_secure,
        "samesite": settings.COOKIE_SAMESITE,
    }
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        **cookie_options,
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=create_csrf_token(token),
        httponly=False,
        **cookie_options,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new citizen account",
    dependencies=[
        Depends(rate_limit_dependency(
            scope="registration",
            limit=settings.REGISTRATION_RATE_LIMIT_REQUESTS,
            window_seconds=settings.REGISTRATION_RATE_LIMIT_WINDOW_SECONDS,
        ))
    ],
)
async def register(request: UserRegisterRequest, response: Response) -> AuthResponse:
    try:
        user = await register_user(request)
        role = user.get("role", "citizen")
        token = create_access_token(user_id=user["user_id"], email=user["email"], role=role)
        _set_auth_cookies(response, token)
        return AuthResponse(
            user=UserResponse(
                user_id=user["user_id"],
                email=user["email"],
                role=role,
                created_at=user["created_at"],
                is_active=user["is_active"],
            ),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    except UserRepositoryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account service is temporarily unavailable.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate a user and establish a session cookie",
    dependencies=[
        Depends(rate_limit_dependency(
            scope="login",
            limit=settings.LOGIN_RATE_LIMIT_REQUESTS,
            window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        ))
    ],
)
async def login(request: UserLoginRequest, response: Response) -> AuthResponse:
    try:
        user = await authenticate_user(request)
        role = user.get("role", "citizen")
        token = create_access_token(user_id=user["user_id"], email=user["email"], role=role)
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                action="auth_login",
                result="success",
                actor_user_id=user["user_id"],
                actor_role=role,
                resource_type="auth",
                metadata={"email": user["email"]},
            )
        except Exception:
            pass
        _set_auth_cookies(response, token)
        return AuthResponse(
            user=UserResponse(
                user_id=user["user_id"],
                email=user["email"],
                role=role,
                created_at=user["created_at"],
                is_active=user["is_active"],
            ),
        )
    except InvalidCredentialsError:
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                action="auth_login",
                result="failure",
                actor_user_id=None,
                actor_role=None,
                resource_type="auth",
                metadata={"attempted_email": request.email},
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    except UserInactiveError:
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                action="auth_login",
                result="failure",
                actor_user_id=None,
                actor_role=None,
                resource_type="auth",
                metadata={"attempted_email": request.email, "reason": "inactive_account"},
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    except UserRepositoryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account service is temporarily unavailable.",
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Clear the current session")
async def logout(response: Response) -> Response:
    response.status_code = status.HTTP_204_NO_CONTENT
    cookie_options = {
        "path": "/",
        "secure": settings.auth_cookie_secure,
        "samesite": settings.COOKIE_SAMESITE,
    }
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        httponly=True,
        **cookie_options,
    )
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        httponly=False,
        **cookie_options,
    )
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
        created_at=datetime.now(timezone.utc),
        is_active=current_user.is_active,
    )
