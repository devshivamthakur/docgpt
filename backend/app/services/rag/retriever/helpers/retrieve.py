"""LangChain ``@tool`` for the RAG retrieval agent.

This is the **only** LangChain tool exposed to the LLM.  All other
classes in this package are internal async helpers used by the
:class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import logging

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig

from app.schemas.conversation import SourceItem
from app.services.rag.config import rag_config
from app.services.rag.query_processor.processor import QueryProcessor
from app.services.rag.retriever.retrieval import RetrievalPipeline

logger = logging.getLogger(__name__)

# Module-level accumulator for source items returned by the tool.
# Cleared before each ``stream_answer`` call in the orchestrator.
_last_sources: list[SourceItem] = []


def get_last_sources() -> list[SourceItem]:
    """Return sources from the most recent tool invocation(s)."""
    return _last_sources


def clear_sources() -> None:
    """Clear the accumulated sources (call before each stream run)."""
    _last_sources.clear()


@tool
async def retrieve_documents(query: str, config: RunnableConfig) -> str:
    """Search uploaded documents for relevant context using a specific query.

    **You MUST provide a `query` parameter** — a focused search phrase derived
    from the user's question.  Do NOT call this tool without a query.

    The tool performs multi-stage retrieval — query rewriting, vector search,
    optional re-ranking, and fallback — then returns numbered source excerpts
    with document names and page numbers.

    You can call this tool **multiple times** with different queries
    to gather comprehensive context from different parts of the
    documents.
    """

    query = query.strip()
    if not query:
        return (
            "You must provide a `query` parameter. Rephrase the user's "
            "question into a focused search phrase and try again."
        )
    print(config, "config")
    user_id: int = config["configurable"]["user_id"]
    # Create fresh instances per tool call so config is always current
    retriever = RetrievalPipeline(rag_config)
    query_processor = QueryProcessor(rag_config)

    processed = await query_processor.process(query, history=[])
    sources = await retriever.retrieve(
        processed_query=processed,
        user_id=user_id,
    )

    if not sources:
        return "No relevant documents found for the query."

    _last_sources.extend(sources)
    return _format_sources(sources)


def _format_sources(sources: list[SourceItem]) -> str:
    """Format retrieved source documents into a numbered string."""
    parts: list[str] = []
    for i, src in enumerate(sources, 1):
        header = f"[Source {i}]: {src.document_name}"
        if src.page_index is not None:
            header += f" (page {src.page_index})"
        parts.append(f"{header}\n{src.content}")
    return "\n\n".join(parts)
