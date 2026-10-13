from enum import Enum
from typing import Any


class UserRole(str, Enum):
    CITIZEN = "citizen"
    ADMIN = "admin"
    AUTHORITY = "authority"


VALID_ROLES = {role.value for role in UserRole}


def validate_role(role: Any) -> UserRole:
    """
    Strictly validates a role against allowed UserRole values.
    Accepts UserRole enum instances or strings.
    Raises ValueError on any invalid or unsupported role.
    """
    if isinstance(role, UserRole):
        return role
    if not isinstance(role, str):
        raise ValueError(f"Invalid role type '{type(role).__name__}'. Must be string or UserRole.")
    clean = role.strip().lower()
    try:
        return UserRole(clean)
    except ValueError:
        raise ValueError(
            f"Invalid role '{role}'. Allowed roles are: {sorted(list(VALID_ROLES))}."
        )
