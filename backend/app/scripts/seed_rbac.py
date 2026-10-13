import argparse
import asyncio
import logging
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.database import USERS_COLLECTION, mongo_client_options
from app.core.security import hash_password
from app.models.roles import UserRole, validate_role
from app.services.user import MongoUserRepository, set_user_repository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cvki.seed_rbac")


async def seed_account(
    email: str,
    password: str,
    role: str,
    mongo_client: AsyncIOMotorClient = None,
) -> dict:
    """
    Safely creates or promotes a privileged account (admin or authority).
    Uses bcrypt hashing and canonical role validation.
    """
    validated_role = validate_role(role)
    normalized_email = email.strip().lower()

    if mongo_client is None:
        mongo_client = AsyncIOMotorClient(settings.MONGODB_URI, **mongo_client_options())

    db = mongo_client[settings.MONGODB_DB_NAME]
    repo = MongoUserRepository(db=db)
    set_user_repository(repo)

    existing = await repo.get_by_email(normalized_email)
    if existing:
        logger.info("Account '%s' exists. Updating role to '%s'...", normalized_email, validated_role.value)
        updated = await repo.update_role(existing["user_id"], validated_role)
        logger.info("Successfully updated account '%s' (user_id: %s) to role '%s'.", normalized_email, existing["user_id"], validated_role.value)
        return {"user_id": existing["user_id"], "email": normalized_email, "role": validated_role.value, "action": "updated"}
    else:
        logger.info("Creating new privileged account '%s' with role '%s'...", normalized_email, validated_role.value)
        hashed = hash_password(password)
        created = await repo.create_user(normalized_email, hashed, role=validated_role)
        logger.info("Successfully created account '%s' (user_id: %s) with role '%s'.", normalized_email, created["user_id"], validated_role.value)
        return {"user_id": created["user_id"], "email": normalized_email, "role": validated_role.value, "action": "created"}


async def bootstrap_default_privileged_accounts():
    """
    Bootstraps default development admin and authority accounts from environment variables.
    """
    admin_email = os.environ.get("CVKI_BOOTSTRAP_ADMIN_EMAIL", "admin@cvki.gov.in")
    admin_password = os.environ.get("CVKI_BOOTSTRAP_ADMIN_PASSWORD")

    auth_email = os.environ.get("CVKI_BOOTSTRAP_AUTHORITY_EMAIL", "authority@bbmp.gov.in")
    auth_password = os.environ.get("CVKI_BOOTSTRAP_AUTHORITY_PASSWORD")

    if not admin_password or not auth_password:
        raise ValueError(
            "Set CVKI_BOOTSTRAP_ADMIN_PASSWORD and "
            "CVKI_BOOTSTRAP_AUTHORITY_PASSWORD before using --bootstrap."
        )

    client = AsyncIOMotorClient(settings.MONGODB_URI, **mongo_client_options())
    try:
        await seed_account(admin_email, admin_password, UserRole.ADMIN.value, client)
        await seed_account(auth_email, auth_password, UserRole.AUTHORITY.value, client)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Seed privileged CVKI accounts (admin / authority)")
    parser.add_argument("--email", help="Account email address")
    parser.add_argument("--password", help="Account password (plain text, will be bcrypt hashed)")
    parser.add_argument("--role", choices=[r.value for r in UserRole], help="Target role (admin or authority)")
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap default dev admin & authority accounts")

    args = parser.parse_args()

    if args.bootstrap:
        asyncio.run(bootstrap_default_privileged_accounts())
    elif args.email and args.password and args.role:
        client = AsyncIOMotorClient(settings.MONGODB_URI, **mongo_client_options())
        try:
            asyncio.run(seed_account(args.email, args.password, args.role, client))
        finally:
            client.close()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
