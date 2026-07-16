"""
Async Redis caching service and decorator.

Provides a `CacheService` class for direct programmatic access and a
``@cached`` decorator that can be applied to FastAPI endpoint functions
(or any async function) to cache their return values.

Usage (endpoint decorator)::

    from app.core.redis_cache import cached

    @router.get("/items")
    @cached(ttl=60)
    async def list_items(db: AsyncSession = Depends(get_db)):
        ...

Usage (programmatic)::

    from app.core.redis_cache import cache_service

    await cache_service.set("my-key", {"data": 42})
    value = await cache_service.get("my-key")
    await cache_service.invalidate("my-key")

Cache keys are auto-generated from the function name + positional args +
keyword args, so different arguments produce different cache entries.
"""

import hashlib
import inspect
import json
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import redis.asyncio as aioredis
from redis.asyncio.lock import Lock
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# ── Serialisation helpers ─────────────────────────────────────────────
import asyncio
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def _default_serialiser(obj: Any) -> Any:
    """Extend JSON serialisation to Pydantic models and common types."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()
    if isinstance(obj, DeclarativeBase):
        # Convert SQLAlchemy model to a dictionary
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    # SQLAlchemy internal state objects — skip them
    if type(obj).__name__ in ("InstanceState", "DeclarativeAttributeIntercept"):
        return str(obj)
    # Common non-serialisable types
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: _default_serialiser(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_default_serialiser(v) for v in obj]
    if hasattr(obj, "__dict__"):
        # Recursively clean the dict to avoid embedded non-serialisable objects
        return _default_serialiser(obj.__dict__)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


# ── Cache service ─────────────────────────────────────────────────────


class CacheService:
    """Async Redis cache wrapper with common operations.

    The underlying Redis client is created lazily on first use and cached
    for the lifetime of the service instance.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url: str = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._default_ttl: int = 300  # 5 minutes
        self._lock_timeout = 10  # seconds to lock for revalidation

    # ── Connection management ───────────────────────────────────────

    async def _get_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def get_lock(self, key: str) -> Lock:
        """Get a Redis lock for a given key."""
        client = await self._get_client()
        return client.lock(f"lock:{key}", timeout=self._lock_timeout)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    # ── Core operations ─────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached value by key. Returns ``None`` when missing."""
        client = await self._get_client()
        try:
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.exception("Cache GET error for key '%s'", key)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Store a value in the cache with a timestamp.

        The value is stored in a JSON object ``{"data": ..., "timestamp": ...}``
        to support stale-while-revalidate logic.

        Args:
            key: Cache key.
            value: Any JSON-serialisable value.
            ttl: Time-to-live in seconds. Falls back to ``_default_ttl``.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        client = await self._get_client()
        try:
            payload = {
                "data": value,
                "timestamp": time.time(),
            }
            serialised = json.dumps(payload, default=_default_serialiser)
            return await client.setex(key, ttl or self._default_ttl, serialised)
        except Exception:
            logger.exception("Cache SET error for key '%s'", key)
            return False

    async def delete(self, key: str) -> bool:
        """Remove a single key from the cache."""
        client = await self._get_client()
        try:
            deleted = await client.delete(key)
            return deleted > 0
        except Exception:
            logger.exception("Cache DELETE error for key '%s'", key)
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Remove all keys matching a glob pattern (e.g. ``"documents:list:*"``).

        Returns the number of deleted keys.
        """
        client = await self._get_client()
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted += await client.delete(*keys)
                if cursor == 0:
                    break
            return deleted
        except Exception:
            logger.exception("Cache CLEAR error for pattern '%s'", pattern)
            return 0


# Singleton — import this wherever needed
cache_service = CacheService()


# ── Cache key builders ────────────────────────────────────────────────


def _make_cache_key(
    func: Callable, args: tuple, kwargs: dict, prefix: str | None = None
) -> str:
    """Generate a deterministic cache key from function metadata + arguments.

    The key includes the module and function name so there are no collisions
    across different endpoints.

    ``current_user`` is handled specially: its ``id`` is included both
    in the hash and as a separate path segment in the key so that each user
    gets their own cache entry and per-user cache invalidation is possible.
    Key format: ``<prefix>:<user_id>:<hash>`` (or ``<prefix>:<hash>`` if
    no user context). Other DI-only parameters such as ``db``, ``request``,
    ``response``, and ``session`` are excluded.
    """
    module = inspect.getmodule(func)
    module_name = module.__name__ if module else "unknown"
    func_path = f"{module_name}.{func.__qualname__}"

    # Build a stable representation of args/kwargs for the hash
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    # Remove common dependency-injection parameters that don't affect the result
    skip_params = {"db", "request", "response", "session"}
    args_dict: dict[str, Any] = {}
    user_id: int | None = None
    for k, v in bound.arguments.items():
        if k in skip_params:
            continue
        if k == "current_user":
            # Include user ID so each user has their own cache entry
            uid = getattr(v, "id", None)
            args_dict["user_id"] = uid
            user_id = uid
        else:
            args_dict[k] = v

    # Hash the serialised args to keep keys short
    raw = json.dumps(args_dict, sort_keys=True, default=str)
    arg_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    prefix_str = prefix or func.__name__
    if user_id is not None:
        return f"{prefix_str}:{user_id}:{arg_hash}"
    return f"{prefix_str}:{arg_hash}"


# Custom key function type — users can pass their own
CacheKeyFn = Callable[..., str]


# ── Decorator ─────────────────────────────────────────────────────────


def cached(
    ttl: int = 300,
    soft_ttl: int | None = None,
    prefix: str | None = None,
    key_builder: CacheKeyFn | None = None,
    condition: Callable[..., bool] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that caches the return value of an async function in Redis.

    Implements a "stale-while-revalidate" strategy if ``soft_ttl`` is set.

    Parameters
    ----------
    ttl:
        The "hard" time-to-live in seconds. After this time, the cache entry
        is considered expired and will be removed. Default is 300 (5 minutes).
    soft_ttl:
        The "soft" time-to-live in seconds. If the cached data is older than
        this, it's considered "stale". The stale data will be returned, but a
        background refresh will be triggered. Must be less than ``ttl``.
    prefix:
        Optional override for the cache-key prefix. Defaults to the function name.
    key_builder:
        Optional custom callable that receives ``(func, args, kwargs)`` and
        returns a cache key string. When provided, ``prefix`` is ignored.
    condition:
        Optional callable that receives the same arguments as the decorated
        function and returns ``True`` if caching should be attempted.

    Usage::

        @router.get("/documents")
        @cached(ttl=3600, soft_ttl=60)
        async def list_documents(...):
            ...

    The cache is automatically bypassed when the function raises an exception.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            use_soft_ttl = soft_ttl is not None and soft_ttl < ttl

            # ── Check condition ────────────────────────────────────
            if condition is not None and not condition(*args, **kwargs):
                logger.debug(
                    "Cache condition not met for %s — skipping", func.__qualname__
                )
                return await func(*args, **kwargs)

            # ── Build key ──────────────────────────────────────────
            if key_builder is not None:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _make_cache_key(func, args, kwargs, prefix=prefix)

            # ── Try cache hit ──────────────────────────────────────
            cached_payload = await cache_service.get(cache_key)

            if cached_payload is not None:
                cached_data = cached_payload.get("data")
                timestamp = cached_payload.get("timestamp", 0)
                age = time.time() - timestamp

                # Fresh hit
                if not use_soft_ttl or age <= soft_ttl:
                    logger.debug("Cache HIT for key '%s'", cache_key)
                    return cached_data

                # Stale hit — return stale data and revalidate in background
                logger.debug("Cache STALE for key '%s'. Revalidating.", cache_key)
                lock = await cache_service.get_lock(cache_key)
                if await lock.acquire(blocking=False):
                    try:
                        # Got lock, do the refresh
                        asyncio.create_task(
                            _revalidate_cache(func, args, kwargs, cache_key, ttl)
                        )
                    finally:
                        # asyncio.create_task(lock.release()) is not safe,
                        # but we can let it expire naturally.
                        pass
                return cached_data

            logger.debug("Cache MISS for key '%s'", cache_key)

            # ── Execute function and cache result ──────────────────
            result = await func(*args, **kwargs)
            await _set_cache(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


async def _revalidate_cache(
    func: Callable[P, R],
    args: P.args,
    kwargs: P.kwargs,
    cache_key: str,
    ttl: int,
) -> None:
    """Execute a function and cache its result."""
    try:
        logger.debug("Revalidating cache for key '%s'...", cache_key)
        result = await func(*args, **kwargs)
        await _set_cache(cache_key, result, ttl)
        logger.info("Cache revalidated for key '%s'", cache_key)
    except Exception:
        logger.exception("Error revalidating cache for key '%s'", cache_key)


async def _set_cache(cache_key: str, result: Any, ttl: int) -> None:
    """Helper to serialise and cache a result by delegating to ``cache_service.set``.

    ``cache_service.set`` internally calls ``json.dumps`` with the
    ``_default_serialiser``, which already knows how to handle Pydantic
    models, SQLAlchemy ORM models (``DeclarativeBase``), and other common
    types.  No pre-conversion is needed here.
    """
    await cache_service.set(cache_key, result, ttl=ttl)


# ── Convenience invalidator helpers ───────────────────────────────────


async def invalidate_document_caches(user_id: int | None = None) -> None:
    """Invalidate document-related cache entries for a specific user (or all users).

    Should be called after any document write operation (upload / delete).
    """
    if user_id is not None:
        await cache_service.clear_pattern(f"list_documents:{user_id}:*")
        await cache_service.clear_pattern(f"get_document:{user_id}:*")
    else:
        await cache_service.clear_pattern("list_documents:*")
        await cache_service.clear_pattern("get_document:*")
    logger.info("Invalidated document caches (user=%s)", user_id)


async def invalidate_user_caches(user_id: int | None = None) -> None:
    """Invalidate user-related cache entries for a specific user (or all users)."""
    if user_id is not None:
        await cache_service.clear_pattern(f"get_me:{user_id}:*")
    else:
        await cache_service.clear_pattern("get_me:*")
    logger.info("Invalidated user caches (user=%s)", user_id)


async def invalidate_conversation_caches(user_id: int | None = None) -> None:
    """Invalidate conversation-related cache entries for a specific user (or all users).

    Should be called after any conversation write operation (create / delete / send message).
    """
    if user_id is not None:
        await cache_service.clear_pattern(f"list_conversations:{user_id}:*")
        await cache_service.clear_pattern(f"get_conversation:{user_id}:*")
    else:
        await cache_service.clear_pattern("list_conversations:*")
        await cache_service.clear_pattern("get_conversation:*")
    logger.info("Invalidated conversation caches (user=%s)", user_id)
