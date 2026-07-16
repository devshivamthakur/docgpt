"""Qdrant vector-search helper for the retrieval pipeline.

This class is **not** a LangChain tool — it is an internal building
block used by :class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import logging

from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.schemas.conversation import SourceItem
from app.services.ai.embedding.qdrant import get_qdrant
from app.services.rag.retriever.helpers.base import RetrievalHelper

logger = logging.getLogger(__name__)

# ── Batch-size presets ──────────────────────────────────────────────────

_DEFAULT_K = 10
"""Default number of results to fetch when *k* is not specified."""


class QdrantSearch(RetrievalHelper):
    """Hybrid (dense + sparse) vector search against Qdrant.

    Executes a similarity search on the Qdrant collection, filtering
    results to the given ``user_id`` for scoped access.

    Supports ``asimilarity_search_with_relevance_scores`` with a fallback
    to ``asimilarity_search_with_score`` for broader compatibility.
    """

    async def run(
        self,
        query: str,
        user_id: int,
        k: int = _DEFAULT_K,
    ) -> list[SourceItem]:
        """Search for the *k* most relevant document chunks for *query*.

        Results are scoped to *user_id* and deduplicated by
        ``(document_id, chunk_index)``.
        """
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        )

        sources: list[SourceItem] = []
        seen: set[str] = set()

        try:
            results = await get_qdrant().asimilarity_search_with_relevance_scores(
                query,
                k=k,
                filter=qdrant_filter,
            )
        except NotImplementedError, AttributeError:
            results = await get_qdrant().asimilarity_search_with_score(
                query,
                k=k,
                filter=qdrant_filter,
            )

        for doc, score in results:
            meta = doc.metadata or {}
            doc_id = meta.get("document_id", 0)
            chunk_idx = meta.get("chunk_index")
            key = f"{doc_id}-{chunk_idx}"

            if key in seen:
                continue
            seen.add(key)

            sources.append(
                SourceItem(
                    document_id=doc_id,
                    document_name=meta.get("file", "Unknown document"),
                    page_index=meta.get("page_index"),
                    chunk_index=chunk_idx,
                    content=doc.page_content[:500],
                    score=round(float(score), 4) if score is not None else None,
                )
            )
        return sources
