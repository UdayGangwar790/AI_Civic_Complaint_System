from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.roles import UserRole, VALID_ROLES

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 non-empty characters.")
        return v

    @field_validator("role")
    @classmethod
    def validate_optional_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in VALID_ROLES:
                raise ValueError("Invalid role.")
            return clean
        return v


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str = UserRole.CITIZEN.value
    created_at: datetime
    is_active: bool = True


class AuthResponse(BaseModel):
    user: UserResponse
