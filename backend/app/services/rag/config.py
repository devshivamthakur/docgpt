"""RAG pipeline configuration — all tuning knobs in one place."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class RagConfig:
    """Central configuration for the RAG pipeline.

    All values can be overridden via ``RagConfig(**{...}.model_dump())``
    when integrating with ``pydantic-settings``.
    """

    # ── Retrieval ──────────────────────────────────────────────────────
    top_k_initial: int = 25
    """How many candidates to fetch from the vector store before re-ranking.
    
    Set higher than ``top_k_final`` to give the cross-encoder reranker enough
    candidates to pick from.  25—30 is a good range for most use cases.
    """

    top_k_final: int = 7
    """How many results to keep after re-ranking."""

    top_k_fallback: int = 5
    """How many results when using relaxed fallback retrieval."""

    min_score_threshold: float = 0.30
    """Minimum relevance score to consider a result valid.
    
    Increased from 0.25 to reduce low-quality results entering the context.
    """

    # ── Fusion Strategy ────────────────────────────────────────────────
    fusion_strategy: Literal["rrf", "dbsf", "weighted"] = "dbsf"
    """How to fuse dense and sparse results in hybrid search.
    
    - ``"rrf"``: Reciprocal Rank Fusion — rank-based, robust when score
      scales differ between dense and sparse.  Qdrant's default.
    - ``"dbsf"``: Distribution-Based Score Fusion — normalises score
      distributions before fusing.  Usually more accurate than RRF when
      scores are well-calibrated.
    - ``"weighted"``: Weighted linear combination — lets you explicitly
      control dense vs. sparse importance via ``dense_weight`` /
      ``sparse_weight``.
    """

    dense_weight: float = 0.65
    """Weight for dense vector scores when ``fusion_strategy="weighted"``.
    
    Increase (e.g. 0.8—0.9) for semantically focused queries; decrease
    (e.g. 0.4—0.5) for keyword/factual lookups.
    """

    sparse_weight: float = 0.35
    """Weight for sparse (BM25) vector scores when ``fusion_strategy="weighted"``."""

    rrf_k: int = 60
    """RRF constant for reciprocal rank fusion (both Qdrant-level and pipeline-level).
    
    Higher values dilute the impact of rank position, giving more weight to
    documents appearing across multiple result sets.  Qdrant's default is 20;
    the original paper recommends 60 for multi-query fusion.
    """

    # ── Re-ranking ─────────────────────────────────────────────────────
    enable_reranking: bool = True
    """Whether to apply a cross-encoder re-ranker after initial retrieval.
    
    Improves precision by 15—30 %.  Requires ``top_k_initial > top_k_final``
    to be effective.
    """
    minimum_reranking_score: float = 0.8

    reranking_model: str = "Xenova/ms-marco-MiniLM-L-12-v2"
    """Cross-encoder model for re-ranking (used if ``enable_reranking`` is True)."""

    # ── Query Processing ───────────────────────────────────────────────
    enable_query_rewriting: bool = False
    """Whether to rewrite the user query before retrieval."""

    enable_query_expansion: bool = False
    """Whether to expand the query with generated sub-questions (HyDE-light).
    
    Generates a hypothetical document chunk via LLM to improve recall for
    complex or multi-faceted queries.
    """

    query_rewrite_model: str | None = None
    """Model name for query rewriting (falls back to the main LLM)."""

    # ── Diversity ──────────────────────────────────────────────────────
    enable_diversity: bool = False
    """Whether to apply document-level diversity to avoid same-document saturation.
    
    Limits the number of chunks from a single source document in the final
    result set so the LLM sees a broader range of evidence.
    """

    max_chunks_per_document: int = 2
    """Maximum number of chunks from the same document in the final result."""

    diversity_sim_threshold: float = 0.85
    """Similarity threshold for considering two chunks as near-duplicate.
    
    Used by the diversity filter to remove redundant chunks.
    """

    # ── Context Window ─────────────────────────────────────────────────
    max_context_chars: int = 16_000
    """Maximum characters for the retrieved context section of the prompt.
    
    Increased to 16k to accommodate larger chunks (1 000 chars × 10 sources
    ≈ 10 000 chars content + formatting overhead).
    """

    max_history_chars: int = 4_000
    """Maximum characters for the conversation history section."""

    max_history_messages: int = 10
    """How many recent messages to include in the prompt."""

    context_truncation_strategy: Literal["head", "tail", "middle"] = "middle"
    """Which part of the context to truncate when it exceeds ``max_context_chars``.
    
    Changed from ``tail`` to ``middle`` — dropping the middle preserves
    the beginning (most relevant sources) and end (recency bias) of the
    context window.
    """

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

    # ── Performance Tuning ─────────────────────────────────────────────
    max_concurrent_qdrant_queries: int = 8
    """Maximum number of Qdrant searches to run in parallel per retrieve() call.
    
    Increased to 8 to handle additional query variations from HyDE expansion
    without adding latency.  Adjust based on your Qdrant server capacity.
    """

    cache_lookup_parallel: bool = True
    """Whether to check exact-match and semantic caches in parallel."""

    enable_query_deduplication: bool = True
    """Whether to deduplicate query variations before Qdrant search."""

    early_exit_score_threshold: float | None = None
    """If set, skip fallback retrieval if avg score >= this threshold.
    
    Set to None to disable early exit (always run fallback).
    Set to 0.5 for aggressive early exit.
    """

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
