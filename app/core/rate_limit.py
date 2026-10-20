"""Process-local rate limits for public authentication endpoints.

This is a lightweight guard for the default single-process deployment. When running
multiple API workers/replicas, use a shared gateway or distributed rate limiter too.
"""
from collections import OrderedDict, deque
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request

from .config import get_settings

_BUCKETS: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
_LOCK = Lock()
_MAX_BUCKETS = 10_000


def rate_limit(max_requests: int, window_seconds: int):
    """Build a dependency limiting requests per source IP in a rolling time window."""
    if max_requests < 1 or window_seconds < 1:
        raise ValueError("Rate limit values must be positive")

    def enforce_limit(request: Request) -> None:
        if get_settings().environment.lower() in {"development", "test"}:
            return

        client_ip = request.client.host if request.client else "unknown"
        key = (request.url.path, client_ip)
        now = monotonic()
        retry_after = None

        with _LOCK:
            attempts = _BUCKETS.get(key)
            if attempts is None:
                attempts = deque()
                _BUCKETS[key] = attempts
            _BUCKETS.move_to_end(key)

            cutoff = now - window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            if len(attempts) >= max_requests:
                retry_after = max(1, ceil(window_seconds - (now - attempts[0])))
            else:
                attempts.append(now)

            while len(_BUCKETS) > _MAX_BUCKETS:
                _BUCKETS.popitem(last=False)

        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    return enforce_limit
