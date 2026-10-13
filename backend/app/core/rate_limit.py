from collections import OrderedDict
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Process-local fixed-window limiter for low-cost abuse protection."""

    _MAX_BUCKETS = 10_000

    def __init__(self) -> None:
        self._buckets: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def check(
        self,
        *,
        scope: str,
        client_key: str,
        limit: int,
        window_seconds: int,
    ) -> int | None:
        now = monotonic()
        key = (scope, client_key)
        with self._lock:
            expired = [
                bucket_key
                for bucket_key, (window_start, _) in self._buckets.items()
                if now - window_start >= window_seconds
            ]
            for bucket_key in expired:
                self._buckets.pop(bucket_key, None)

            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= window_seconds:
                window_start, count = now, 0

            if count >= limit:
                self._buckets.move_to_end(key)
                return max(1, int(window_seconds - (now - window_start)))

            self._buckets[key] = (window_start, count + 1)
            self._buckets.move_to_end(key)
            while len(self._buckets) > self._MAX_BUCKETS:
                self._buckets.popitem(last=False)
        return None

    def reset(self) -> None:
        """Clears buckets for deterministic tests and controlled local use."""
        with self._lock:
            self._buckets.clear()


rate_limiter = InMemoryRateLimiter()


def rate_limit_dependency(
    *,
    scope: str,
    limit: int,
    window_seconds: int,
):
    async def enforce_rate_limit(request: Request) -> None:
        client = request.client
        client_key = client.host if client is not None else "unknown"
        retry_after = rate_limiter.check(
            scope=scope,
            client_key=client_key,
            limit=limit,
            window_seconds=window_seconds,
        )
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    return enforce_rate_limit
