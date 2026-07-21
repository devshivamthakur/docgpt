"""Cross-encoder re-ranker helper for the retrieval pipeline.

This class is **not** a LangChain tool — it is an internal building
block used by :class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import asyncio
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
    _model: Any | None = None
    _model_name: str | None = None

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()

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
            contents = [src.content for src in sources]
            # Run the CPU-bound reranking operation and consume the generator in a thread pool to avoid blocking the event loop
            raw_scores = await asyncio.to_thread(lambda: list(model.rerank(query, contents)))

            # Apply sigmoid to normalize raw logit scores to [0, 1] range for correct frontend percentage display
            import math
            def safe_sigmoid(x: float) -> float:
                if x >= 0:
                    return 1.0 / (1.0 + math.exp(-x))
                else:
                    z = math.exp(x)
                    return z / (1.0 + z)

            scores = [safe_sigmoid(float(s)) for s in raw_scores]
            ranking = [(i, score) for i, score in enumerate(scores)]
            ranking.sort(key=lambda x: x[1], reverse=True)
            logger.debug("Cross-encoder ranking scores: %s", ranking)

            reordered: list[SourceItem] = []
            for i, score in ranking:
                sources[i].score = round(score, 4)
                reordered.append(sources[i])

            return reordered
        except Exception:
            logger.warning("Cross-encoder re-ranking failed, using original order")
            return sources

    async def _get_model(self) -> Any | None:
        """Lazy-load the cross-encoder model."""
        if Reranker._model is not None and Reranker._model_name == self.config.reranking_model:
            return Reranker._model

        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            model_name = self.config.reranking_model
            logger.info("Loading cross-encoder re-ranker: %s", model_name)
            # Run model initialization in thread pool because loading weights can take a while and blocks the event loop
            Reranker._model = await asyncio.to_thread(TextCrossEncoder, model_name)
            Reranker._model_name = model_name
            return Reranker._model
        except ImportError:
            logger.warning("sentence-transformers not installed — re-ranking disabled")
            return None
        except Exception:
            logger.exception("Failed to load cross-encoder re-ranker")
            return None

# if __name__ == "__main__":
#     import asyncio

#     async def main():
#         output = TextCrossEncoder.list_supported_models()
#         print(output)

#     asyncio.run(main())