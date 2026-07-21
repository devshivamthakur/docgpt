"""Qdrant vector-search helper for the retrieval pipeline.

Supports multiple fusion strategies for combining dense and sparse
search results:
  - **RRF** (Reciprocal Rank Fusion) — rank-based, Qdrant's default.
  - **DBSF** (Distribution-Based Score Fusion) — score-normalised,
    generally more accurate when scores are well-calibrated.
  - **Weighted** — explicit linear combination of dense + sparse scores.

This class is **not** a LangChain tool — it is an internal building
block used by :class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import asyncio
import logging

from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Prefetch,
    QueryResponse,
    RrfQuery,
    ScoredPoint,
    SparseVector as QdrantSparseVector,
)

from app.schemas.conversation import SourceItem
from app.services.ai.embedding.qdrant import get_qdrant, get_qdrant_service
from app.services.rag.retriever.helpers.base import RetrievalHelper

logger = logging.getLogger(__name__)

# ── Batch-size presets ──────────────────────────────────────────────────

_DEFAULT_K = 10
"""Default number of results to fetch when *k* is not specified."""


class QdrantSearch(RetrievalHelper):
    """Hybrid (dense + sparse) vector search against Qdrant.

    Executes a similarity search on the Qdrant collection, filtering
    results to the given ``user_id`` for scoped access.

    Supports multiple fusion strategies — DBSF, RRF, and weighted —
    for combining dense and sparse retrieval signals.
    """

    async def run(
        self,
        query: str,
        user_id: int,
        k: int = _DEFAULT_K,
        fusion_strategy: str = "dbsf",
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> list[SourceItem]:
        """Search for the *k* most relevant document chunks for *query*.

        Args:
            query: The search query string.
            user_id: Scope results to this user.
            k: Number of results to return.
            fusion_strategy: One of ``"rrf"``, ``"dbsf"``, or ``"weighted"``.
            dense_weight: Weight for dense scores (weighted fusion only).
            sparse_weight: Weight for sparse scores (weighted fusion only).
            rrf_k: RRF smoothing constant.

        Returns:
            List of ``SourceItem`` sorted by descending relevance.
        """
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        )

        if fusion_strategy == "weighted":
            return await self._weighted_search(
                query=query,
                user_id=user_id,
                k=k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                filter_condition=qdrant_filter,
            )

        # RRF and DBSF use the same prefetch-based path with different FusionQuery
        if fusion_strategy == "rrf":
            query_obj: FusionQuery | RrfQuery = RrfQuery(rrf={"k": rrf_k})
        else:
            query_obj = FusionQuery(fusion=Fusion.DBSF)

        return await self._prefetch_search(
            query=query,
            k=k,
            query_obj=query_obj,
            filter_condition=qdrant_filter,
        )

    # ── DBSF / RRF (Prefetch-based) ────────────────────────────────────

    async def _prefetch_search(
        self,
        query: str,
        k: int,
        query_obj: FusionQuery | RrfQuery,
        filter_condition: Filter,
    ) -> list[SourceItem]:
        """Search using Qdrant's ``query_points`` with prefetch (dense + sparse).

        Each modality (dense, sparse) fetches ``fetch_k`` candidates, then
        Qdrant's fusion step combines them and returns the top ``k`` results.
        Using more candidates per modality gives the fusion step better
        material to work with, improving result quality.

        Falls back to the langchain vector-store hybrid search if the
        direct client call fails (e.g. older Qdrant version).
        """
        svc = get_qdrant_service()
        embedder = svc.embadding_model
        sparse_embedder = svc.sparse_embeddings

        try:
            # Embed query (use async to avoid blocking the event loop)
            dense_vector, sparse_raw = await asyncio.gather(
    embedder.aembed_query(query),
    sparse_embedder.aembed_query(query),
)
            sparse_vector = QdrantSparseVector(
                indices=sparse_raw.indices, values=sparse_raw.values
            )

            # Fetch extra candidates per modality — gives the fusion step
            # more high-quality material.  The top-level limit=k trims
            # back down to the desired count after fusion.
            fetch_k = max(k * 2, 50)

            prefetch = [
                Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=fetch_k,
                    filter=filter_condition,
                ),
                Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=fetch_k,
                    filter=filter_condition,
                ),
            ]

            response: QueryResponse = svc.client.query_points(
                collection_name=svc.collection_name,
                prefetch=prefetch,
                query=query_obj,
                limit=k,
                with_payload=True,
                with_vectors=False,
            )

            return self._scored_points_to_sources(response.points)

        except Exception as exc:
            logger.warning(
                "Direct Qdrant query_points call failed (%s), "
                "falling back to langchain hybrid search: %s",
                type(exc).__name__,
                exc,
            )
            return await self._langchain_hybrid_search(
                query=query,
                k=k,
                filter_condition=filter_condition,
            )

    # ── Weighted Fusion ────────────────────────────────────────────────

    async def _weighted_search(
        self,
        query: str,
        user_id: int,
        k: int,
        dense_weight: float,
        sparse_weight: float,
        filter_condition: Filter,
    ) -> list[SourceItem]:
        """Run separate dense and sparse searches, then fuse via weighted sum.

        This lets you explicitly control the contribution of each modality.
        """
        svc = get_qdrant_service()
        embedder = svc.embadding_model
        sparse_embedder = svc.sparse_embeddings

        try:
            dense_vector = await embedder.aembed_query(query)
            sparse_raw = await sparse_embedder.aembed_query(query)
            sparse_vector = QdrantSparseVector(
                indices=sparse_raw.indices, values=sparse_raw.values
            )

            # Fetch extra candidates so the weighted merge has enough to pick from
            fetch_k = max(k * 2, 50)

            # Dense search
            dense_response = svc.client.query_points(
                collection_name=svc.collection_name,
                query=dense_vector,
                using="dense",
                limit=fetch_k,
                with_payload=True,
                with_vectors=False,
                query_filter=filter_condition,
            )

            # Sparse search
            sparse_response = svc.client.query_points(
                collection_name=svc.collection_name,
                query=sparse_vector,
                using="sparse",
                limit=fetch_k,
                with_payload=True,
                with_vectors=False,
                query_filter=filter_condition,
            )

            return self._weighted_fusion(
                dense_points=dense_response.points,
                sparse_points=sparse_response.points,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                top_k=k,
            )

        except Exception as exc:
            logger.warning(
                "Weighted search via Qdrant client failed (%s), "
                "falling back to langchain hybrid search: %s",
                type(exc).__name__,
                exc,
            )
            return await self._langchain_hybrid_search(
                query=query,
                k=k,
                filter_condition=filter_condition,
            )

    @staticmethod
    def _weighted_fusion(
        dense_points: list[ScoredPoint],
        sparse_points: list[ScoredPoint],
        dense_weight: float,
        sparse_weight: float,
        top_k: int,
    ) -> list[SourceItem]:
        """Fuse dense and sparse results via weighted linear combination.

        Scores from each modality are *min-max normalised* before fusion
        to account for different score scales.
        """
        # Build score maps keyed by point ID
        dense_scores = {p.id: p.score for p in dense_points}
        sparse_scores = {p.id: p.score for p in sparse_points}

        if not dense_scores and not sparse_scores:
            return []

        all_ids = set(dense_scores) | set(sparse_scores)

        # Min-max normalise each score set
        def _normalise(
            scores: dict, id_set: set
        ) -> dict:
            values = [scores[i] for i in id_set if i in scores]
            if not values:
                return {}
            mn, mx = min(values), max(values)
            if mx == mn:
                return {i: 0.5 for i in id_set if i in scores}
            return {
                i: (scores[i] - mn) / (mx - mn)
                for i in id_set
                if i in scores
            }

        norm_dense = _normalise(dense_scores, all_ids)
        norm_sparse = _normalise(sparse_scores, all_ids)

        # Weighted fusion
        fused: dict[int, float] = {}
        for pid in all_ids:
            d = norm_dense.get(pid, 0.0)
            s = norm_sparse.get(pid, 0.0)
            fused[pid] = d * dense_weight + s * sparse_weight

        # Merge metadata (use whichever point has a payload)
        point_map: dict[int, ScoredPoint] = {
            p.id: p for p in dense_points
        }
        for p in sparse_points:
            if p.id not in point_map or not p.payload:
                point_map[p.id] = p

        # Sort by fused score
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        sources: list[SourceItem] = []
        for pid, score in ranked:
            point = point_map.get(pid)
            if point is None or not point.payload:
                continue
            sources.append(
                _point_to_source_item(point, round(float(score), 4))
            )
        return sources

    # ── LangChain Fallback ─────────────────────────────────────────────

    async def _langchain_hybrid_search(
        self,
        query: str,
        k: int,
        filter_condition: Filter,
    ) -> list[SourceItem]:
        """Fallback using langchain's ``asimilarity_search_with_relevance_scores``."""
        try:
            results = await get_qdrant().asimilarity_search_with_relevance_scores(
                query,
                k=k,
                filter=filter_condition,
            )
        except (NotImplementedError, AttributeError):
            results = await get_qdrant().asimilarity_search_with_score(
                query,
                k=k,
                filter=filter_condition,
            )

        sources: list[SourceItem] = []
        for doc, score in results:
            meta = doc.metadata or {}
            sources.append(
                SourceItem(
                    id=meta.get("_id"),
                    document_id=meta.get("document_id", 0),
                    document_name=meta.get("file", "Unknown document"),
                    page_index=meta.get("page_index"),
                    chunk_index=meta.get("chunk_index"),
                    content=doc.page_content,
                    score=round(float(score), 4) if score is not None else None,
                )
            )
        return sources

    # ── Response Parsing ───────────────────────────────────────────────

    @staticmethod
    def _scored_points_to_sources(
        points: list[ScoredPoint],
    ) -> list[SourceItem]:
        """Convert raw ``ScoredPoint`` list to ``SourceItem`` list."""
        sources: list[SourceItem] = []
        for pt in points:
            if not pt.payload:
                continue
            sources.append(_point_to_source_item(pt, pt.score))
        return sources


# ── Standalone helpers ──────────────────────────────────────────────────


def _point_to_source_item(
    point: ScoredPoint,
    score: float | None,
) -> SourceItem:
    """Convert a ``ScoredPoint`` to a ``SourceItem``.

    Payload structure (from langchain-qdrant ``add_documents``):
      ``page_content`` (str), ``metadata`` (dict), ``_id`` (str|UUID).
    """
    payload = point.payload or {}
    meta = payload.get("metadata") or {}

    # The point ID (UUID from Qdrant) doubles as ``_id``
    raw_id = payload.get("_id") or point.id

    if isinstance(raw_id, str):
        try:
            from uuid import UUID
            parsed_id = UUID(raw_id)
        except (ValueError, AttributeError):
            parsed_id = raw_id
    else:
        parsed_id = raw_id

    return SourceItem(
        id=parsed_id,
        document_id=meta.get("document_id", 0),
        document_name=meta.get("file", "Unknown document"),
        page_index=meta.get("page_index"),
        chunk_index=meta.get("chunk_index"),
        content=payload.get("page_content", ""),
        score=round(float(score), 4) if score is not None else None,
    )
