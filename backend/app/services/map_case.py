import logging
import re
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import PyMongoError

from app.core.database import COMPLAINT_CASES_COLLECTION, mongo_manager
from app.models.roles import UserRole
from app.schemas.map_case import MapCaseItem, MapCasesResponse
from app.services.complaint_case import ComplaintCaseDatabaseError

logger = logging.getLogger("cvki.map_case")

_DEFAULT_DB = object()


def _get_collection(name: str = COMPLAINT_CASES_COLLECTION, db: object = None):
    if db is not None and hasattr(db, "__getitem__"):
        return db[name]
    database = mongo_manager.db
    if database is None:
        raise ComplaintCaseDatabaseError("MongoDB persistence is unavailable.")
    return database[name]


def _is_valid_coordinate(lat: Optional[float], lng: Optional[float]) -> bool:
    if lat is None or lng is None:
        return False
    try:
        f_lat = float(lat)
        f_lng = float(lng)
    except (ValueError, TypeError):
        return False

    # Exclude 0,0 (null-island) or out-of-bounds GPS
    if abs(f_lat) < 1e-6 and abs(f_lng) < 1e-6:
        return False
    if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lng <= 180.0):
        return False
    return True


async def get_map_cases(
    actor_user_id: str,
    actor_role: str,
    issue: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    authority: Optional[str] = None,
    assignment: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    limit: int = 500,
    db: object = _DEFAULT_DB,
) -> MapCasesResponse:
    """
    Retrieves operational map cases with real stored GPS coordinates.
    Filters out cases with missing, invalid, or (0,0) coordinates into unmapped_cases_count.
    """
    if actor_role == UserRole.CITIZEN.value:
        raise PermissionError("Citizens are not permitted to access operational map views.")

    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)
    query: dict = {}

    # Role scoping: Authorities only see cases assigned to them
    if actor_role == UserRole.AUTHORITY.value:
        query["assignment.assigned_to_user_id"] = actor_user_id

    # Filter by issue category
    if issue and issue.strip():
        query["issue.class_name"] = issue.strip().lower()

    # Filter by priority level
    if priority and priority.strip():
        query["priority_analysis.priority_level"] = priority.strip().upper()

    # Filter by status
    if status and status.strip():
        query["status"] = status.strip().lower()

    # Filter by city
    if city and city.strip():
        query["location.city"] = {"$regex": f"^{re.escape(city.strip())}", "$options": "i"}

    # Filter by authority status or name
    if authority and authority.strip():
        query["$or"] = [
            {"authority.name": {"$regex": re.escape(authority.strip()), "$options": "i"}},
            {"authority.authority_status": authority.strip().lower()},
        ]

    # Filter by assignment state
    if assignment and assignment.strip():
        assign_clean = assignment.strip().lower()
        if assign_clean == "assigned":
            query["assignment.assignment_status"] = "assigned"
            query["assignment.assigned_to_user_id"] = {"$ne": None}
        elif assign_clean == "unassigned":
            query["$and"] = query.get("$and", [])
            query["$and"].append({
                "$or": [
                    {"assignment": None},
                    {"assignment.assignment_status": "unassigned"},
                    {"assignment.assigned_to_user_id": None},
                ]
            })

    # Date range filters
    date_filter: dict = {}
    if created_from and created_from.strip():
        try:
            norm_from = created_from.strip().replace(" ", "+").replace("Z", "+00:00")
            date_filter["$gte"] = datetime.fromisoformat(norm_from)
        except ValueError:
            pass
    if created_to and created_to.strip():
        try:
            norm_to = created_to.strip().replace(" ", "+").replace("Z", "+00:00")
            date_filter["$lte"] = datetime.fromisoformat(norm_to)
        except ValueError:
            pass
    if date_filter:
        query["created_at"] = date_filter

    safe_limit = max(1, min(limit, 2000))

    try:
        total_matching = await cases_col.count_documents(query)
        cursor = cases_col.find(query).sort("created_at", -1).limit(safe_limit)
        docs = await cursor.to_list(length=safe_limit)
    except PyMongoError as exc:
        logger.error("Map case query failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    mapped_cases: list[MapCaseItem] = []
    unmapped_count = 0

    for doc in docs:
        loc = doc.get("location") or {}
        lat = loc.get("latitude")
        lng = loc.get("longitude")

        if not _is_valid_coordinate(lat, lng):
            unmapped_count += 1
            continue

        issue_obj = doc.get("issue") or {}
        prio_obj = doc.get("priority_analysis") or {}
        auth_obj = doc.get("authority") or {}
        asgn_obj = doc.get("assignment") or {}

        created_at_val = doc.get("created_at")
        if isinstance(created_at_val, datetime) and created_at_val.tzinfo is None:
            created_at_val = created_at_val.replace(tzinfo=timezone.utc)

        is_assigned = (
            asgn_obj.get("assignment_status") == "assigned"
            and bool(asgn_obj.get("assigned_to_user_id"))
        )

        mapped_cases.append(
            MapCaseItem(
                reference_id=doc.get("reference_id", ""),
                issue=issue_obj.get("class_name", "other_civic_issue"),
                issue_label=issue_obj.get("label", "Civic Issue"),
                status=doc.get("status", "submitted_to_cvki"),
                priority=prio_obj.get("priority_level", "P3"),
                latitude=float(lat),
                longitude=float(lng),
                road=loc.get("road"),
                city=loc.get("city"),
                authority_name=auth_obj.get("name"),
                authority_status=auth_obj.get("authority_status"),
                assigned=is_assigned,
                assigned_to_user_id=asgn_obj.get("assigned_to_user_id"),
                assignment_status=asgn_obj.get("assignment_status", "assigned" if is_assigned else "unassigned"),
                created_at=created_at_val,
            )
        )

    return MapCasesResponse(
        mapped_cases=mapped_cases,
        total_mapped=len(mapped_cases),
        unmapped_cases_count=unmapped_count,
        total_matching=total_matching,
    )
