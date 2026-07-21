"""LangChain ``@tool`` for the RAG retrieval agent.

This is the **only** LangChain tool exposed to the LLM.  All other
classes in this package are internal async helpers used by the
:class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

import logging

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.conversation import SourceItem
from app.services.document_service import DocumentService
from app.services.rag.config import rag_config
from app.services.rag.query_processor.processor import QueryProcessor
from app.services.rag.retriever.retrieval import RetrievalPipeline
from app.services.rag.source_tracking import SourceTracker

logger = logging.getLogger(__name__)


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
    configurable = (config or {}).get("configurable") or {}
    user_id: int = configurable.get("user_id")
    if user_id is None:
        raise KeyError("configurable.user_id is required")
    history = configurable.get("history", [])
    tracker: SourceTracker | None = configurable.get("source_tracker")
    # Create fresh instances per tool call so config is always current
    retriever = RetrievalPipeline(rag_config)
    query_processor = QueryProcessor(rag_config)

    processed = await query_processor.process(query, history=history)
    sources = await retriever.retrieve(
        processed_query=processed,
        user_id=user_id,
    )

    if not sources:
        return "No relevant documents found for the query."

    if tracker is not None:
        tracker.add_sources(sources)
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


@tool
async def list_uploaded_documents(config: RunnableConfig) -> str:
    """List all the documents that the user has uploaded to DocGPT.

    Use this tool whenever the user asks for a list of their uploaded files,
    documents, or wants to know what files are currently available in their account.
    """
    user_id: int = config["configurable"]["user_id"]
    db: AsyncSession | None = config["configurable"].get("db")

    if db is not None:
        service = DocumentService(db)
        documents, total = await service.list_documents(
            user_id=user_id, skip=0, limit=100
        )
    else:
        from app.db.session import SessionLocal

        async with SessionLocal() as session:
            service = DocumentService(session)
            documents, total = await service.list_documents(
                user_id=user_id, skip=0, limit=100
            )

    if not documents:
        return "You have not uploaded any documents yet."

    doc_list = []
    for doc in documents:
        doc_list.append(f"- {doc.original_filename} (Status: {doc.status})")

    return "Here is the list of your uploaded documents:\n" + "\n".join(doc_list)
