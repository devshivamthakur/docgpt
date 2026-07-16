"""Multi-stage retrieval agent for the RAG pipeline.

Orchestrates a series of retrieval and re-ranking tools to gather
the most relevant context for a given query.
"""

import logging

import numpy as np

from app.schemas.conversation import SourceItem
from app.services.rag.config import RagConfig
from app.services.rag.query_processor.schemas import ProcessedQuery
from app.services.rag.retriever.helpers.cache import (
    CacheGet,
    CacheSet,
    SemanticCacheGet,
    SemanticCacheSet,
)
from app.services.rag.retriever.helpers.qdrant import QdrantSearch
from app.services.rag.retriever.helpers.reranker import Reranker

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """Agent that orchestrates retrieval using a set of tools."""

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()
        # Initialize helpers
        self.qdrant_search = QdrantSearch()
        self.reranker = Reranker(config=self.config)
        self.cache_get = CacheGet()
        self.cache_set = CacheSet()
        self.semantic_cache_get = SemanticCacheGet()
        self.semantic_cache_set = SemanticCacheSet()

    async def retrieve(
        self,
        processed_query: ProcessedQuery,
        user_id: int,
        bypass_cache: bool = False,
    ) -> list[SourceItem]:
        """Run the full multi-stage retrieval pipeline."""

        # Stage 1: Cache lookup
        if not bypass_cache:
            cached = await self.cache_get.run(processed_query.rewritten, user_id)
            if cached is not None:
                logger.debug("Retrieval cache HIT for user_id=%d", user_id)
                return cached

        # Stage 2: Semantic cache lookup
        if not bypass_cache:
            semantic_hit = await self.semantic_cache_get.run(
                processed_query.rewritten,
                user_id,
            )
            if semantic_hit is not None:
                logger.debug("Semantic retrieval cache HIT for user_id=%d", user_id)
                await self.cache_set.run(
                    processed_query.rewritten,
                    user_id,
                    semantic_hit,
                    ttl=self.config.retrieval_cache_ttl,
                )
                return semantic_hit

        # Stage 3: Initial retrieval
        sources = await self._initial_retrieval(
            queries=processed_query.all_queries(),
            user_id=user_id,
        )

        # Stage 4: Re-ranking
        if self.config.enable_reranking and len(sources) > 1:
            try:
                sources = await self.reranker.run(
                    query=processed_query.rewritten,
                    sources=sources,
                )
            except Exception:
                logger.warning("Re-ranking failed, using initial ranking")

        # Stage 5: Apply final top-k
        sources = sources[: self.config.top_k_final]

        # Stage 6: Fallback if results are weak
        if not sources or self._avg_score(sources) < self.config.min_score_threshold:
            logger.debug("Fallback triggered")
            fallback = await self._fallback_retrieval(
                processed_query.rewritten, user_id
            )
            existing_ids = {(s.document_id, s.chunk_index) for s in sources}
            for fb in fallback:
                key = (fb.document_id, fb.chunk_index)
                if key not in existing_ids:
                    sources.append(fb)
                    existing_ids.add(key)
            sources = sources[: self.config.top_k_final]

        # Stage 7: Cache results
        if sources:
            await self.cache_set.run(
                processed_query.rewritten,
                user_id,
                sources,
                ttl=self.config.retrieval_cache_ttl,
            )
            await self.semantic_cache_set.run(
                processed_query.rewritten, user_id, sources
            )

        logger.info("Retrieval complete: user_id=%d, sources=%d", user_id, len(sources))
        return sources

    async def _initial_retrieval(
        self,
        queries: list[str],
        user_id: int,
    ) -> list[SourceItem]:
        all_results: list[list[SourceItem]] = []
        for query in queries:
            try:
                results = await self.qdrant_search.run(
                    query=query,
                    user_id=user_id,
                    k=self.config.top_k_initial,
                )
                if results:
                    all_results.append(results)
            except Exception:
                logger.debug("Query '%s' failed in vector search", query[:40])

        if not all_results:
            return []

        return self._merge_results(all_results)

    async def _fallback_retrieval(
        self,
        query: str,
        user_id: int,
    ) -> list[SourceItem]:
        try:
            results = await self.qdrant_search.run(
                query=query,
                user_id=user_id,
                k=self.config.top_k_fallback,
            )
            return results
        except Exception:
            logger.exception("Fallback retrieval failed")
            return []

    @staticmethod
    def _merge_results(
        result_sets: list[list[SourceItem]],
    ) -> list[SourceItem]:
        score_map: dict[str, list[float]] = {}
        source_map: dict[str, SourceItem] = {}

        for results in result_sets:
            for src in results:
                key = f"{src.document_id}-{src.chunk_index}"
                if key not in source_map:
                    source_map[key] = src
                    score_map[key] = []
                if src.score is not None:
                    score_map[key].append(src.score)

        # Average scores and sort descending
        merged: list[SourceItem] = []
        for key, src in source_map.items():
            scores = score_map.get(key, [])
            if scores:
                src.score = round(float(np.mean(scores)), 4)
            merged.append(src)

        merged.sort(
            key=lambda x: x.score if x.score is not None else 0,
            reverse=True,
        )
        return merged

    @staticmethod
    def _avg_score(sources: list[SourceItem]) -> float:
        """Compute the average relevance score across sources."""
        scores = [s.score for s in sources if s.score is not None]
        return float(np.mean(scores)) if scores else 0.0
