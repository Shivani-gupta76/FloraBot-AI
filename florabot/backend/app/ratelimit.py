import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

TOO_MANY_REQUESTS = "You're sending requests too quickly. Please wait a minute and try again."


class RateLimiter:
    """Allows at most `limit` requests per client in any rolling window."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True


def rate_limit(name: str):
    """Dependency that rejects a client once it exceeds the named limiter on app.state.rate_limiters."""

    def check(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not request.app.state.rate_limiters[name].allow(client):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_REQUESTS)

    return check
