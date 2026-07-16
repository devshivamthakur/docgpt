"""Semantic caching for the RAG pipeline.

Uses embeddings to detect near-identical queries and return cached
responses, avoiding redundant LLM calls and retrieval operations.
"""

from app.services.ai.semantic_cache.cache import RedisSemanticCache

__all__ = [
    "RedisSemanticCache",
]
