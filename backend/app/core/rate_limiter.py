"""
Redis-based rate limiter with sliding-window support.

Provides:
- ``RateLimitService`` — programmatic rate-limit checks against Redis
- ``rate_limiter_service`` — singleton service instance
- ``RateLimitMiddleware`` — ASGI middleware for global baseline limiting
- ``rate_limit`` — decorator for per-endpoint rate limiting
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.constants import (
    RATE_LIMIT_AUTH_MAX,
    RATE_LIMIT_AUTH_WINDOW,
    RATE_LIMIT_CONVERSATIONS_MAX,
    RATE_LIMIT_CONVERSATIONS_WINDOW,
    RATE_LIMIT_DOCUMENTS_MAX,
    RATE_LIMIT_DOCUMENTS_WINDOW,
    RATE_LIMIT_GLOBAL_MAX,
    RATE_LIMIT_GLOBAL_WINDOW,
)

logger = logging.getLogger(__name__)


# ── Rate limit result ─────────────────────────────────────────────────


@dataclass
class RateLimitResult:
    """Result of a rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: float  # Unix timestamp
    retry_after: float = 0.0

    def to_headers(self) -> dict[str, str]:
        """Return standard rate-limit headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(math.ceil(self.reset_at)),
        }
        if not self.allowed and self.retry_after > 0:
            headers["Retry-After"] = str(math.ceil(self.retry_after))
        return headers


# ── Rate-limit rule ───────────────────────────────────────────────────


@dataclass
class RateLimitRule:
    """A single rate-limit rule.

    Attributes
    ----------
    max_requests:
        Maximum number of requests allowed in the window.
    window_seconds:
        Duration of the sliding window in seconds.
    scope:
        Logical name for this rule (used in the Redis key).
    """

    max_requests: int
    window_seconds: int
    scope: str = "global"


# ── Service ───────────────────────────────────────────────────────────


class RateLimitService:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Each unique key (e.g. ``user:42:global``) is tracked in a Redis sorted
    set where each member is a request timestamp. Old entries outside the
    window are pruned on every check, keeping memory usage low.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url: str = redis_url or settings.redis_url
        self._redis: Redis | None = None

    async def _get_client(self) -> Redis:
        if self._redis is None:
            self._redis = await Redis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check whether a request identified by *key* is within *rule*.

        Returns a ``RateLimitResult`` with the decision and metadata.
        """
        client = await self._get_client()
        now = time.time()
        window_start = now - rule.window_seconds

        redis_key = f"ratelimit:{key}:{rule.scope}"

        # Remove entries outside the current window
        await client.zremrangebyscore(redis_key, "-inf", window_start)

        # Count remaining requests
        request_count = await client.zcard(redis_key)
        remaining = max(0, rule.max_requests - request_count)
        reset_at = now + rule.window_seconds

        if request_count >= rule.max_requests:
            # Find when the oldest request expires to tell the client
            oldest = await client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = oldest[0][1] + rule.window_seconds - now if oldest else 1.0
            return RateLimitResult(
                allowed=False,
                limit=rule.max_requests,
                remaining=0,
                reset_at=reset_at,
                retry_after=max(retry_after, 1.0),
            )

        # Record this request
        await client.zadd(redis_key, {str(now): now})
        await client.expire(redis_key, rule.window_seconds)

        # Re-fetch count after inserting
        current_count = await client.zcard(redis_key)
        return RateLimitResult(
            allowed=True,
            limit=rule.max_requests,
            remaining=max(0, rule.max_requests - current_count),
            reset_at=reset_at,
        )

    async def reset(self, key: str, scope: str = "global") -> None:
        """Reset the rate-limit counter for a given key and scope."""
        client = await self._get_client()
        redis_key = f"ratelimit:{key}:{scope}"
        await client.delete(redis_key)


# Singleton — import this wherever needed
rate_limiter_service = RateLimitService()


# ── Identifier helpers ────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from the request, respecting proxies."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def build_rate_limit_key(request: Request, scope: str = "global") -> str:
    """Build a unique Redis key for the client.

    Uses the authenticated user ID when available, otherwise falls back
    to the client IP address.
    """
    user = getattr(request.state, "user", None)
    if user is not None and hasattr(user, "id"):
        return f"user:{user.id}:{scope}"
    client_ip = _get_client_ip(request)
    return f"ip:{client_ip}:{scope}"


# ── Middleware ─────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces a global baseline rate limit.

    This catches all requests (except public excluded paths) and applies
    the configured global rate limit.  It returns a **429** response with
    standard rate-limit headers when the limit is exceeded.

    The middleware runs *after* ``AuthMiddleware`` so that
    ``request.state.user`` is available for building the rate-limit key.
    """

    def __init__(
        self,
        app: ASGIApp,
        rule: RateLimitRule | None = None,
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.rule = rule or RateLimitRule(
            max_requests=RATE_LIMIT_GLOBAL_MAX,
            window_seconds=RATE_LIMIT_GLOBAL_WINDOW,
            scope="global",
        )
        self.exclude_paths: set[str] = exclude_paths or frozenset(
            {"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico", "/"}
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Skip WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        key = build_rate_limit_key(request, scope=self.rule.scope)
        result = await rate_limiter_service.check(key, self.rule)

        if not result.allowed:
            logger.warning(
                "Rate limit exceeded for %s — limit=%d window=%ds path=%s",
                key,
                self.rule.max_requests,
                self.rule.window_seconds,
                request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={"message": "Too many requests. Please try again later."},
                headers=result.to_headers(),
            )

        # Let the request through and attach rate-limit headers
        response: Response = await call_next(request)
        for header, value in result.to_headers().items():
            response.headers[header] = value
        return response


# ── Decorator ─────────────────────────────────────────────────────────


def rate_limit(
    max_requests: int = RATE_LIMIT_GLOBAL_MAX,
    window_seconds: int = RATE_LIMIT_GLOBAL_WINDOW,
    scope: str = "global",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that enforces a per-endpoint rate limit via Redis.

    Usage on a route::

        from app.core.rate_limiter import rate_limit

        @router.post("/auth/login")
        @rate_limit(max_requests=10, window_seconds=60, scope="auth")
        async def login(payload: UserLogin, ...):
            ...

    The decorator extracts the ``Request`` from the endpoint's keyword
    arguments (FastAPI injects it when the function has a ``request``
    parameter) and builds a rate-limit key from the authenticated user
    or client IP.  When the limit is exceeded it raises an
    ``HTTPException(429)`` with standard rate-limit headers.

    .. note::
        The endpoint **must** accept a ``request: Request`` parameter.
        The decorator does **not** add one automatically — add it to
        the function signature like any other FastAPI injection.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            if request is None:
                # Fallback: scan positional args for a Request instance
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None:
                logger.warning(
                    "rate_limit decorator on '%s' cannot find Request — "
                    "ensure the endpoint has a 'request: Request' parameter",
                    func.__qualname__,
                )
                return await func(*args, **kwargs)

            rule = RateLimitRule(
                max_requests=max_requests,
                window_seconds=window_seconds,
                scope=scope,
            )
            key = build_rate_limit_key(request, scope=rule.scope)
            result = await rate_limiter_service.check(key, rule)

            if not result.allowed:
                logger.warning(
                    "Rate limit exceeded for %s — limit=%d window=%ds path=%s",
                    key,
                    rule.max_requests,
                    rule.window_seconds,
                    request.url.path,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                    headers=result.to_headers(),
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ── Lifespan helper ───────────────────────────────────────────────────


async def init_rate_limiter() -> None:
    """Warm up the rate-limiter Redis connection.

    Call this during application startup if you want eager initialisation.
    """
    try:
        client = await rate_limiter_service._get_client()
        await client.ping()
        logger.info("Rate-limiter Redis connection established")
    except Exception:
        logger.exception(
            "Rate-limiter Redis connection failed — rate limiting disabled"
        )
