from typing import Callable, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import decode_access_token
from app.models.roles import UserRole, validate_role
from app.services.user import UserRepositoryUnavailableError, get_user_by_id

bearer_security = HTTPBearer(auto_error=False)

class AuthenticatedUser(BaseModel):
    user_id: str
    email: str
    role: str = UserRole.CITIZEN.value
    is_active: bool = True


async def get_current_user(
    request: Request,
    credentials: Union[HTTPAuthorizationCredentials, None] = Depends(bearer_security),
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts and validates the Bearer JWT token,
    retrieves the active user identity from MongoDB, and prevents unauthenticated access.
    The user's canonical role is derived and validated from the database.
    """
    token = credentials.credentials if credentials is not None else request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token has expired.",
        )

    try:
        user = await get_user_by_id(user_id)
    except UserRepositoryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account service is temporarily unavailable.",
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user was not found.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
        )

    raw_role = user.get("role") or UserRole.CITIZEN.value
    validated_role = validate_role(raw_role).value

    return AuthenticatedUser(
        user_id=user["user_id"],
        email=user["email"],
        role=validated_role,
        is_active=user["is_active"],
    )


# Alias for explicitly requiring an authenticated user
require_authenticated_user = get_current_user


def require_roles(*allowed_roles: Union[str, UserRole]) -> Callable:
    """
    Dependency factory that restricts endpoint access to users holding one of the specified roles.
    Raises 401 if unauthenticated, 403 if authenticated user lacks required role.
    """
    normalized_allowed = {
        validate_role(r).value for r in allowed_roles
    }

    async def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.role not in normalized_allowed:
            try:
                from app.services.audit import AuditService
                await AuditService.record_event(
                    action="access_denied",
                    result="denied",
                    actor_user_id=current_user.user_id,
                    actor_role=current_user.role,
                    resource_type="endpoint",
                    metadata={
                        "required_roles": sorted(list(normalized_allowed)),
                    },
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Insufficient permissions. Required role: {', '.join(sorted(list(normalized_allowed)))}.",
            )
        return current_user

    return role_checker


def require_role(role: Union[str, UserRole]) -> Callable:
    """
    Dependency factory that restricts endpoint access to users holding a specific role.
    Raises 401 if unauthenticated, 403 if authenticated user lacks the required role.
    """
    return require_roles(role)
