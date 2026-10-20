"""Atomic Redis-backed rolling-window rate limits for public authentication endpoints."""
from hashlib import sha256
import logging
from functools import lru_cache
from time import time
from uuid import uuid4

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from .config import get_settings

logger = logging.getLogger(__name__)

_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count >= max_requests then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_ms = tonumber(oldest[2]) + window_ms - now_ms
    return {0, math.max(1, math.ceil(retry_ms / 1000))}
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, 0}
"""


@lru_cache(maxsize=8)
def _get_redis_client(redis_url: str) -> Redis:
    """Reuse bounded Redis connection pools across API requests."""
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )


def rate_limit(max_requests: int, window_seconds: int):
    """Build a shared per-source-IP rolling-window dependency."""
    if max_requests < 1 or window_seconds < 1:
        raise ValueError("Rate limit values must be positive")

    def enforce_limit(request: Request) -> None:
        settings = get_settings()
        if settings.environment.lower() in {"development", "test"}:
            return

        if not settings.redis_url:
            raise HTTPException(
                status_code=503,
                detail="Authentication protection is temporarily unavailable.",
                headers={"Retry-After": "5"},
            )

        client_ip = request.client.host if request.client else "unknown"
        identity = sha256(f"{request.url.path}\0{client_ip}".encode("utf-8")).hexdigest()
        key = f"campaign:auth-rate-limit:{identity}"
        now_ms = int(time() * 1000)
        try:
            allowed, retry_after = _get_redis_client(settings.redis_url).eval(
                _WINDOW_SCRIPT,
                1,
                key,
                now_ms,
                window_seconds * 1000,
                max_requests,
                f"{now_ms}:{uuid4().hex}",
            )
        except RedisError as exc:
            logger.error("Shared authentication rate limiter is unavailable: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Authentication protection is temporarily unavailable.",
                headers={"Retry-After": "5"},
            ) from exc

        if int(allowed) != 1:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )

    return enforce_limit
