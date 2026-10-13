from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status


def validate_iso_date_range(
    created_from: Optional[str],
    created_to: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    parsed: list[datetime | None] = []
    for field_name, value in (("created_from", created_from), ("created_to", created_to)):
        if value is None:
            parsed.append(None)
            continue
        try:
            parsed.append(datetime.fromisoformat(value.replace(" ", "+").replace("Z", "+00:00")))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field_name} must be a valid ISO 8601 date or datetime.",
            ) from exc

    start, end = parsed
    if start is not None and end is not None:
        start_compare = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_compare = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        if start_compare > end_compare:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="created_from must not be later than created_to.",
            )

    return (
        start.isoformat() if start is not None else None,
        end.isoformat() if end is not None else None,
    )
