"""Reusable Redis fixed-window rate limiter as a FastAPI dependency.

Generalises the per-IP limiter that already guards public microsites. Coarse but
enough to stop floods/brute force; swap for a sliding window or slowapi if finer
control is ever needed. Always fails OPEN on a Redis hiccup — a limiter outage must
never take down the endpoint it protects.
"""
import logging
from fastapi import Request, HTTPException, status
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


def rate_limiter(bucket: str, limit: int, window_seconds: int = 60):
    """Build a dependency that allows `limit` requests per `window_seconds` per IP."""
    def _dep(request: Request) -> None:
        ip = _client_ip(request)
        try:
            r = get_redis()
            key = f"ratelimit:{bucket}:{ip}"
            count = r.incr(key)
            if count == 1:
                r.expire(key, window_seconds)
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Rate limit check failed (bucket=%s), allowing request: %s", bucket, e)
    return _dep
