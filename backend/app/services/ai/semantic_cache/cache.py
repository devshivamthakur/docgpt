"""
Redis-backed semantic cache for the RAG pipeline.

Wraps ``langchain_redis.RedisSemanticCache`` to provide fast,
embedding-based semantic matching for near-identical queries.

Two caching strategies are exposed:

1. **Retrieval result caching** (``get_retrieval_result`` / ``set_retrieval_result``)
   — caches ``list[SourceItem]`` keyed by query embedding + user scope.

2. **LLM response short-circuit** (``get_llm_response`` / ``set_llm_response``)
   — caches full LLM response text so repeated questions skip the RAG pipeline.
"""

import json
import logging
from typing import Any, Optional

from langchain_core.outputs import Generation
from langchain_redis import RedisSemanticCache as RedisCache

from app.core.config import settings
from app.services.ai.llm.embedding import EmbeddingLLM

logger = logging.getLogger(__name__)


# ── Lazy import helper (avoids circular imports at module level) ──────


def _import_source_item() -> Any:
    """Dynamically import SourceItem to break circular dependency chains."""
    from app.schemas.conversation import SourceItem

    return SourceItem


# ======================================================================
# Strategy name helpers (centralised so all callers use the same prefix)
# ======================================================================


def _retrieval_llm_string(user_id: int) -> str:
    """Semantic cache ``llm_string`` for retrieval results per user."""
    return f"rag:retrieval:user_{user_id}"


def _llm_response_llm_string(model: str) -> str:
    """Semantic cache ``llm_string`` for cached LLM responses."""
    return f"rag:llm_response:{model}"


# ======================================================================
# Main singleton class
# ======================================================================


class RedisSemanticCache:
    """Singleton — central semantic cache for the RAG pipeline.

    Two usage patterns:

    **Retrieval results** (``list[SourceItem]``)::

        cache = RedisSemanticCache.get_instance()
        sources = await cache.get_retrieval_result(query, user_id)
        if sources is None:
            sources = await retriever.retrieve(...)
            await cache.set_retrieval_result(query, user_id, sources)

    **LLM response short-circuit** (plain text)::

        cached = await cache.get_llm_response(query, "gpt-4o-mini")
        if cached:
            return cached
        response = await llm.ainvoke(...)
        await cache.set_llm_response(query, "gpt-4o-mini", response)
    """

    _instance: Optional["RedisSemanticCache"] = None
    _initialized: bool = False

    def __new__(cls) -> "RedisSemanticCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = None  # type: ignore[attr-defined]
            from app.services.rag.config import rag_config

            cls._instance._config = rag_config  # type: ignore[attr-defined]
        return cls._instance

    # ──────────────────────────────────────────────────────────────────
    #  Initialisation
    # ──────────────────────────────────────────────────────────────────

    async def initialize(
        self,
        redis_url: str | None = None,
        threshold: float | None = None,
        ttl: int | None = None,
    ) -> None:
        """Create (or re-create) the underlying Redis semantic cache.

        Idempotent — subsequent calls are no-ops unless
        :meth:`reset_instance` was called.

        Args:
            redis_url: Redis connection URL. Defaults to ``settings.redis_url``.
            threshold: Cosine *distance* threshold for semantic matching.
                Defaults to ``1 - rag_config.semantic_cache_threshold``.
            ttl: Entry TTL in seconds. Defaults to ``rag_config.semantic_cache_ttl``.
        """
        if self._initialized:
            logger.debug("RedisSemanticCache already initialised — skipping.")
            return

        redis_url = redis_url or settings.redis_url
        effective_threshold = (
            threshold
            if threshold is not None
            else (1.0 - self._config.semantic_cache_threshold)
        )
        effective_ttl = ttl or self._config.semantic_cache_ttl

        try:
            logger.info(
                "Initialising Redis semantic cache at %s "
                "(distance_threshold=%.4f, ttl=%ds)",
                redis_url,
                effective_threshold,
                effective_ttl,
            )

            embedding_model = EmbeddingLLM(
                model_name=settings.HUGGINGFACE_EMBEDDING_MODEL,
            ).embedding_model

            self._cache = RedisCache(
                redis_url=redis_url,
                embeddings=embedding_model,
                distance_threshold=effective_threshold,
                ttl=effective_ttl,
                name="docgpt_semantic_cache",
                prefix="docgpt_sc",
            )
            self._initialized = True
            logger.info("Redis semantic cache is ready.")
        except Exception as e:
            logger.exception("Failed to initialise Redis semantic cache: %s", e)

    # ──────────────────────────────────────────────────────────────────
    #  Low-level public API (raw get / set)
    # ──────────────────────────────────────────────────────────────────

    async def get(self, prompt: str, llm_string: str) -> str | None:
        """Low-level lookup — returns cached text or ``None``."""
        if not self._ensure_ready():
            return None

        try:
            result = await self._cache.alookup(prompt, llm_string)
            if result and result[0].text:
                logger.debug("Semantic cache HIT for prompt: %.50s", prompt)
                return result[0].text
            logger.debug("Semantic cache MISS for prompt: %.50s", prompt)
            return None
        except Exception:
            logger.exception("Error looking up semantic cache")
            return None

    async def set(self, prompt: str, llm_string: str, response: str) -> None:
        """Low-level store."""
        if not self._ensure_ready():
            return

        try:
            generation = Generation(text=response)
            await self._cache.aupdate(prompt, llm_string, [generation])
            logger.debug("Semantic cache SET for prompt: %.50s", prompt)
        except Exception:
            logger.exception("Error updating semantic cache")

    async def clear(self) -> None:
        """Remove all entries from the semantic cache."""
        if not self._ensure_ready():
            return
        try:
            await self._cache.aclear()
            logger.info("Semantic cache cleared.")
        except Exception:
            logger.exception("Error clearing semantic cache")

    async def aclear(self) -> None:
        """Alias for :meth:`clear`."""
        await self.clear()

    # ──────────────────────────────────────────────────────────────────
    #  Strategy 1 — Retrieval result caching (SourceItem lists)
    # ──────────────────────────────────────────────────────────────────

    async def get_retrieval_result(
        self,
        query: str,
        user_id: int,
    ) -> Optional[list[Any]]:
        """Load retrieval results (``list[SourceItem]``) from semantic cache.

        Returns:
            Deserialised ``list[SourceItem]``, or ``None`` on miss / error.
        """
        cached_json = await self.get(query, _retrieval_llm_string(user_id))
        if cached_json is None:
            return None

        try:
            SourceItem = _import_source_item()
            items = json.loads(cached_json)
            return [SourceItem(**item) for item in items]
        except Exception:
            logger.debug("Failed to deserialise retrieval cache", exc_info=True)
            return None

    async def set_retrieval_result(
        self,
        query: str,
        user_id: int,
        sources: list[Any],
    ) -> None:
        """Store retrieval results in the semantic cache."""
        try:
            serialized = json.dumps(
                [s.model_dump() for s in sources],
                default=str,
            )
            await self.set(query, _retrieval_llm_string(user_id), serialized)
        except Exception:
            logger.debug("Failed to save retrieval cache", exc_info=True)

    # ──────────────────────────────────────────────────────────────────
    #  Strategy 2 — LLM response short-circuit (plain text)
    # ──────────────────────────────────────────────────────────────────

    async def get_llm_response(
        self,
        query: str,
        model: str,
    ) -> str | None:
        """Try to short-circuit the RAG pipeline with a cached LLM response.

        Returns:
            The cached response text, or ``None`` on a miss.
        """
        return await self.get(query, _llm_response_llm_string(model))

    async def set_llm_response(
        self,
        query: str,
        model: str,
        response: str,
    ) -> None:
        """Persist an LLM response for future short-circuits."""
        await self.set(query, _llm_response_llm_string(model), response)

    # ──────────────────────────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _ensure_ready(self) -> bool:
        """Check whether the cache backend is initialised; log if not."""
        if not self._initialized or self._cache is None:
            logger.warning(
                "RedisSemanticCache not initialised — call .initialize() first"
            )
            return False
        return True

    @property
    def is_initialized(self) -> bool:
        """``True`` once :meth:`initialize` has completed successfully."""
        return self._initialized and self._cache is not None

    async def ensure_initialized(self) -> bool:
        """Lazily initialise the cache if not already done.

        Safe to call anywhere — returns ``True`` if the cache is ready,
        ``False`` if initialisation failed.
        """
        if self._initialized:
            return True
        try:
            await self.initialize()
            return True
        except Exception:
            logger.warning(
                "RedisSemanticCache could not be initialised — "
                "semantic caching will be skipped"
            )
            return False

    # ──────────────────────────────────────────────────────────────────
    #  Singleton management
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "RedisSemanticCache":
        """Return the singleton instance (lazily created on first call)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (primarily for testing / teardown)."""
        if cls._instance is not None:
            cls._instance._cache = None
            cls._instance._initialized = False
        cls._instance = None
