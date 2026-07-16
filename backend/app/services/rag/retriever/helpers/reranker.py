"""Cross-encoder re-ranker helper for the retrieval pipeline.

This class is **not** a LangChain tool — it is an internal building
block used by :class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.schemas.conversation import SourceItem
from app.services.rag.config import RagConfig

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder re-ranker for improving retrieval precision.

    Lazy-loads a ``sentence_transformers.CrossEncoder`` model on first
    use. Falls back to the original ordering when the model is
    unavailable or re-ranking fails.
    """

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()
        self._model: Any | None = None

    async def run(
        self,
        query: str,
        sources: list[SourceItem],
    ) -> list[SourceItem]:
        """Re-rank *sources* by relevance to *query* using a cross-encoder."""
        if not sources:
            return sources

        model = await self._get_model()
        if model is None:
            return sources

        try:
            pairs = [(query, src.content) for src in sources]
            scores = model.predict(pairs)
            scores = np.array(scores).flatten()

            scored = [
                (src, float(scores[i]))
                for i, src in enumerate(sources)
                if i < len(scores)
            ]
            scored.sort(key=lambda x: x[1], reverse=True)

            for src, score in scored:
                src.score = round(score, 4)

            return [src for src, _ in scored]
        except Exception:
            logger.warning("Cross-encoder re-ranking failed, using original order")
            return sources

    async def _get_model(self) -> Any | None:
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder

            model_name = self.config.reranking_model
            logger.info("Loading cross-encoder re-ranker: %s", model_name)
            self._model = CrossEncoder(model_name)
            return self._model
        except ImportError:
            logger.warning("sentence-transformers not installed — re-ranking disabled")
            return None
        except Exception:
            logger.exception("Failed to load cross-encoder re-ranker")
            return None
