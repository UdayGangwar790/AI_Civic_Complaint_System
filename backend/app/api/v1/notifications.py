from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.schemas.notification import (
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationListResponse,
    UnreadCountResponse,
)
from app.services.notification import (
    NotificationAccessDeniedError,
    NotificationDatabaseError,
    NotificationNotFoundError,
    get_user_unread_count,
    list_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)

router = APIRouter()


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List authenticated user's notifications",
)
async def get_notifications(
    page: int = Query(default=1, ge=1, le=1000, description="Page number (1-indexed, max 1000)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    unread_only: bool = Query(default=False, description="Filter only unread notifications"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> NotificationListResponse:
    try:
        return await list_user_notifications(
            user_id=current_user.user_id,
            page=page,
            page_size=page_size,
            unread_only=unread_only,
        )
    except NotificationDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get count of unread notifications",
)
async def get_unread_count_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UnreadCountResponse:
    try:
        count = await get_user_unread_count(current_user.user_id)
        return UnreadCountResponse(unread_count=count)
    except NotificationDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.post(
    "/{notification_id}/read",
    response_model=MarkReadResponse,
    summary="Mark single notification as read",
)
async def mark_one_as_read(
    notification_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MarkReadResponse:
    try:
        updated = await mark_notification_as_read(
            notification_id=notification_id,
            user_id=current_user.user_id,
        )
        return MarkReadResponse(success=True, notification=updated)
    except NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found.",
        )
    except NotificationAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this notification.",
        )
    except NotificationDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    summary="Mark all user notifications as read",
)
async def mark_all_as_read_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MarkAllReadResponse:
    try:
        count = await mark_all_notifications_as_read(current_user.user_id)
        return MarkAllReadResponse(success=True, updated_count=count)
    except NotificationDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )
