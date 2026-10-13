from datetime import datetime, timezone
import inspect
import logging
from secrets import token_hex
from threading import Lock
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.core.database import NOTIFICATIONS_COLLECTION, get_database
from app.schemas.complaint_case import ComplaintCase
from app.schemas.notification import (
    Notification,
    NotificationCreate,
    NotificationListResponse,
    NotificationPriority,
)

logger = logging.getLogger("cvki.notification")


class NotificationNotFoundError(LookupError):
    """The requested notification does not exist."""


class NotificationAccessDeniedError(PermissionError):
    """Authenticated user does not own this notification."""


class NotificationDatabaseError(RuntimeError):
    """The notification persistence layer is unavailable."""


class NotificationRepository:
    """Abstract interface for notification storage."""

    async def save(self, notification: Notification) -> Notification:
        raise NotImplementedError

    async def get(self, notification_id: str) -> Optional[Notification]:
        raise NotImplementedError

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        raise NotImplementedError

    async def get_unread_count(self, user_id: str) -> int:
        raise NotImplementedError

    async def mark_as_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        raise NotImplementedError

    async def mark_all_as_read(self, user_id: str) -> int:
        raise NotImplementedError


_DEFAULT_DB = object()


class MongoNotificationRepository(NotificationRepository):
    """
    MongoDB-backed notification repository.
    """

    def __init__(
        self,
        db: object = _DEFAULT_DB,
        collection_name: str = NOTIFICATIONS_COLLECTION,
    ):
        self._db = db
        self._collection_name = collection_name

    def _get_collection(self):
        db = get_database() if self._db is _DEFAULT_DB else self._db
        if db is None:
            raise NotificationDatabaseError("MongoDB persistence is unavailable.")
        return db[self._collection_name]

    async def save(self, notification: Notification) -> Notification:
        collection = self._get_collection()
        doc = notification.model_dump()
        try:
            await collection.replace_one(
                {"notification_id": notification.notification_id},
                doc,
                upsert=True,
            )
            return notification
        except PyMongoError as exc:
            logger.error("Notification persistence failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc

    async def get(self, notification_id: str) -> Optional[Notification]:
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"notification_id": notification_id})
            if doc is None:
                return None
            doc.pop("_id", None)
            return Notification(**doc)
        except PyMongoError as exc:
            logger.error("Notification lookup failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        collection = self._get_collection()
        query: dict = {"user_id": user_id}
        if unread_only:
            query["is_read"] = False

        try:
            total = await collection.count_documents(query)
            skip = (page - 1) * page_size
            cursor = (
                collection.find(query)
                .sort("created_at", -1)
                .skip(skip)
                .limit(page_size)
            )
            items: list[Notification] = []
            async for doc in cursor:
                doc.pop("_id", None)
                items.append(Notification(**doc))
            return items, total
        except PyMongoError as exc:
            logger.error("Notification list query failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc

    async def get_unread_count(self, user_id: str) -> int:
        collection = self._get_collection()
        try:
            return await collection.count_documents({"user_id": user_id, "is_read": False})
        except PyMongoError as exc:
            logger.error("Unread notification count query failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc

    async def mark_as_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"notification_id": notification_id})
            if doc is None:
                return None
            if doc.get("user_id") != user_id:
                raise NotificationAccessDeniedError("Access denied to notification belonging to another user.")

            await collection.update_one(
                {"notification_id": notification_id},
                {"$set": {"is_read": True}},
            )
            doc["is_read"] = True
            doc.pop("_id", None)
            return Notification(**doc)
        except NotificationAccessDeniedError:
            raise
        except PyMongoError as exc:
            logger.error("Notification read update failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc

    async def mark_all_as_read(self, user_id: str) -> int:
        collection = self._get_collection()
        try:
            res = await collection.update_many(
                {"user_id": user_id, "is_read": False},
                {"$set": {"is_read": True}},
            )
            return res.modified_count
        except PyMongoError as exc:
            logger.error("Bulk notification read update failed (error_type=%s).", type(exc).__name__)
            raise NotificationDatabaseError("Database service is unavailable.") from exc


class InMemoryNotificationRepository(NotificationRepository):
    """
    In-memory notification repository for fast, deterministic, dependency-free tests.
    """

    def __init__(self):
        self._notifications: dict[str, Notification] = {}
        self._lock = Lock()

    def clear(self):
        with self._lock:
            self._notifications.clear()

    async def save(self, notification: Notification) -> Notification:
        with self._lock:
            self._notifications[notification.notification_id] = notification
            return notification

    async def get(self, notification_id: str) -> Optional[Notification]:
        with self._lock:
            return self._notifications.get(notification_id)

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        with self._lock:
            user_notifs = [
                n for n in self._notifications.values()
                if n.user_id == user_id and (not unread_only or not n.is_read)
            ]
            user_notifs.sort(key=lambda n: n.created_at, reverse=True)
            total = len(user_notifs)
            start = (page - 1) * page_size
            end = start + page_size
            return user_notifs[start:end], total

    async def get_unread_count(self, user_id: str) -> int:
        with self._lock:
            return sum(
                1 for n in self._notifications.values()
                if n.user_id == user_id and not n.is_read
            )

    async def mark_as_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        with self._lock:
            notif = self._notifications.get(notification_id)
            if not notif:
                return None
            if notif.user_id != user_id:
                raise NotificationAccessDeniedError("Access denied to notification belonging to another user.")
            updated = notif.model_copy(update={"is_read": True})
            self._notifications[notification_id] = updated
            return updated

    async def mark_all_as_read(self, user_id: str) -> int:
        with self._lock:
            count = 0
            for nid, notif in list(self._notifications.items()):
                if notif.user_id == user_id and not notif.is_read:
                    self._notifications[nid] = notif.model_copy(update={"is_read": True})
                    count += 1
            return count


notification_repository: NotificationRepository = MongoNotificationRepository()


def set_notification_repository(repo: NotificationRepository) -> None:
    global notification_repository
    notification_repository = repo


def _generate_notification_id() -> str:
    return f"notif_{token_hex(8)}"


async def create_notification(req: NotificationCreate) -> Notification:
    """
    Creates and persists an in-app citizen notification.
    """
    now = datetime.now(timezone.utc)
    notification = Notification(
        notification_id=_generate_notification_id(),
        user_id=req.user_id,
        reference_id=req.reference_id,
        type=req.type,
        title=req.title,
        message=req.message,
        priority=req.priority,
        is_read=False,
        created_at=now,
        metadata=req.metadata,
        delivery_status="in_app",
    )
    res = notification_repository.save(notification)
    if inspect.isawaitable(res):
        return await res
    return res


async def list_user_notifications(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> NotificationListResponse:
    """
    Retrieves paginated notifications for the authenticated citizen, newest first.
    """
    page = min(max(1, page), 1000)
    page_size = min(max(1, page_size), 100)
    res = notification_repository.list_by_user(
        user_id=user_id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )
    if inspect.isawaitable(res):
        items, total = await res
    else:
        items, total = res

    unread_res = notification_repository.get_unread_count(user_id)
    if inspect.isawaitable(unread_res):
        unread_count = await unread_res
    else:
        unread_count = unread_res

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return NotificationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        unread_count=unread_count,
    )


async def get_user_unread_count(user_id: str) -> int:
    res = notification_repository.get_unread_count(user_id)
    if inspect.isawaitable(res):
        return await res
    return res


async def mark_notification_as_read(notification_id: str, user_id: str) -> Notification:
    res = notification_repository.mark_as_read(notification_id, user_id)
    if inspect.isawaitable(res):
        notif = await res
    else:
        notif = res

    if notif is None:
        raise NotificationNotFoundError(f"Notification '{notification_id}' was not found.")
    return notif


async def mark_all_notifications_as_read(user_id: str) -> int:
    res = notification_repository.mark_all_as_read(user_id)
    if inspect.isawaitable(res):
        return await res
    return res


def _resolve_case_priority(case: ComplaintCase) -> NotificationPriority:
    if case.priority_analysis and case.priority_analysis.priority_level in ("P1", "P2", "P3", "P4"):
        return case.priority_analysis.priority_level
    if case.issue.severity == "high":
        return "P2"
    if case.issue.severity == "medium":
        return "P3"
    return "P4"


async def trigger_case_created_notification(case: ComplaintCase) -> Optional[Notification]:
    """
    Fires automatic in-app notification when a CVKI complaint case is successfully created.
    """
    if not case.user_id:
        return None

    priority = _resolve_case_priority(case)
    return await create_notification(
        NotificationCreate(
            user_id=case.user_id,
            reference_id=case.reference_id,
            type="case_created",
            title=f"Case Created: {case.reference_id}",
            message=f"Your CVKI case {case.reference_id} has been created successfully.",
            priority=priority,
            metadata={
                "issue_class": case.issue.class_name,
                "road": case.location.road,
            },
        )
    )


async def trigger_duplicate_detected_notification(case: ComplaintCase) -> Optional[Notification]:
    """
    Fires notification when duplicate detection flags a possible duplicate or duplicate.
    """
    if not case.user_id or not case.duplicate_analysis:
        return None

    dup_status = case.duplicate_analysis.classification
    if dup_status not in ("possible_duplicate", "duplicate"):
        return None

    matched_ref = case.duplicate_analysis.matched_reference_id
    ref_desc = f"related case {matched_ref}" if matched_ref else "a nearby similar complaint"

    return await create_notification(
        NotificationCreate(
            user_id=case.user_id,
            reference_id=case.reference_id,
            type="duplicate_detected",
            title="Duplicate Report Detected",
            message=f"Your complaint matches {ref_desc}. Your submission has been preserved to aid municipal consolidation.",
            priority="P3",
            metadata={
                "classification": dup_status,
                "similarity_score": case.duplicate_analysis.similarity_score,
                "matched_reference_id": matched_ref,
            },
        )
    )


async def trigger_priority_assigned_notification(case: ComplaintCase) -> Optional[Notification]:
    """
    Fires notification when a high or critical priority (P1/P2) is assigned.
    """
    if not case.user_id or not case.priority_analysis:
        return None

    level = case.priority_analysis.priority_level
    if level not in ("P1", "P2"):
        return None

    return await create_notification(
        NotificationCreate(
            user_id=case.user_id,
            reference_id=case.reference_id,
            type="priority_assigned",
            title=f"Priority Assigned: {level}",
            message=f"Case {case.reference_id} has been evaluated as {level} ({case.priority_analysis.risk_level}).",
            priority=level,
            metadata={
                "priority_score": case.priority_analysis.priority_score,
                "priority_level": level,
                "risk_level": case.priority_analysis.risk_level,
            },
        )
    )


async def trigger_status_changed_notification(
    case: ComplaintCase,
    old_status: str,
    new_status: str,
) -> Optional[Notification]:
    """
    Fires notification when case workflow status changes.
    """
    if not case.user_id or old_status == new_status:
        return None

    return await create_notification(
        NotificationCreate(
            user_id=case.user_id,
            reference_id=case.reference_id,
            type="case_status_changed",
            title=f"Case Status Updated: {case.reference_id}",
            message=f"Status changed from '{old_status}' to '{new_status}'.",
            priority=_resolve_case_priority(case),
            metadata={
                "old_status": old_status,
                "new_status": new_status,
            },
        )
    )


async def trigger_gov_submission_prepared_notification(case: ComplaintCase) -> Optional[Notification]:
    """
    Fires notification when government submission package preparation succeeds.
    """
    if not case.user_id:
        return None

    return await create_notification(
        NotificationCreate(
            user_id=case.user_id,
            reference_id=case.reference_id,
            type="government_submission_prepared",
            title=f"Government Submission Package Prepared: {case.reference_id}",
            message=f"Dispatch package for case {case.reference_id} is prepared and ready for citizen review. Note: Not submitted to external portal yet.",
            priority=_resolve_case_priority(case),
            metadata={
                "reference_id": case.reference_id,
                "external_status": "NOT_SUBMITTED",
            },
        )
    )


async def trigger_case_assigned_notification(
    case: ComplaintCase,
    authority_user_id: str,
    assigned_by_user_id: Optional[str] = None,
) -> Optional[Notification]:
    """
    Fires notification when an admin assigns a case to an authority user.
    """
    if not authority_user_id:
        return None

    priority = _resolve_case_priority(case)
    return await create_notification(
        NotificationCreate(
            user_id=authority_user_id,
            reference_id=case.reference_id,
            type="case_assigned",
            title=f"Case Assigned: {case.reference_id}",
            message=f"Case {case.reference_id} ({case.issue.label}) has been assigned to you for operational review.",
            priority=priority,
            metadata={
                "reference_id": case.reference_id,
                "issue_class": case.issue.class_name,
                "assigned_by_user_id": assigned_by_user_id,
            },
        )
    )


async def trigger_case_unassigned_notification(
    case: ComplaintCase,
    authority_user_id: str,
    unassigned_by_user_id: Optional[str] = None,
) -> Optional[Notification]:
    """
    Fires notification when an admin unassigns a case from an authority user.
    """
    if not authority_user_id:
        return None

    priority = _resolve_case_priority(case)
    return await create_notification(
        NotificationCreate(
            user_id=authority_user_id,
            reference_id=case.reference_id,
            type="case_unassigned",
            title=f"Case Unassigned: {case.reference_id}",
            message=f"Case {case.reference_id} assignment has been removed by administration.",
            priority=priority,
            metadata={
                "reference_id": case.reference_id,
                "unassigned_by_user_id": unassigned_by_user_id,
            },
        )
    )


# Canonical alias for case status workflow notification
trigger_case_status_changed_notification = trigger_status_changed_notification
