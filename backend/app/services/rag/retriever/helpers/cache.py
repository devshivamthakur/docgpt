"""Cache helpers for the retrieval pipeline.

Provides four internal async helpers used by
:class:`~app.services.rag.retriever.retrieval.RetrievalAgent`:

* :class:`CacheGet` / :class:`CacheSet` — exact-match Redis caching
  (via ``app.core.redis_cache.cache_service``).

* :class:`SemanticCacheGet` / :class:`SemanticCacheSet` — embedding-based
  semantic caching (via ``app.services.ai.semantic_cache.RedisSemanticCache``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.schemas.conversation import SourceItem

logger = logging.getLogger(__name__)


# ── Cache key helpers ─────────────────────────────────────────────────


def _retrieval_cache_key(query: str, user_id: int) -> str:
    """Return a deterministic Redis key for exact-match caching."""
    query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
    return f"rag:retrieval:{user_id}:{query_hash}"


# ── Exact-match cache helpers (Redis via cache_service) ──────────────


class CacheGet:
    """Exact-match retrieval cache lookup.

    Reads previously cached :class:`SourceItem` lists from Redis.
    """

    async def run(self, query: str, user_id: int) -> list[SourceItem] | None:
        """Return cached results for *query* scoped to *user_id*, or ``None``."""
        try:
            from app.core.redis_cache import cache_service

            key = _retrieval_cache_key(query, user_id)
            raw: dict[str, Any] | None = await cache_service.get(key)
            if raw is None:
                return None

            data = raw.get("data")
            if data is None:
                return None

            return [SourceItem(**item) for item in data]
        except Exception:
            logger.exception("CacheGet failed for user_id=%d", user_id)
            return None


class CacheSet:
    """Exact-match retrieval cache store.

    Persists :class:`SourceItem` lists to Redis with configurable TTL.
    """

    async def run(
        self,
        query: str,
        user_id: int,
        sources: list[SourceItem],
        ttl: int = 300,
    ) -> None:
        """Cache *sources* for *query* scoped to *user_id*."""
        try:
            from app.core.redis_cache import cache_service

            key = _retrieval_cache_key(query, user_id)
            serialisable = [s.model_dump() for s in sources]
            await cache_service.set(key, serialisable, ttl=ttl)
        except Exception:
            logger.exception("CacheSet failed for user_id=%d", user_id)


# ── Semantic cache helpers (embedding-based via RedisSemanticCache) ──


class SemanticCacheGet:
    """Semantic (embedding-based) retrieval cache lookup.

    Delegates to :class:`app.services.ai.semantic_cache.RedisSemanticCache`
    to find near-matching queries.
    """

    async def run(self, query: str, user_id: int) -> list[SourceItem] | None:
        """Return semantically cached results for *query*, or ``None``."""
        try:
            from app.services.ai.semantic_cache import RedisSemanticCache

            cache = RedisSemanticCache.get_instance()
            if not await cache.ensure_initialized():
                return None

            result = await cache.get_retrieval_result(query, user_id)
            return result  # type: ignore[return-value]
        except Exception:
            logger.exception("SemanticCacheGet failed for user_id=%d", user_id)
            return None


class SemanticCacheSet:
    """Semantic (embedding-based) retrieval cache store.

    Delegates to :class:`app.services.ai.semantic_cache.RedisSemanticCache`
    to persist results keyed by query embedding.
    """

    async def run(
        self,
        query: str,
        user_id: int,
        sources: list[SourceItem],
    ) -> None:
        """Cache *sources* in the semantic cache for *query*."""
        try:
            from app.services.ai.semantic_cache import RedisSemanticCache

            cache = RedisSemanticCache.get_instance()
            if not await cache.ensure_initialized():
                return

            await cache.set_retrieval_result(query, user_id, sources)
        except Exception:
            logger.exception("SemanticCacheSet failed for user_id=%d", user_id)
