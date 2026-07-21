"""Retrieval helper classes and the LangChain ``@tool``.

* :func:`retrieve_documents` — the **only** LangChain tool in this
  package, exposed to the LLM for dynamic document retrieval.
* :class:`SourceTracker` — explicit per-run source collection used by the
  orchestrator after streaming.

* All other classes are internal async helpers used by the
  :class:`~app.services.rag.retriever.retrieval.RetrievalAgent` and are **not**
  exposed to the LLM.
"""

from app.services.rag.source_tracking import SourceTracker

from .cache import CacheGet, CacheSet, SemanticCacheGet, SemanticCacheSet
from .qdrant import QdrantSearch
from .reranker import Reranker


__all__ = [
    # LangChain @tool (exposed to the LLM)
    "SourceTracker",
    # Internal async helpers (used by RetrievalAgent, not the LLM)
    "CacheGet",
    "CacheSet",
    "SemanticCacheGet",
    "SemanticCacheSet",
    "QdrantSearch",
    "Reranker",
]
