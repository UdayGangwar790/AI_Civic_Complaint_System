import logging
import re
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from app.core.config import settings

logger = logging.getLogger("cvki.database")

COMPLAINT_CASES_COLLECTION = "complaint_cases"
USERS_COLLECTION = "users"
NOTIFICATIONS_COLLECTION = "notifications"
AUDIT_LOGS_COLLECTION = "audit_logs"


def sanitize_mongodb_uri(uri: str) -> str:
    """
    Masks credentials in a MongoDB connection URI for safe logging.
    """
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", uri)


class MongoManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


mongo_manager = MongoManager()


def mongo_client_options() -> dict[str, int]:
    return {
        "serverSelectionTimeoutMS": settings.MONGODB_TIMEOUT_MS,
        "connectTimeoutMS": settings.MONGODB_CONNECT_TIMEOUT_MS,
        "socketTimeoutMS": settings.MONGODB_SOCKET_TIMEOUT_MS,
    }


async def init_mongo_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Ensures required indexes exist on MongoDB collections.
    reference_id must be strictly unique to prevent duplicate case creation.
    email and user_id must be unique on the users collection.
    notification_id must be unique on notifications collection.
    event_id must be unique on audit_logs collection.
    """
    cases_col = db[COMPLAINT_CASES_COLLECTION]
    await cases_col.create_index("reference_id", unique=True)
    await cases_col.create_index("created_at")
    await cases_col.create_index([("user_id", 1), ("created_at", -1)])
    await cases_col.create_index("status")
    await cases_col.create_index("issue.class_name")
    await cases_col.create_index("priority_analysis.priority_level")
    await cases_col.create_index("assignment.assigned_to_user_id")
    await cases_col.create_index("assignment.assignment_status")
    await cases_col.create_index("duplicate_analysis.classification")
    await cases_col.create_index([("priority_analysis.priority_score", -1), ("created_at", -1)])
    await cases_col.create_index([("assignment.assigned_to_user_id", 1), ("created_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", COMPLAINT_CASES_COLLECTION)

    users_col = db[USERS_COLLECTION]
    await users_col.create_index("email", unique=True)
    await users_col.create_index("user_id", unique=True)
    await users_col.create_index([("role", 1), ("email", 1)])
    logger.info("MongoDB indexes verified for collection '%s'.", USERS_COLLECTION)

    notifs_col = db[NOTIFICATIONS_COLLECTION]
    await notifs_col.create_index("notification_id", unique=True)
    await notifs_col.create_index([("user_id", 1), ("created_at", -1)])
    await notifs_col.create_index([("user_id", 1), ("is_read", 1)])
    await notifs_col.create_index([("reference_id", 1), ("created_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", NOTIFICATIONS_COLLECTION)

    audit_col = db[AUDIT_LOGS_COLLECTION]
    await audit_col.create_index("event_id", unique=True)
    await audit_col.create_index([("timestamp", -1)])
    await audit_col.create_index([("actor_user_id", 1), ("timestamp", -1)])
    await audit_col.create_index([("action", 1), ("timestamp", -1)])
    await audit_col.create_index([("result", 1), ("timestamp", -1)])
    await audit_col.create_index([("resource_reference_id", 1), ("timestamp", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", AUDIT_LOGS_COLLECTION)


async def connect_to_mongo(uri: Optional[str] = None, db_name: Optional[str] = None) -> bool:
    """
    Initializes the shared MongoDB client and verifies connection via ping.
    Returns True on success, False if connection fails.
    """
    target_uri = uri or settings.MONGODB_URI
    target_db_name = db_name or settings.MONGODB_DB_NAME
    logger.info("Connecting to MongoDB (database: %s)...", target_db_name)
    client: Optional[AsyncIOMotorClient] = None
    try:
        client = AsyncIOMotorClient(
            target_uri,
            **mongo_client_options(),
        )
        # Verify connection immediately via admin ping
        await client.admin.command("ping")
        mongo_manager.client = client
        mongo_manager.db = client[target_db_name]

        await init_mongo_indexes(mongo_manager.db)
        logger.info("Successfully connected to MongoDB (%s).", target_db_name)
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
        logger.error(
            "MongoDB connection failed (database: %s, error_type=%s).",
            target_db_name,
            exc.__class__.__name__,
        )
        if client is not None:
            client.close()
        mongo_manager.client = None
        mongo_manager.db = None
        return False


async def close_mongo_connection() -> None:
    """
    Gracefully shuts down the MongoDB client connection pool.
    """
    if mongo_manager.client is not None:
        logger.info("Closing MongoDB connection pool...")
        mongo_manager.client.close()
        mongo_manager.client = None
        mongo_manager.db = None
        logger.info("MongoDB connection pool closed.")


async def is_mongo_healthy() -> bool:
    """
    Checks if the active MongoDB connection is healthy and responsive.
    """
    if mongo_manager.client is None or mongo_manager.db is None:
        return False
    try:
        await mongo_manager.client.admin.command("ping")
        return True
    except PyMongoError as exc:
        logger.debug("MongoDB readiness probe failed (error_type=%s).", exc.__class__.__name__)
        return False


def get_database() -> Optional[AsyncIOMotorDatabase]:
    """
    Returns the active AsyncIOMotorDatabase instance, or None if unavailable.
    """
    return mongo_manager.db
