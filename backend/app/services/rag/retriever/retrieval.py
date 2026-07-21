"""Multi-stage retrieval agent for the RAG pipeline.

Orchestrates a series of retrieval and re-ranking tools to gather
the most relevant context for a given query.

Improvements over v1:
- **RRF fusion** instead of max-score for multi-query merging
- **Cross-encoder re-ranking** (enabled by default) for precision
- **Document-level diversity** to avoid same-document saturation
- **Adaptive fallback** — tries alternative query variants when scores are low

Fusion strategies (v2):
- **DBSF** (default) — Distribution-Based Score Fusion via Qdrant prefetch API
- **RRF** — Reciprocal Rank Fusion (rank-based, Qdrant's legacy default)
- **Weighted** — explicit weighted combination of dense + sparse scores
  with min-max normalisation
"""

from __future__ import annotations

import asyncio
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
        """Run the full multi-stage retrieval pipeline.

        Stages:
          1. Parallel cache lookup (exact + semantic)
          2. Initial hybrid retrieval across all query variations
          3. RRF fusion of multi-query results
          4. Cross-encoder re-ranking (if enabled)
          5. Document-level diversity filter
          6. Adaptive fallback if scores are poor
          7. Semantic cache write-back
        """

        # Stage 1: Parallel cache lookups (exact + semantic)
        if not bypass_cache:
            cache_hit, semantic_hit = await self._parallel_cache_lookup(
                processed_query.rewritten, user_id
            )
            if cache_hit is not None:
                logger.debug("Exact cache HIT for user_id=%d", user_id)
                return cache_hit
            if semantic_hit is not None:
                logger.debug("Semantic cache HIT for user_id=%d", user_id)
                # Promote to exact cache for future identical queries
                await self.cache_set.run(
                    processed_query.rewritten,
                    user_id,
                    semantic_hit,
                    ttl=self.config.retrieval_cache_ttl,
                )
                return semantic_hit

        # Stage 2: Initial hybrid retrieval across all query variations
        sources = await self._initial_retrieval(
            queries=processed_query.all_queries(),
            user_id=user_id,
        )
        logger.info(
            "Initial retrieval: %d candidates for query '%.40s'",
            len(sources),
            processed_query.rewritten,
        )

        # Stage 3: Re-ranking (cross-encoder)
        if self.config.enable_reranking and len(sources) > 1:
            try:
                sources = await self.reranker.run(
                    query=processed_query.rewritten,
                    sources=sources,
                )
            except Exception:
                logger.warning("Re-ranking failed, using initial ranking")

        # Stage 4: Document-level diversity filter
        if self.config.enable_diversity and len(sources) > 1:
            sources = self._apply_diversity(sources)

        # Stage 5: Apply final top-k
        sources = sources[: self.config.top_k_final]

        # # Stage 6: Adaptive fallback check (only if results are poor)
        # should_fallback = await self._should_fallback(
        #     sources, processed_query, user_id
        # )

        # if should_fallback:
        #     fallback = await self._fallback_retrieval(
        #         processed_query, user_id
        #     )
        #     sources = self._merge_fallback(sources, fallback)

        # Stage 7: Cache results
        if sources:
            await self.semantic_cache_set.run(
                processed_query.rewritten, user_id, sources
            )

        logger.info(
            "Retrieval complete: user_id=%d, final_sources=%d",
            user_id,
            len(sources),
        )
        return sources

    # ── Cache ───────────────────────────────────────────────────────────

    async def _parallel_cache_lookup(
        self,
        query: str,
        user_id: int,
    ) -> tuple[list[SourceItem] | None, list[SourceItem] | None]:
        """Check exact-match and semantic caches in parallel."""
        exact_task = self.cache_get.run(query, user_id)
        semantic_task = self.semantic_cache_get.run(query, user_id)

        exact_result, semantic_result = await asyncio.gather(
            exact_task, semantic_task, return_exceptions=False
        )
        return exact_result, semantic_result

    # ── Initial Retrieval ──────────────────────────────────────────────

    async def _initial_retrieval(
        self,
        queries: list[str],
        user_id: int,
    ) -> list[SourceItem]:
        """Parallel Qdrant searches for every query variation.

        Results from each query are fused via **RRF** (Reciprocal Rank Fusion)
        which is more robust than score-based merging when different queries
        produce scores on different scales.
        """
        # Deduplicate queries while preserving order
        seen: set[str] = set()
        unique_queries: list[str] = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        if not unique_queries:
            return []

        semaphore = asyncio.Semaphore(self.config.max_concurrent_qdrant_queries)

        async def _search(query: str) -> list[SourceItem]:
            async with semaphore:
                return await self.qdrant_search.run(
                    query=query,
                    user_id=user_id,
                    k=self.config.top_k_initial,
                    fusion_strategy=self.config.fusion_strategy,
                    dense_weight=self.config.dense_weight,
                    sparse_weight=self.config.sparse_weight,
                    rrf_k=self.config.rrf_k,
                )

        tasks = [_search(q) for q in unique_queries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        valid_sets: list[list[SourceItem]] = []
        for i, r in enumerate(results_list):
            if isinstance(r, list) and r:
                valid_sets.append(r)
            elif isinstance(r, Exception):
                logger.debug(
                    "Query '%.40s' failed: %s", unique_queries[i][:40], str(r)
                )

        if not valid_sets:
            return []

        # Multi-query fusion via RRF — boosts documents that rank high
        # across multiple query variations (e.g. rewritten + expanded).
        return self._rrf_merge(valid_sets, k=self.config.rrf_k)

    # ── Reciprocal Rank Fusion ─────────────────────────────────────────

    @staticmethod
    def _rrf_merge(
        result_sets: list[list[SourceItem]],
        k: int = 60,
    ) -> list[SourceItem]:
        """Reciprocal Rank Fusion — robust multi-query result fusion.

        Each result's RRF score is ``Σ 1 / (k + rank)`` across all result
        sets.  This avoids score-scale issues and naturally boosts documents
        that appear high in multiple result lists.

        Args:
            result_sets: One ranked list of SourceItems per query variation.
            k: RRF constant.  Higher values dilute the rank advantage
               (default 60 per the original paper; Qdrant uses 20).

        Returns:
            Sources sorted by descending RRF score.
        """
        rrf_scores: dict[str, float] = {}
        source_map: dict[str, SourceItem] = {}

        for results in result_sets:
            for rank, src in enumerate(results, start=1):
                key = f"{src.id}-{src.chunk_index}"
                if key not in source_map:
                    source_map[key] = src
                rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)

        merged: list[SourceItem] = []
        for key, src in source_map.items():
            src.score = round(float(rrf_scores.get(key, 0.0)), 4)
            merged.append(src)

        merged.sort(
            key=lambda x: x.score if x.score is not None else 0.0,
            reverse=True,
        )
        return merged

    # ── Diversity ──────────────────────────────────────────────────────

    def _apply_diversity(self, sources: list[SourceItem]) -> list[SourceItem]:
        """Limit chunks per document to ensure diverse evidence.

        Preserves the highest-scored chunk(s) from each document.
        """
        doc_count: dict[int, int] = {}
        diverse: list[SourceItem] = []

        for src in sources:
            doc_id = src.document_id
            count = doc_count.get(doc_id, 0)
            if count < self.config.max_chunks_per_document:
                diverse.append(src)
                doc_count[doc_id] = count + 1
            else:
                logger.debug(
                    "Diversity: skipped chunk %d from doc %s (limit=%d)",
                    src.chunk_index,
                    src.document_name,
                    self.config.max_chunks_per_document,
                )

        return diverse

    # ── Fallback ────────────────────────────────────────────────────────

    async def _should_fallback(
        self,
        sources: list[SourceItem],
        processed_query: ProcessedQuery,
        user_id: int,
    ) -> bool:
        """Decide whether to trigger the fallback retrieval path."""
        if not sources:
            return True

        avg_score = self._avg_score(sources)
        if avg_score < self.config.min_score_threshold:
            logger.debug(
                "Fallback triggered (avg_score=%.3f < %.2f)",
                avg_score,
                self.config.min_score_threshold,
            )
            return True

        # Also fall back if we have too few unique documents
        unique_docs = {s.document_id for s in sources}
        if len(unique_docs) <= 1 and len(sources) >= 3:
            logger.debug(
                "Fallback triggered: all %d sources from a single document",
                len(sources),
            )
            return True

        return False

    async def _fallback_retrieval(
        self,
        processed_query: ProcessedQuery,
        user_id: int,
    ) -> list[SourceItem]:
        """Adaptive fallback retrieval.

        Tries multiple strategies to find better results in parallel:
        1. Original normalised query (broader than rewritten)
        2. If the original query differs from rewritten, try original
        """
        queries_to_try: list[str] = [processed_query.normalised]

        # If the original query has more keywords, try it too
        original = processed_query.original.strip()
        if original and original.lower() != processed_query.normalised.lower():
            queries_to_try.append(original)

        # Deduplicate fallback queries
        queries_to_try = list(dict.fromkeys(queries_to_try))

        async def _run_fallback(query: str) -> list[SourceItem]:
            try:
                return await self.qdrant_search.run(
                    query=query,
                    user_id=user_id,
                    k=self.config.top_k_fallback,
                    fusion_strategy=self.config.fusion_strategy,
                    dense_weight=self.config.dense_weight,
                    sparse_weight=self.config.sparse_weight,
                    rrf_k=self.config.rrf_k,
                )
            except Exception:
                logger.debug("Fallback query '%.40s' failed", query[:40])
                return []

        # Run all fallback searches in parallel
        tasks = [_run_fallback(q) for q in queries_to_try]
        results_list = await asyncio.gather(*tasks)

        all_fallback: list[SourceItem] = []
        seen_keys: set[str] = set()

        for results in results_list:
            for src in results:
                key = f"{src.id}-{src.chunk_index}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_fallback.append(src)

        return all_fallback

    @staticmethod
    def _merge_fallback(
        primary: list[SourceItem],
        fallback: list[SourceItem],
    ) -> list[SourceItem]:
        """Merge fallback results into primary, deduplicating by (id, chunk)."""
        existing_keys = {(s.id, s.chunk_index) for s in primary}
        merged = list(primary)
        for fb in fallback:
            key = (fb.id, fb.chunk_index)
            if key not in existing_keys:
                existing_keys.add(key)
                merged.append(fb)
        return merged

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _avg_score(sources: list[SourceItem]) -> float:
        """Compute the average relevance score across sources."""
        scores = [s.score for s in sources if s.score is not None]
        return float(np.mean(scores)) if scores else 0.0


