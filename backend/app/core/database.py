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
AUTHORITY_CACHE_COLLECTION = "authority_cache"
GEO_CACHE_COLLECTION = "geo_cache"
EXTERNAL_CIVIC_CACHE_COLLECTION = "external_civic_cache"
EVIDENCE_RECORDS_COLLECTION = "evidence_records"
KNOWLEDGE_NODES_COLLECTION = "knowledge_nodes"
KNOWLEDGE_EDGES_COLLECTION = "knowledge_edges"
GOVERNMENT_SUBMISSIONS_COLLECTION = "government_submissions"
GOVERNMENT_INTEGRATIONS_COLLECTION = "government_integrations"
GOVERNMENT_REFERENCE_MAPPINGS_COLLECTION = "government_reference_mappings"
GOVERNMENT_STATUS_RECORDS_COLLECTION = "government_status_records"
ESCALATION_DECISIONS_COLLECTION = "escalation_decisions"
ESCALATION_POLICIES_COLLECTION = "escalation_policies"
RESOLUTION_VERIFICATIONS_COLLECTION = "resolution_verifications"


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
    await cases_col.create_index([("geo_location", "2dsphere")], sparse=True)
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

    cache_col = db[AUTHORITY_CACHE_COLLECTION]
    await cache_col.create_index("cache_key", unique=True)
    await cache_col.create_index("expires_at")
    await cache_col.create_index("retrieved_at")
    logger.info("MongoDB indexes verified for collection '%s'.", AUTHORITY_CACHE_COLLECTION)

    geo_col = db[GEO_CACHE_COLLECTION]
    await geo_col.create_index("cache_key", unique=True)
    await geo_col.create_index("expires_at")
    await geo_col.create_index("retrieved_at")
    logger.info("MongoDB indexes verified for collection '%s'.", GEO_CACHE_COLLECTION)

    ext_civic_col = db[EXTERNAL_CIVIC_CACHE_COLLECTION]
    await ext_civic_col.create_index("cache_key", unique=True)
    await ext_civic_col.create_index("expires_at")
    await ext_civic_col.create_index("retrieved_at")
    logger.info("MongoDB indexes verified for collection '%s'.", EXTERNAL_CIVIC_CACHE_COLLECTION)

    evidence_col = db[EVIDENCE_RECORDS_COLLECTION]
    await evidence_col.create_index("evidence_id", unique=True)
    await evidence_col.create_index("case_reference")
    await evidence_col.create_index("claim_type")
    await evidence_col.create_index("matched_attribute")
    await evidence_col.create_index("verification_state")
    await evidence_col.create_index("evidence_hash")
    await evidence_col.create_index([("case_reference", 1), ("created_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", EVIDENCE_RECORDS_COLLECTION)

    nodes_col = db[KNOWLEDGE_NODES_COLLECTION]
    await nodes_col.create_index("node_id", unique=True)
    await nodes_col.create_index("canonical_key", unique=True)
    await nodes_col.create_index("node_type")
    await nodes_col.create_index("case_references")
    logger.info("MongoDB indexes verified for collection '%s'.", KNOWLEDGE_NODES_COLLECTION)

    edges_col = db[KNOWLEDGE_EDGES_COLLECTION]
    await edges_col.create_index("edge_id", unique=True)
    await edges_col.create_index("canonical_edge_key", unique=True)
    await edges_col.create_index("from_node")
    await edges_col.create_index("to_node")
    await edges_col.create_index("relation_type")
    await edges_col.create_index("verification_state")
    await edges_col.create_index("case_reference")
    await edges_col.create_index([("from_node", 1), ("relation_type", 1)])
    logger.info("MongoDB indexes verified for collection '%s'.", KNOWLEDGE_EDGES_COLLECTION)

    gov_sub_col = db[GOVERNMENT_SUBMISSIONS_COLLECTION]
    await gov_sub_col.create_index("submission_id", unique=True)
    await gov_sub_col.create_index("case_reference_id")
    await gov_sub_col.create_index("integration_id")
    await gov_sub_col.create_index("submission_state")
    await gov_sub_col.create_index("external_reference_id")
    await gov_sub_col.create_index([("case_reference_id", 1), ("integration_id", 1)])
    await gov_sub_col.create_index([("submitted_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", GOVERNMENT_SUBMISSIONS_COLLECTION)

    gov_int_col = db[GOVERNMENT_INTEGRATIONS_COLLECTION]
    await gov_int_col.create_index("integration_id", unique=True)
    await gov_int_col.create_index("authority")
    await gov_int_col.create_index("enabled")
    logger.info("MongoDB indexes verified for collection '%s'.", GOVERNMENT_INTEGRATIONS_COLLECTION)

    gov_ref_col = db[GOVERNMENT_REFERENCE_MAPPINGS_COLLECTION]
    await gov_ref_col.create_index("mapping_id", unique=True)
    await gov_ref_col.create_index("cvki_reference_id")
    await gov_ref_col.create_index("submission_id")
    await gov_ref_col.create_index("integration_id")
    await gov_ref_col.create_index("government_reference_id")
    await gov_ref_col.create_index("mapping_state")
    await gov_ref_col.create_index([("integration_id", 1), ("government_reference_id", 1)])
    await gov_ref_col.create_index([("cvki_reference_id", 1), ("integration_id", 1)])
    logger.info("MongoDB indexes verified for collection '%s'.", GOVERNMENT_REFERENCE_MAPPINGS_COLLECTION)

    gov_status_col = db[GOVERNMENT_STATUS_RECORDS_COLLECTION]
    await gov_status_col.create_index("sync_id", unique=True)
    await gov_status_col.create_index("cvki_reference_id")
    await gov_status_col.create_index("integration_id")
    await gov_status_col.create_index("government_reference_id")
    await gov_status_col.create_index([("cvki_reference_id", 1), ("integration_id", 1)])
    await gov_status_col.create_index([("cvki_reference_id", 1), ("retrieved_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", GOVERNMENT_STATUS_RECORDS_COLLECTION)

    esc_dec_col = db[ESCALATION_DECISIONS_COLLECTION]
    await esc_dec_col.create_index("decision_id", unique=True)
    await esc_dec_col.create_index("cvki_reference_id")
    await esc_dec_col.create_index("integration_id")
    await esc_dec_col.create_index([("cvki_reference_id", 1), ("evaluated_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", ESCALATION_DECISIONS_COLLECTION)

    esc_pol_col = db[ESCALATION_POLICIES_COLLECTION]
    await esc_pol_col.create_index("policy_id", unique=True)
    await esc_pol_col.create_index("integration_id")
    await esc_pol_col.create_index("enabled")
    logger.info("MongoDB indexes verified for collection '%s'.", ESCALATION_POLICIES_COLLECTION)

    res_verif_col = db[RESOLUTION_VERIFICATIONS_COLLECTION]
    await res_verif_col.create_index("verification_id", unique=True)
    await res_verif_col.create_index("cvki_reference_id")
    await res_verif_col.create_index("integration_id")
    await res_verif_col.create_index("citizen_user_id")
    await res_verif_col.create_index("verification_status")
    await res_verif_col.create_index([("cvki_reference_id", 1), ("submitted_at", -1)])
    logger.info("MongoDB indexes verified for collection '%s'.", RESOLUTION_VERIFICATIONS_COLLECTION)


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
