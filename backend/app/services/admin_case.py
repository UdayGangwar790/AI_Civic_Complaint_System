from datetime import datetime, timezone
import logging
import re
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.core.database import COMPLAINT_CASES_COLLECTION, USERS_COLLECTION, get_database
from app.models.roles import UserRole
from app.schemas.admin import (
    AuthorityUserSummary,
    DashboardSummaryResponse,
)
from app.schemas.complaint_case import CaseAssignment, ComplaintCase
from app.services.complaint_case import ComplaintCaseDatabaseError, ComplaintCaseNotFoundError
from app.services.notification import (
    trigger_case_assigned_notification,
    trigger_case_unassigned_notification,
)

logger = logging.getLogger("cvki.admin_case")

_DEFAULT_DB = object()


def _get_collection(name: str, db: object = _DEFAULT_DB):
    database = get_database() if db is _DEFAULT_DB else db
    if database is None:
        raise ComplaintCaseDatabaseError("MongoDB persistence is unavailable.")
    return database[name]


def _clean_case_doc(doc: dict) -> ComplaintCase:
    doc.pop("_id", None)
    if isinstance(doc.get("created_at"), datetime) and doc["created_at"].tzinfo is None:
        doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
    if isinstance(doc.get("updated_at"), datetime) and doc["updated_at"].tzinfo is None:
        doc["updated_at"] = doc["updated_at"].replace(tzinfo=timezone.utc)
    if (
        isinstance(doc.get("assignment"), dict)
        and isinstance(doc["assignment"].get("assigned_at"), datetime)
        and doc["assignment"]["assigned_at"].tzinfo is None
    ):
        doc["assignment"]["assigned_at"] = doc["assignment"]["assigned_at"].replace(tzinfo=timezone.utc)
    return ComplaintCase.model_validate(doc)


async def get_dashboard_summary(db: object = _DEFAULT_DB) -> DashboardSummaryResponse:
    """
    Computes real aggregated metrics across all CVKI cases in MongoDB.
    Uses native count and aggregation operations without loading entire dataset.
    """
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)

    try:
        total_cases = await cases_col.count_documents({})
        open_cases = await cases_col.count_documents({"status": {"$nin": ["resolved", "closed"]}})
        resolved_cases = await cases_col.count_documents({"status": "resolved"})
        unassigned_cases = await cases_col.count_documents({
            "$or": [
                {"assignment": None},
                {"assignment.assignment_status": "unassigned"},
                {"assignment.assigned_to_user_id": None},
            ]
        })

        # Priority Counts
        priority_counts = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "unscored": 0}
        priority_agg = await cases_col.aggregate([
            {"$group": {"_id": "$priority_analysis.priority_level", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        for entry in priority_agg:
            key = entry.get("_id")
            if key in priority_counts:
                priority_counts[key] = entry["count"]
            else:
                priority_counts["unscored"] += entry["count"]

        # Issue Counts
        issue_counts = {
            "open_damaged_manhole": 0,
            "damaged_missing_road_sign": 0,
            "road_waterlogging": 0,
            "other_civic_issue": 0,
        }
        issue_agg = await cases_col.aggregate([
            {"$group": {"_id": "$issue.class_name", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        for entry in issue_agg:
            key = entry.get("_id")
            if key in issue_counts:
                issue_counts[key] = entry["count"]
            elif key:
                issue_counts["other_civic_issue"] += entry["count"]

        # Duplicate Counts
        duplicate_counts = {
            "unique": 0,
            "possible_duplicate": 0,
            "duplicate": 0,
            "unknown": 0,
        }
        dup_agg = await cases_col.aggregate([
            {"$group": {"_id": "$duplicate_analysis.classification", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        for entry in dup_agg:
            key = entry.get("_id")
            if key in duplicate_counts:
                duplicate_counts[key] = entry["count"]
            else:
                duplicate_counts["unknown"] += entry["count"]

        # Status Counts
        status_counts = {
            "draft": 0,
            "submitted_to_cvki": 0,
            "under_review": 0,
            "resolved": 0,
            "closed": 0,
        }
        status_agg = await cases_col.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        for entry in status_agg:
            key = entry.get("_id")
            if key in status_counts:
                status_counts[key] = entry["count"]
            elif key:
                status_counts[key] = entry["count"]

        # Recent Cases (newest first, max 5)
        recent_cursor = cases_col.find({}).sort("created_at", -1).limit(5)
        recent_docs = await recent_cursor.to_list(length=5)
        recent_cases = [_clean_case_doc(d) for d in recent_docs]

        return DashboardSummaryResponse(
            total_cases=total_cases,
            open_cases=open_cases,
            resolved_cases=resolved_cases,
            unassigned_cases=unassigned_cases,
            priority_counts=priority_counts,
            issue_counts=issue_counts,
            duplicate_counts=duplicate_counts,
            status_counts=status_counts,
            recent_cases=recent_cases,
        )
    except PyMongoError as exc:
        logger.error("Admin dashboard aggregation failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc


async def get_admin_cases(
    search: Optional[str] = None,
    priority: Optional[str] = None,
    issue: Optional[str] = None,
    status: Optional[str] = None,
    assignment: Optional[str] = None,
    duplicate: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    sort_by: str = "newest",
    page: int = 1,
    page_size: int = 20,
    db: object = _DEFAULT_DB,
) -> tuple[list[ComplaintCase], int]:
    """
    Searches, filters, sorts, and paginates complaint cases across all users for administrative operations.
    """
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)
    if search is not None and len(search) > 200:
        raise ValueError("Search terms must be 200 characters or fewer.")
    if sort_by not in {"newest", "oldest", "highest_priority"}:
        raise ValueError("Unsupported sort order.")
    query: dict = {}

    # Safe Search
    if search and search.strip():
        term = search.strip()
        escaped_term = re.escape(term)
        regex_pattern = {"$regex": escaped_term, "$options": "i"}
        query["$or"] = [
            {"reference_id": regex_pattern},
            {"complaint.title": regex_pattern},
            {"complaint.description": regex_pattern},
            {"location.road": regex_pattern},
            {"location.city": regex_pattern},
            {"location.area": regex_pattern},
        ]

    # Filters
    if priority and priority.strip():
        query["priority_analysis.priority_level"] = priority.strip().upper()

    if issue and issue.strip():
        query["issue.class_name"] = issue.strip().lower()

    if status and status.strip():
        query["status"] = status.strip().lower()

    if assignment and assignment.strip():
        assign_val = assignment.strip().lower()
        if assign_val == "assigned":
            query["assignment.assignment_status"] = "assigned"
            query["assignment.assigned_to_user_id"] = {"$ne": None}
        elif assign_val == "unassigned":
            query["$and"] = query.get("$and", [])
            query["$and"].append({
                "$or": [
                    {"assignment": None},
                    {"assignment.assignment_status": "unassigned"},
                    {"assignment.assigned_to_user_id": None},
                ]
            })

    if duplicate and duplicate.strip():
        query["duplicate_analysis.classification"] = duplicate.strip().lower()

    # Date range filters
    date_filter: dict = {}
    if created_from and created_from.strip():
        try:
            norm_from = created_from.strip().replace(" ", "+").replace("Z", "+00:00")
            dt_from = datetime.fromisoformat(norm_from)
            date_filter["$gte"] = dt_from
        except ValueError:
            pass
    if created_to and created_to.strip():
        try:
            norm_to = created_to.strip().replace(" ", "+").replace("Z", "+00:00")
            dt_to = datetime.fromisoformat(norm_to)
            date_filter["$lte"] = dt_to
        except ValueError:
            pass
    if date_filter:
        query["created_at"] = date_filter

    # Sorting
    if sort_by == "oldest":
        sort_order = [("created_at", 1)]
    elif sort_by == "highest_priority":
        sort_order = [
            ("priority_analysis.priority_score", -1),
            ("created_at", -1),
        ]
    else:  # newest
        sort_order = [("created_at", -1)]

    # Pagination bounds
    safe_page = min(max(1, page), 1000)
    safe_page_size = min(max(1, page_size), 100)
    skip = (safe_page - 1) * safe_page_size

    try:
        total = await cases_col.count_documents(query)
        cursor = cases_col.find(query).sort(sort_order).skip(skip).limit(safe_page_size)
        docs = await cursor.to_list(length=safe_page_size)
        items = [_clean_case_doc(d) for d in docs]
        return items, total
    except PyMongoError as exc:
        logger.error("Admin case search failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc


async def get_admin_case_detail(reference_id: str, db: object = _DEFAULT_DB) -> ComplaintCase:
    """
    Retrieves full operational case detail for administrators.
    """
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)
    try:
        doc = await cases_col.find_one({"reference_id": reference_id})
    except PyMongoError as exc:
        logger.error("Admin case lookup failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    if doc is None:
        raise ComplaintCaseNotFoundError(reference_id)

    return _clean_case_doc(doc)


async def assign_case_to_authority(
    reference_id: str,
    authority_user_id: str,
    admin_user_id: str,
    db: object = _DEFAULT_DB,
) -> ComplaintCase:
    """
    Assigns or reassigns a complaint case to an operational authority user.
    Strictly verifies that the target user exists, is active, and possesses the authority role.
    """
    users_col = _get_collection(USERS_COLLECTION, db)
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)

    # 1. Target user validation
    target_user = await users_col.find_one({"user_id": authority_user_id})
    if target_user is None:
        raise ValueError(f"Target authority user '{authority_user_id}' does not exist.")

    if target_user.get("role") != UserRole.AUTHORITY.value:
        raise ValueError(f"Target user '{authority_user_id}' does not have the 'authority' role.")

    if not target_user.get("is_active", True):
        raise ValueError(f"Target authority user '{authority_user_id}' is inactive.")

    # 2. Case existence check
    case_doc = await cases_col.find_one({"reference_id": reference_id})
    if case_doc is None:
        raise ComplaintCaseNotFoundError(reference_id)

    # 3. Apply assignment update
    now = datetime.now(timezone.utc)
    assignment_doc = {
        "assigned_to_user_id": target_user["user_id"],
        "assigned_to_role": UserRole.AUTHORITY.value,
        "assigned_to_email": target_user.get("email"),
        "assigned_by_user_id": admin_user_id,
        "assigned_at": now,
        "assignment_status": "assigned",
    }

    try:
        updated_doc = await cases_col.find_one_and_update(
            {"reference_id": reference_id},
            {
                "$set": {
                    "assignment": assignment_doc,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
    except PyMongoError as exc:
        logger.error("Case assignment persistence failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    updated_case = _clean_case_doc(updated_doc)

    # 4. Trigger in-app notification to assigned authority
    try:
        await trigger_case_assigned_notification(
            case=updated_case,
            authority_user_id=target_user["user_id"],
            assigned_by_user_id=admin_user_id,
        )
    except Exception as exc:
        logger.warning("Failed to fire assignment notification for %s: %s", reference_id, exc)

    # 5. Record audit event (M4.8)
    try:
        from app.services.audit import AuditService
        await AuditService.record_event(
            action="case_assigned",
            result="success",
            actor_user_id=admin_user_id,
            actor_role=UserRole.ADMIN.value,
            resource_type="case",
            resource_reference_id=reference_id,
            metadata={
                "assigned_to_user_id": target_user["user_id"],
                "assigned_to_email": target_user.get("email"),
            },
            db=db,
        )
    except Exception as exc:
        logger.debug("Audit logging non-fatal exception on assign: %s", exc)

    return updated_case


async def unassign_case(
    reference_id: str,
    admin_user_id: str,
    db: object = _DEFAULT_DB,
) -> ComplaintCase:
    """
    Removes operational assignment from a case safely.
    """
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)

    case_doc = await cases_col.find_one({"reference_id": reference_id})
    if case_doc is None:
        raise ComplaintCaseNotFoundError(reference_id)

    prev_assignment = case_doc.get("assignment") or {}
    prev_authority_id = prev_assignment.get("assigned_to_user_id")

    now = datetime.now(timezone.utc)
    unassigned_doc = {
        "assigned_to_user_id": None,
        "assigned_to_role": UserRole.AUTHORITY.value,
        "assigned_to_email": None,
        "assigned_by_user_id": admin_user_id,
        "assigned_at": now,
        "assignment_status": "unassigned",
    }

    try:
        updated_doc = await cases_col.find_one_and_update(
            {"reference_id": reference_id},
            {
                "$set": {
                    "assignment": unassigned_doc,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
    except PyMongoError as exc:
        logger.error("Case unassignment persistence failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    updated_case = _clean_case_doc(updated_doc)

    # Optionally notify previous authority
    if prev_authority_id:
        try:
            await trigger_case_unassigned_notification(
                case=updated_case,
                authority_user_id=prev_authority_id,
                unassigned_by_user_id=admin_user_id,
            )
        except Exception as exc:
            logger.warning("Failed to fire unassignment notification for %s: %s", reference_id, exc)

    # Record audit event (M4.8)
    try:
        from app.services.audit import AuditService
        await AuditService.record_event(
            action="case_unassigned",
            result="success",
            actor_user_id=admin_user_id,
            actor_role=UserRole.ADMIN.value,
            resource_type="case",
            resource_reference_id=reference_id,
            metadata={
                "previous_authority_id": prev_authority_id,
            },
            db=db,
        )
    except Exception as exc:
        logger.debug("Audit logging non-fatal exception on unassign: %s", exc)

    return updated_case


async def list_authorities(
    page: int = 1,
    page_size: int = 100,
    db: object = _DEFAULT_DB,
) -> list[AuthorityUserSummary]:
    """
    Returns list of verified authority accounts for assignment selection.
    """
    users_col = _get_collection(USERS_COLLECTION, db)
    safe_page = min(max(1, page), 1000)
    safe_page_size = min(max(1, page_size), 200)
    try:
        cursor = (
            users_col.find({"role": UserRole.AUTHORITY.value})
            .sort("email", 1)
            .skip((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
        )
        docs = await cursor.to_list(length=safe_page_size)
    except PyMongoError as exc:
        logger.error("Authority account lookup failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    results: list[AuthorityUserSummary] = []
    for d in docs:
        results.append(
            AuthorityUserSummary(
                user_id=d["user_id"],
                email=d["email"],
                role=d.get("role", UserRole.AUTHORITY.value),
                is_active=d.get("is_active", True),
            )
        )
    return results
