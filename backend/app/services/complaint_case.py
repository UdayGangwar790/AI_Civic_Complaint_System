from datetime import datetime, timezone
import inspect
import logging
from secrets import token_hex
from threading import Lock
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError

from app.core.database import COMPLAINT_CASES_COLLECTION, get_database
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseStatus,
    ComplaintCase,
    ComplaintCaseCreateRequest,
    ComplaintCaseStatus,
    ComplaintCaseSummary,
    ComplaintHistoryResponse,
    FollowUp,
)
from app.services.complaint import ISSUE_DEFINITIONS, UnsupportedIssueError
from app.services.authority import resolve_authority_for_location

logger = logging.getLogger("cvki.complaint_case")

STATUS_DESCRIPTIONS = {
    "draft": "The complaint draft exists but has not been created as a CVKI case.",
    "submitted_to_cvki": "The complaint has been created inside the CVKI application.",
    "under_review": "The CVKI case is marked for internal review; no government submission is implied.",
    "resolved": "The CVKI case is marked resolved internally; no government action is implied.",
    "closed": "The CVKI case is closed internally; no government action is implied.",
}


class ComplaintCaseNotFoundError(LookupError):
    """The requested internal CVKI reference does not exist."""


class ComplaintCaseDuplicateError(ValueError):
    """A complaint case with this reference ID already exists."""


class ComplaintCaseDatabaseError(RuntimeError):
    """The persistence layer is unavailable or encountered an error."""


class ComplaintCaseRepository:
    """Abstract interface for complaint case repository."""

    async def save(self, case: ComplaintCase) -> ComplaintCase:
        raise NotImplementedError

    async def get(self, reference_id: str) -> ComplaintCase:
        raise NotImplementedError

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> tuple[list[ComplaintCaseSummary], int]:
        raise NotImplementedError

    async def list_recent_candidates(self, limit: int = 100) -> list[ComplaintCase]:
        raise NotImplementedError

    async def find_nearby_candidates(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        cutoff: datetime,
        issue_category: Optional[str] = None,
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[ComplaintCase]:
        raise NotImplementedError


_DEFAULT_DB = object()


class MongoComplaintCaseRepository(ComplaintCaseRepository):
    """
    MongoDB-backed complaint case repository providing persistent storage.
    Enforces uniqueness on reference_id and persists complete case data.
    """

    def __init__(
        self,
        db: object = _DEFAULT_DB,
        collection_name: str = COMPLAINT_CASES_COLLECTION,
    ):
        self._db = db
        self._collection_name = collection_name

    def _get_collection(self):
        db = get_database() if self._db is _DEFAULT_DB else self._db
        if db is None:
            raise ComplaintCaseDatabaseError("MongoDB persistence is unavailable.")
        return db[self._collection_name]

    async def save(self, case: ComplaintCase) -> ComplaintCase:
        collection = self._get_collection()

        created_at = (
            case.created_at
            if case.created_at.tzinfo is not None
            else case.created_at.replace(tzinfo=timezone.utc)
        )
        updated_at = case.updated_at or created_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        geo_location = None
        if case.location.latitude is not None and case.location.longitude is not None:
            try:
                from app.services.spatial import to_geojson_point
                geo_location = to_geojson_point(case.location.latitude, case.location.longitude)
            except Exception:
                geo_location = None

        if geo_location and not case.geo_location:
            case = case.model_copy(update={"geo_location": geo_location})

        doc = {
            "reference_id": case.reference_id,
            "user_id": case.user_id,
            "status": case.status,
            "created_at": created_at,
            "updated_at": updated_at,
            "external_submission_status": "not_submitted",
            "issue": case.issue.model_dump(mode="python"),
            "location": case.location.model_dump(mode="python"),
            "geo_location": geo_location,
            "authority": case.authority.model_dump(mode="python"),
            "complaint": case.complaint.model_dump(mode="python"),
            "evidence": list(case.evidence),
            "follow_up": case.follow_up.model_dump(mode="python"),
            "nlp_analysis": case.nlp_analysis.model_dump(mode="python") if case.nlp_analysis else None,
            "duplicate_analysis": case.duplicate_analysis.model_dump(mode="python") if case.duplicate_analysis else None,
            "priority_analysis": case.priority_analysis.model_dump(mode="python") if case.priority_analysis else None,
            "recurrence_analysis": case.recurrence_analysis.model_dump(mode="python") if case.recurrence_analysis else None,
            "resolution_evidence": [item.model_dump(mode="python") for item in case.resolution_evidence],
            "resolution_evidence_recorded_at": case.resolution_evidence_recorded_at,
            "assignment": case.assignment.model_dump(mode="python") if case.assignment else None,
        }

        try:
            await collection.insert_one(doc)
        except DuplicateKeyError as exc:
            logger.warning("Duplicate reference_id prevented: %s", case.reference_id)
            raise ComplaintCaseDuplicateError(
                f"Complaint case with reference '{case.reference_id}' already exists."
            ) from exc
        except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
            logger.error("Database error saving case %s: %s", case.reference_id, exc.__class__.__name__)
            raise ComplaintCaseDatabaseError(
                f"Database error during case persistence: {exc.__class__.__name__}"
            ) from exc

        return case

    async def get(self, reference_id: str) -> ComplaintCase:
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"reference_id": reference_id})
        except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
            logger.error("Database error retrieving case %s: %s", reference_id, exc.__class__.__name__)
            raise ComplaintCaseDatabaseError(
                f"Database error retrieving case: {exc.__class__.__name__}"
            ) from exc

        if doc is None:
            raise ComplaintCaseNotFoundError(reference_id)

        doc.pop("_id", None)
        if doc.get("created_at") and doc["created_at"].tzinfo is None:
            doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
        if doc.get("updated_at") and doc["updated_at"].tzinfo is None:
            doc["updated_at"] = doc["updated_at"].replace(tzinfo=timezone.utc)

        return ComplaintCase.model_validate(doc)

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> tuple[list[ComplaintCaseSummary], int]:
        collection = self._get_collection()
        filter_query = {"user_id": user_id}
        try:
            total = await collection.count_documents(filter_query)
            cursor = (
                collection.find(filter_query)
                .sort("created_at", -1)
                .skip((page - 1) * limit)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
        except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
            logger.error("Database error listing cases for user %s: %s", user_id, exc.__class__.__name__)
            raise ComplaintCaseDatabaseError(
                f"Database error listing user cases: {exc.__class__.__name__}"
            ) from exc

        items: list[ComplaintCaseSummary] = []
        for doc in docs:
            doc.pop("_id", None)
            created_at = doc.get("created_at")
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            updated_at = doc.get("updated_at") or created_at
            if updated_at and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            loc = doc.get("location") or {}
            loc_parts = [p for p in [loc.get("road"), loc.get("area"), loc.get("city")] if p]
            loc_summary = ", ".join(loc_parts) if loc_parts else (loc.get("state") or None)

            issue = doc.get("issue") or {}
            complaint = doc.get("complaint") or {}

            items.append(
                ComplaintCaseSummary(
                    reference_id=doc["reference_id"],
                    created_at=created_at,
                    updated_at=updated_at,
                    status=doc.get("status", "submitted_to_cvki"),
                    external_submission_status="not_submitted",
                    issue_class=issue.get("class_name", ""),
                    issue_label=issue.get("label", ""),
                    severity=issue.get("severity", "medium"),
                    confidence=float(issue.get("confidence", 0.0)),
                    location_summary=loc_summary,
                    title=complaint.get("title", ""),
                    assignment=CaseAssignment.model_validate(doc["assignment"]) if doc.get("assignment") else None,
                )
            )
        return items, total

    async def list_recent_candidates(self, limit: int = 100) -> list[ComplaintCase]:
        collection = self._get_collection()
        try:
            cursor = collection.find({}).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
        except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
            logger.error("Database error listing candidates: %s", exc.__class__.__name__)
            raise ComplaintCaseDatabaseError(
                f"Database error listing candidates: {exc.__class__.__name__}"
            ) from exc

        cases: list[ComplaintCase] = []
        for doc in docs:
            doc.pop("_id", None)
            if doc.get("created_at") and doc["created_at"].tzinfo is None:
                doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
            if doc.get("updated_at") and doc["updated_at"].tzinfo is None:
                doc["updated_at"] = doc["updated_at"].replace(tzinfo=timezone.utc)
            try:
                cases.append(ComplaintCase.model_validate(doc))
            except Exception as e:
                logger.warning("Error parsing candidate case: %s", e)
        return cases

    async def find_nearby_candidates(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        cutoff: datetime,
        issue_category: Optional[str] = None,
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[ComplaintCase]:
        collection = self._get_collection()
        query: dict[str, Any] = {
            "location.latitude": {"$gte": min_lat, "$lte": max_lat},
            "location.longitude": {"$gte": min_lon, "$lte": max_lon},
            "created_at": {"$gte": cutoff},
            "status": {"$ne": "draft"},
        }
        if issue_category and issue_category.strip():
            query["issue.class_name"] = issue_category.strip().lower()
        if unresolved_only:
            query["status"] = {"$nin": ["resolved", "closed"]}

        try:
            cursor = collection.find(query).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
        except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError) as exc:
            logger.error("Database error finding nearby candidates: %s", exc.__class__.__name__)
            raise ComplaintCaseDatabaseError(
                f"Database error finding nearby candidates: {exc.__class__.__name__}"
            ) from exc

        cases: list[ComplaintCase] = []
        for doc in docs:
            doc.pop("_id", None)
            if doc.get("created_at") and doc["created_at"].tzinfo is None:
                doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
            if doc.get("updated_at") and doc["updated_at"].tzinfo is None:
                doc["updated_at"] = doc["updated_at"].replace(tzinfo=timezone.utc)
            try:
                cases.append(ComplaintCase.model_validate(doc))
            except Exception as e:
                logger.warning("Error parsing candidate case: %s", e)
        return cases


class InMemoryComplaintCaseRepository(ComplaintCaseRepository):
    """
    In-memory complaint case repository preserved for isolated synchronous testing.
    """

    def __init__(self):
        self._cases: dict[str, ComplaintCase] = {}
        self._lock = Lock()

    def save(self, case: ComplaintCase) -> ComplaintCase:
        if case.location.latitude is not None and case.location.longitude is not None and not case.geo_location:
            try:
                from app.services.spatial import to_geojson_point
                geo = to_geojson_point(case.location.latitude, case.location.longitude)
                case = case.model_copy(update={"geo_location": geo})
            except Exception:
                pass
        with self._lock:
            self._cases[case.reference_id] = case
        return case

    def get(self, reference_id: str) -> ComplaintCase:
        with self._lock:
            case = self._cases.get(reference_id)
        if case is None:
            raise ComplaintCaseNotFoundError(reference_id)
        return case

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> tuple[list[ComplaintCaseSummary], int]:
        with self._lock:
            matching = [c for c in self._cases.values() if c.user_id == user_id]
        matching.sort(key=lambda c: c.created_at, reverse=True)
        total = len(matching)
        start = (page - 1) * limit
        end = start + limit
        paginated = matching[start:end]

        items = []
        for c in paginated:
            loc = c.location
            loc_parts = [p for p in [loc.road, loc.area, loc.city] if p]
            loc_summary = ", ".join(loc_parts) if loc_parts else (loc.state or None)

            items.append(
                ComplaintCaseSummary(
                    reference_id=c.reference_id,
                    created_at=c.created_at,
                    updated_at=c.updated_at or c.created_at,
                    status=c.status,
                    external_submission_status="not_submitted",
                    issue_class=c.issue.class_name,
                    issue_label=c.issue.label,
                    severity=c.issue.severity,
                    confidence=c.issue.confidence,
                    location_summary=loc_summary,
                    title=c.complaint.title,
                    assignment=c.assignment,
                )
            )
        return items, total

    async def list_recent_candidates(self, limit: int = 100) -> list[ComplaintCase]:
        with self._lock:
            all_cases = list(self._cases.values())
        all_cases.sort(key=lambda c: c.created_at, reverse=True)
        return all_cases[:limit]

    async def find_nearby_candidates(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        cutoff: datetime,
        issue_category: Optional[str] = None,
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[ComplaintCase]:
        with self._lock:
            all_cases = list(self._cases.values())
        matching = []
        for c in all_cases:
            if c.status == "draft":
                continue
            loc = c.location
            if loc.latitude is None or loc.longitude is None:
                continue
            c_created = c.created_at if c.created_at.tzinfo is not None else c.created_at.replace(tzinfo=timezone.utc)
            if c_created < cutoff:
                continue
            if not (min_lat <= loc.latitude <= max_lat and min_lon <= loc.longitude <= max_lon):
                continue
            if issue_category and c.issue.class_name.lower() != issue_category.strip().lower():
                continue
            if unresolved_only and c.status in ("resolved", "closed"):
                continue
            matching.append(c)
        matching.sort(key=lambda c: c.created_at, reverse=True)
        return matching[:limit]


# Default active repository: persistent MongoDB
case_repository: ComplaintCaseRepository = MongoComplaintCaseRepository()


def set_case_repository(repo: ComplaintCaseRepository) -> None:
    """Allows test fixtures to set or reset the active case repository."""
    global case_repository
    case_repository = repo


def _new_reference_id() -> str:
    return f"CVKI-{datetime.now(timezone.utc):%Y%m%d}-{token_hex(3).upper()}"


def _follow_up(
    authority: AuthorityResult,
    issue_category: str | None = None,
    location: ComplaintLocation | None = None,
    language: str = "en",
    complaint_title: str | None = None,
    complaint_description: str | None = None,
) -> FollowUp:
    if authority.authority_status == "verified":
        guidance = (
            "Your complaint has been created inside the CVKI application and saved as a CVKI case. "
            "No external government complaint has been submitted yet. "
            "Use the verified authority information and its official complaint channel when available."
        )
    else:
        guidance = (
            "Your complaint has been created inside the CVKI application and saved as a CVKI case. "
            "No external government complaint has been submitted yet. "
            "Responsible road authority could not be verified from available authoritative data. "
            "Please verify the appropriate authority before external submission."
        )

    official_guidance = None
    if issue_category:
        try:
            from app.schemas.guidance import GovernmentGuidanceRequest
            from app.services.guidance import generate_government_guidance

            official_guidance = generate_government_guidance(
                GovernmentGuidanceRequest(
                    issue_category=issue_category,
                    location=location,
                    authority=authority,
                    language=language,
                    complaint_title=complaint_title,
                    complaint_description=complaint_description,
                )
            )
        except Exception as exc:
            logger.warning("Failed to generate official guidance for case follow-up: %s", exc)

    return FollowUp(
        guidance=guidance,
        external_submission_status="not_submitted",
        official_guidance=official_guidance,
    )


async def create_case(
    request: ComplaintCaseCreateRequest,
    user_id: Optional[str] = None,
) -> ComplaintCase:
    definition = ISSUE_DEFINITIONS.get(request.issue.class_name)
    if definition is None:
        raise UnsupportedIssueError("Unsupported civic issue class.")
    if request.issue.label != definition.label or request.issue.severity != definition.severity:
        raise ValueError("Issue label or severity does not match the supported CVKI issue class.")

    now = datetime.now(timezone.utc)
    loc = request.location or ComplaintLocation()
    authority = resolve_authority_for_location(loc)
    follow_up = _follow_up(
        authority=authority,
        issue_category=request.issue.class_name,
        location=loc,
        language=request.complaint.language,
        complaint_title=request.complaint.title,
        complaint_description=request.complaint.description,
    )

    # M3.6 NLP Complaint Intelligence
    nlp_analysis = request.nlp_analysis
    if nlp_analysis is None:
        try:
            from app.schemas.nlp import NLPAnalysisRequest
            from app.services.nlp import analyze_complaint_text

            nlp_analysis = analyze_complaint_text(
                NLPAnalysisRequest(
                    title=request.complaint.title,
                    description=request.complaint.description,
                    language=request.complaint.language,
                    issue_class=request.issue.class_name,
                )
            )
        except Exception as exc:
            logger.warning("Failed to generate NLP analysis during case creation: %s", exc)

    # M3.7 Duplicate Complaint Detection
    duplicate_analysis = request.duplicate_analysis
    if duplicate_analysis is None:
        try:
            from app.schemas.duplicate import DuplicateCheckRequest
            from app.services.duplicate import check_complaint_duplicate

            duplicate_analysis = await check_complaint_duplicate(
                DuplicateCheckRequest(
                    complaint_text=f"{request.complaint.title} {request.complaint.description}".strip(),
                    issue_category=request.issue.class_name,
                    latitude=loc.latitude,
                    longitude=loc.longitude,
                    created_at=now,
                )
            )
        except Exception as exc:
            logger.warning("Failed to perform duplicate check during case creation: %s", exc)

    # M5.2 recurrence is separate from M3.7 same-incident duplicate detection.
    from app.services.civic_intelligence import analyze_recurrence_for_new_case

    recurrence_analysis = await analyze_recurrence_for_new_case(
        issue_category=request.issue.class_name,
        location=loc,
        created_at=now,
    )

    # M3.8 Priority / Risk Intelligence
    # Case triage is recomputed from server-side inputs so clients cannot bypass M5.2 recurrence.
    priority_analysis = None
    try:
        from app.schemas.priority import PriorityScoreRequest
        from app.services.priority import calculate_priority_score

        priority_analysis = calculate_priority_score(
            PriorityScoreRequest(
                issue_category=request.issue.class_name,
                cv_confidence=request.issue.confidence,
                nlp_analysis=nlp_analysis,
                duplicate_analysis=duplicate_analysis,
                location_context=loc,
                authority_context=authority,
            ),
            recurrence_analysis=recurrence_analysis,
        )
    except Exception as exc:
        logger.warning("Failed to calculate priority score during case creation: %s", exc)

    case = ComplaintCase(
        reference_id=_new_reference_id(),
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=now,
        updated_at=now,
        issue=request.issue,
        location=loc,
        authority=authority,
        complaint=request.complaint,
        evidence=list(request.evidence),
        follow_up=follow_up,
        nlp_analysis=nlp_analysis,
        duplicate_analysis=duplicate_analysis,
        priority_analysis=priority_analysis,
        recurrence_analysis=recurrence_analysis,
    )
    saved = case_repository.save(case)
    if inspect.isawaitable(saved):
        case_saved = await saved
    else:
        case_saved = saved

    # M3.9 Automatic Notification Triggers
    if user_id:
        try:
            from app.services.notification import (
                trigger_case_created_notification,
                trigger_duplicate_detected_notification,
                trigger_priority_assigned_notification,
            )
            await trigger_case_created_notification(case_saved)
            if duplicate_analysis and duplicate_analysis.classification in ("possible_duplicate", "duplicate"):
                await trigger_duplicate_detected_notification(case_saved)
            if priority_analysis and priority_analysis.priority_level in ("P1", "P2"):
                await trigger_priority_assigned_notification(case_saved)
        except Exception as exc:
            logger.warning("Failed to trigger automatic notification for case %s: %s", case_saved.reference_id, exc)

    return case_saved


async def get_user_cases(
    user_id: str,
    page: int = 1,
    limit: int = 10,
) -> ComplaintHistoryResponse:
    page = min(max(1, page), 1000)
    limit = min(max(1, limit), 50)
    items, total = await case_repository.list_by_user(user_id, page=page, limit=limit)
    pages = (total + limit - 1) // limit if total > 0 else 1
    return ComplaintHistoryResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


async def get_case(reference_id: str) -> ComplaintCase:
    res = case_repository.get(reference_id)
    if inspect.isawaitable(res):
        return await res
    return res


async def get_case_status(reference_id: str) -> ComplaintCaseStatus:
    case = await get_case(reference_id)
    return ComplaintCaseStatus(
        reference_id=case.reference_id,
        status=case.status,
        status_description=STATUS_DESCRIPTIONS[case.status],
        external_submission_status="not_submitted",
    )
