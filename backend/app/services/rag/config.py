"""RAG pipeline configuration — all tuning knobs in one place."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RagConfig:
    """Central configuration for the RAG pipeline.

    All values can be overridden via ``RagConfig(**{...}.model_dump())``
    when integrating with ``pydantic-settings``.
    """

    # ── Retrieval ──────────────────────────────────────────────────────
    top_k_initial: int = 10
    """How many candidates to fetch from the vector store before re-ranking."""

    top_k_final: int = 5
    """How many results to keep after re-ranking."""

    top_k_fallback: int = 3
    """How many results when using relaxed fallback retrieval."""

    min_score_threshold: float = 0.25
    """Minimum relevance score to consider a result valid."""

    enable_hybrid_search: bool = True
    """Whether to combine dense + sparse retrieval (hybrid mode)."""

    enable_reranking: bool = True
    """Whether to apply a cross-encoder re-ranker after initial retrieval."""

    reranking_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    """Cross-encoder model for re-ranking (used if ``enable_reranking`` is True)."""

    # ── Query Processing ───────────────────────────────────────────────
    enable_query_rewriting: bool = True
    """Whether to rewrite the user query before retrieval."""

    enable_query_expansion: bool = False
    """Whether to expand the query with generated sub-questions (HyDE-light)."""

    query_rewrite_model: str | None = None
    """Model name for query rewriting (falls back to the main LLM)."""

    # ── Context Window ─────────────────────────────────────────────────
    max_context_chars: int = 12_000
    """Maximum characters for the retrieved context section of the prompt."""

    max_history_chars: int = 4_000
    """Maximum characters for the conversation history section."""

    max_history_messages: int = 10
    """How many recent messages to include in the prompt."""

    context_truncation_strategy: Literal["head", "tail", "middle"] = "tail"
    """Which part of the context to truncate when it exceeds ``max_context_chars``."""

    # ── Agent ──────────────────────────────────────────────────────────
    agent_recursion_limit: int = 50
    """Maximum LangGraph recursion steps for the agent loop.

    Each tool call + LLM response consumes one step.  Increase this
    if the agent needs to make many tool calls before answering.
    Default LangGraph is 25.
    """

    # ── Streaming ──────────────────────────────────────────────────────
    stream_chunk_timeout: float = 30.0
    """Maximum seconds to wait between consecutive stream chunks."""

    stream_total_timeout: float = 120.0
    """Maximum total seconds for the entire stream response."""

    # ── Caching ────────────────────────────────────────────────────────
    retrieval_cache_ttl: int = 300
    """TTL in seconds for cached retrieval results (per normalised query)."""

    semantic_cache_ttl: int = 600
    """TTL for semantic cache entries (exact/near-exact query matches)."""

    semantic_cache_threshold: float = 0.92
    """Cosine similarity threshold for semantic cache hits."""

    # ── Vector Store ───────────────────────────────────────────────────
    qdrant_collection_name: str = "doc_gpt_collection"
    """Qdrant collection name."""

    qdrant_timeout_sec: float = 30.0
    """Timeout for Qdrant operations."""

    qdrant_max_retries: int = 3
    """How many times to retry a failed Qdrant operation."""

    qdrant_batch_size: int = 64
    """Batch size for indexing documents into Qdrant."""

    # ── Embedding ──────────────────────────────────────────────────────
    embedding_batch_size: int = 32
    """How many texts to embed in a single batch call."""

    embedding_cache_ttl: int = 3600
    """TTL for cached embeddings (keys are text hashes)."""

    # ── Summary ────────────────────────────────────────────────────────
    enable_auto_summary: bool = True
    """Whether to generate conversation summaries in the background."""

    summary_model: str | None = None
    """Model for summary generation (None = same as main LLM)."""

    # ── Observability ──────────────────────────────────────────────────
    enable_metrics: bool = True
    """Whether to emit duration / counter metrics for pipeline stages."""

    enable_tracing: bool = False
    """Whether to enable OpenTelemetry-style tracing spans."""


# Mutable global that services import — update at app startup if needed
rag_config = RagConfig()
