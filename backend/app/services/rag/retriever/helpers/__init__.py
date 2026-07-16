"""Retrieval helper classes and the LangChain ``@tool``.

* :func:`retrieve_documents` — the **only** LangChain tool in this
  package, exposed to the LLM for dynamic document retrieval.
* :func:`get_last_sources` / :func:`clear_sources` — module-level
  source tracking used by the orchestrator after streaming.

* All other classes are internal async helpers used by the
  :class:`~app.services.rag.retriever.retrieval.RetrievalAgent` and are **not**
  exposed to the LLM.
"""

from .cache import CacheGet, CacheSet, SemanticCacheGet, SemanticCacheSet
from .qdrant import QdrantSearch
from .reranker import Reranker


__all__ = [
    # LangChain @tool (exposed to the LLM)
    "get_last_sources",
    "clear_sources",
    # Internal async helpers (used by RetrievalAgent, not the LLM)
    "CacheGet",
    "CacheSet",
    "SemanticCacheGet",
    "SemanticCacheSet",
    "QdrantSearch",
    "Reranker",
]
