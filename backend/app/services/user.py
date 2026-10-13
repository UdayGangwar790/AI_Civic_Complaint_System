from datetime import datetime, timezone
import logging
from typing import Optional, Union
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError, DuplicateKeyError

from app.core.database import USERS_COLLECTION, get_database
from app.core.security import hash_password, verify_password
from app.models.roles import UserRole, validate_role
from app.schemas.auth import UserLoginRequest, UserRegisterRequest

logger = logging.getLogger("cvki.user")


class UserAlreadyExistsError(ValueError):
    """A user with this email already exists."""


class InvalidCredentialsError(ValueError):
    """The provided email or password was incorrect."""


class UserNotFoundError(LookupError):
    """The requested user was not found."""


class UserInactiveError(ValueError):
    """The user account is inactive."""


class UserRepositoryUnavailableError(RuntimeError):
    """User persistence is unavailable or failed."""


_DEFAULT_DB = object()


class MongoUserRepository:
    """
    MongoDB persistence repository for user accounts.
    """

    def __init__(self, db: object = _DEFAULT_DB):
        self._db = db

    def _get_collection(self):
        db = get_database() if self._db is _DEFAULT_DB else self._db
        if db is None:
            raise UserRepositoryUnavailableError("User persistence is unavailable.")
        return db[USERS_COLLECTION]

    async def create_user(
        self,
        email: str,
        password_hash: str,
        role: Union[str, UserRole] = UserRole.CITIZEN,
    ) -> dict:
        validated_role = validate_role(role)
        collection = self._get_collection()
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        doc = {
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "role": validated_role.value,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
        }

        try:
            await collection.insert_one(doc)
        except DuplicateKeyError as exc:
            logger.warning("Duplicate user registration attempted.")
            raise UserAlreadyExistsError("An account with this email already exists.") from exc
        except PyMongoError as exc:
            logger.error("User creation failed (error_type=%s).", type(exc).__name__)
            raise UserRepositoryUnavailableError("User persistence is unavailable.") from exc

        return doc

    async def get_by_email(self, email: str) -> Optional[dict]:
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"email": email.strip().lower()})
        except PyMongoError as exc:
            logger.error("User lookup failed (error_type=%s).", type(exc).__name__)
            raise UserRepositoryUnavailableError("User persistence is unavailable.") from exc
        if doc and "role" not in doc:
            doc["role"] = UserRole.CITIZEN.value
        return doc

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"user_id": user_id})
        except PyMongoError as exc:
            logger.error("User lookup failed (error_type=%s).", type(exc).__name__)
            raise UserRepositoryUnavailableError("User persistence is unavailable.") from exc
        if doc and "role" not in doc:
            doc["role"] = UserRole.CITIZEN.value
        return doc

    async def update_role(self, user_id: str, role: Union[str, UserRole]) -> Optional[dict]:
        validated_role = validate_role(role)
        collection = self._get_collection()
        now = datetime.now(timezone.utc)
        try:
            result = await collection.find_one_and_update(
                {"user_id": user_id},
                {"$set": {"role": validated_role.value, "updated_at": now}},
                return_document=True,
            )
        except PyMongoError as exc:
            logger.error("User role update failed (error_type=%s).", type(exc).__name__)
            raise UserRepositoryUnavailableError("User persistence is unavailable.") from exc
        return result


user_repository = MongoUserRepository()


def set_user_repository(repo: MongoUserRepository) -> None:
    global user_repository
    user_repository = repo


async def register_user(request: UserRegisterRequest) -> dict:
    """
    Registers a new citizen with normalized email and bcrypt hashed password.
    Citizen self-registration ALWAYS creates a citizen role account.
    Never accepts arbitrary or elevated roles from registration requests.
    """
    normalized_email = request.email.strip().lower()
    existing = await user_repository.get_by_email(normalized_email)
    if existing is not None:
        raise UserAlreadyExistsError("An account with this email already exists.")

    hashed = hash_password(request.password)
    user_doc = await user_repository.create_user(
        normalized_email,
        hashed,
        role=UserRole.CITIZEN,
    )

    # Return copy without password_hash
    safe_user = dict(user_doc)
    safe_user.pop("password_hash", None)
    safe_user.pop("_id", None)
    safe_user["role"] = safe_user.get("role") or UserRole.CITIZEN.value
    return safe_user


async def authenticate_user(request: UserLoginRequest) -> dict:
    """
    Authenticates a user via normalized email and password verification.
    Returns safe user dict with canonical role if valid; raises InvalidCredentialsError on failure.
    """
    normalized_email = request.email.strip().lower()
    user = await user_repository.get_by_email(normalized_email)
    if user is None:
        raise InvalidCredentialsError("Invalid email or password.")

    if not verify_password(request.password, user.get("password_hash", "")):
        raise InvalidCredentialsError("Invalid email or password.")

    if not user.get("is_active", True):
        raise UserInactiveError("User account is inactive.")

    safe_user = dict(user)
    safe_user.pop("password_hash", None)
    safe_user.pop("_id", None)
    safe_user["role"] = safe_user.get("role") or UserRole.CITIZEN.value
    return safe_user


async def get_user_by_id(user_id: str) -> Optional[dict]:
    """
    Retrieves safe user document by user_id.
    Lazy-defaults missing role to citizen.
    """
    user = await user_repository.get_by_id(user_id)
    if user is None:
        return None
    safe_user = dict(user)
    safe_user.pop("password_hash", None)
    safe_user.pop("_id", None)
    safe_user["role"] = safe_user.get("role") or UserRole.CITIZEN.value
    return safe_user


async def create_privileged_user(
    email: str,
    password: str,
    role: Union[str, UserRole],
) -> dict:
    """
    Controlled internal/seed mechanism to provision administrative and authority accounts.
    Never exposed as an unauthenticated or public endpoint.
    """
    validated_role = validate_role(role)
    normalized_email = email.strip().lower()

    existing = await user_repository.get_by_email(normalized_email)
    if existing is not None:
        raise UserAlreadyExistsError(f"An account with email '{normalized_email}' already exists.")

    hashed = hash_password(password)
    user_doc = await user_repository.create_user(
        normalized_email,
        hashed,
        role=validated_role,
    )

    safe_user = dict(user_doc)
    safe_user.pop("password_hash", None)
    safe_user.pop("_id", None)
    safe_user["role"] = validated_role.value
    return safe_user
