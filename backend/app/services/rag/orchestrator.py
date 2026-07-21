"""Orchestration layer — ties together retrieval, prompt building, LLM streaming,
citation extraction, and background summary generation into a single RAG pipeline.

This is the primary entry point consumed by the API layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.Prompt.AgentPrompt import build_agent_system_prompt
from app.core.config import settings
from app.core.constants import PROVIDER_OPENAI
from app.core.langfuse import build_langfuse_config
from app.models.conversation import Message
from app.schemas.conversation import SourceItem
from app.services.ai.llm.agent import create_rag_agent
from app.services.ai.llm.models import LLM
from app.services.ai.semantic_cache.cache import RedisSemanticCache
from app.services.conversation_service import ConversationService
from app.services.rag.config import RagConfig, rag_config
from app.services.rag.Tools.tools import tools
from app.services.rag.streaming import StreamManager, StreamTimeoutError
from app.services.rag.citation import CitationExtractor
from app.services.rag.prompt.builder import PromptBuilder
from app.services.rag.source_tracking import SourceTracker
from app.services.rag.query_processor.processor import QueryProcessor
from app.services.rag.retriever.retrieval import RetrievalPipeline
from app.services.rag.utils import extract_chunk_content


logger = logging.getLogger(__name__)


class RagOrchestrator:
    """Production-grade RAG orchestrator.

    Pipeline::

        QueryProcessor ──→ Retriever ──→ PromptBuilder ──→ LLM ──→ CitationExtractor
            (rewrite)        (hybrid         (assemble        (stream        (extract
             +expand)    search + rerank)    prompt)       tokens)        sources)

    Each stage is independently testable and configurable via ``RagConfig``.
    """

    def __init__(
        self,
        config: RagConfig | None = None,
    ):
        self.config = config or rag_config
        # Lazy initialisation — components are created on first use
        self._llm: LLM | None = None
        self._summary_llm: LLM | None = None
        self._query_processor: QueryProcessor | None = None
        self._retriever: RetrievalPipeline | None = None
        self._prompt_builder: PromptBuilder | None = None
        self._citation_extractor: CitationExtractor | None = None

    # ── Property accessors with lazy init ──────────────────────────────

    @property
    def llm(self) -> Any:
        """Main LLM for answer generation."""
        if self._llm is None:
            self._llm = LLM(
                temperature=0.3,
                provider=settings.model_provider,
                streaming=True,
                model_name=settings.GEMINI_CHAT_MODEL,
            ).llm
        return self._llm

    @property
    def summary_llm(self) -> Any:
        """LLM for summary generation (can be a faster/cheaper model)."""
        if self._summary_llm is None:
            model = (
                self.config.summary_model or settings.OPENAI_MODEL_NAME or "gpt-4o-mini"
            )
            self._summary_llm = LLM(
                model_name=model,
                temperature=0.3,
                provider=PROVIDER_OPENAI,
            ).llm
        return self._summary_llm

    @property
    def query_processor(self) -> QueryProcessor:
        if self._query_processor is None:
            self._query_processor = QueryProcessor(self.config)
        return self._query_processor

    @property
    def retriever(self) -> RetrievalPipeline:
        """Lazy-load the retriever instance."""
        if self._retriever is None:
            self._retriever = RetrievalPipeline(self.config)
        return self._retriever

    @property
    def prompt_builder(self) -> PromptBuilder:
        if self._prompt_builder is None:
            self._prompt_builder = PromptBuilder(self.config)
        return self._prompt_builder

    @property
    def citation_extractor(self) -> CitationExtractor:
        if self._citation_extractor is None:
            self._citation_extractor = CitationExtractor()
        return self._citation_extractor

    # ── Langfuse helper ────────────────────────────────────────────────

    @staticmethod
    def _build_llm_config(
        user_id: int,
        conversation_id: uuid.UUID,
        trace_name: str = "rag_call",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a LangChain ``config`` dict with Langfuse tracing.

        Returns an empty dict (no tracing) when Langfuse is not
        configured, so callers can safely pass the result to
        ``llm.astream(…, config=…)`` without extra conditionals.
        """
        return build_langfuse_config(
            user_id=user_id,
            session_id=str(conversation_id),
            trace_name=trace_name,
            tags=(tags or []) + ["rag"],
        )

    # ── Main entry point: full RAG pipeline ────────────────────────────

    async def stream_answer(
        self,
        query: str,
        user_id: int,
        conversation_id: uuid.UUID,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """Enhanced RAG pipeline — v2 with full control over the streaming loop.

        This version collects the full content internally so we can perform
        citation extraction after streaming completes, then yields the
        structured SSE events in the correct order.

        Note: sanitization is already performed by the API layer
        (``_prepare_stream``), so we skip it here to avoid redundant work.
        """

        # ── Step 0: Semantic cache short-circuit (Strategy 1) ─────────
        llm_model = settings.selected_model
        cached_answer = await self._try_llm_short_circuit(query, llm_model)
        # if cached_answer is not None:
        #     logger.info(
        #         "Semantic cache HIT for conv_id=%s — skipping RAG pipeline",
        #         conversation_id,
        #     )
        #     yield StreamManager.sources_event([])
        #     yield StreamManager.done_event(cached_answer, [])
        #     # Still persist the Q&A pair in the background
        #     from app.services.rag.tasks import store_messages_task

        #     asyncio.create_task(
        #         store_messages_task(
        #             conversation_id=conversation_id,
        #             user_id=user_id,
        #             user_message=query,
        #             assistant_content=cached_answer,
        #             sources=[],
        #         )
        #     )
        #     return

        # ── Step 1: Load conversation context ─────────────────────────
        history, summary = await self._load_conversation_context(
            conversation_id,
            user_id,
            db,
        )

        # ── Step 2: Build Langfuse tracing config ─────────────────────
        langfuse_config = self._build_llm_config(
            user_id=user_id,
            conversation_id=conversation_id,
            trace_name="rag_answer",
            tags=["rag", "streaming"],
        )

        # ── Step 3: Create agent with retrieval tool and stream ──────
        full_content = ""
        start_time = time.monotonic()
        last_token_time = start_time
        source_tracker = SourceTracker()

        try:
            # Build system prompt with conversation summary
            system_prompt = build_agent_system_prompt(summary)

            # Build input messages from conversation history + current query
            messages: list = []
            for msg in history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
            messages.append(HumanMessage(content=query))

            # Create the agent via langchain's create_agent API
            agent_graph = create_rag_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
                name="rag_agent",
            )

            # Track whether the current model invocation is generating
            # tool calls vs. final answer content
            has_tool_calls = False

            # Inject user_id, db, and history into RunnableConfig so the @tool can read it
            run_config = {
                **langfuse_config,
                "recursion_limit": self.config.agent_recursion_limit,
                "configurable": {
                    **(langfuse_config.get("configurable") or {}),
                    "user_id": user_id,
                    "db": db,
                    "history": history,
                    "source_tracker": source_tracker,
                },
            }

            async for event in agent_graph.astream_events(
                {"messages": messages},
                version="v2",
                config=run_config,
            ):
                # ── Timeout checks ──
                now = time.monotonic()
                if now - last_token_time > self.config.stream_chunk_timeout:
                    raise StreamTimeoutError(
                        f"Stream stalled for {(now - last_token_time):.1f}s "
                        f"(timeout={self.config.stream_chunk_timeout}s)"
                    )
                if now - start_time > self.config.stream_total_timeout:
                    raise StreamTimeoutError(
                        f"Stream exceeded total timeout of "
                        f"{self.config.stream_total_timeout}s"
                    )

                event_type = event["event"]

                # Reset on each model invocation
                if event_type == "on_chat_model_start":
                    has_tool_calls = False

                # Stream tokens from the model — skip chunks that are
                # part of tool-call generation (those contain JSON, not
                # the final answer)
                elif event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if getattr(chunk, "tool_call_chunks", None):
                        has_tool_calls = True
                    if not has_tool_calls:
                        content = extract_chunk_content(getattr(chunk, "content", None))
                        if content:
                            full_content += content
                            last_token_time = now
                            yield StreamManager._sse_event(
                                "token", {"content": content}
                            )

                elif event_type == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output and not has_tool_calls:
                        msg = None
                        if hasattr(output, "generations"):
                            try:
                                msg = output.generations[0].message
                            except IndexError, AttributeError:
                                pass
                        elif hasattr(output, "content"):
                            msg = output

                        if msg:
                            content = extract_chunk_content(
                                getattr(msg, "content", None)
                            )
                            if content and not full_content:
                                full_content = content
                                last_token_time = now
                                yield StreamManager._sse_event(
                                    "token", {"content": content}
                                )

                # Log tool usage for observability
                elif event_type == "on_tool_start":
                    tool_input = event["data"]
                    logger.debug(
                        "Agent calling tool=%s conv_id=%s input=%.100s",
                        event.get("name", ""),
                        conversation_id,
                        str(tool_input),
                    )

                # Track tool completion — sources are accumulated
                # in the module-level _last_sources list inside the tool
                elif event_type == "on_tool_end":
                    tool_output = event["data"]["output"]
                    if tool_output.name == "retrieve_documents":
                        pass

                    logger.info(
                        "Tool %s finished conv_id=%s",
                        event.get("name", ""),
                        conversation_id,
                    )

        except asyncio.CancelledError:
            logger.info("Stream cancelled for conv_id=%s", conversation_id)
            yield StreamManager._sse_error("Stream cancelled")
            return
        except StreamTimeoutError as e:
            logger.warning("Stream timeout for conv_id=%s: %s", conversation_id, e)
            yield StreamManager._sse_error(str(e))
            return
        except Exception:
            logger.exception("Agent streaming failed for conv_id=%s", conversation_id)
            yield StreamManager._sse_error(
                "An error occurred while generating the response."
            )
            return

        # ── Step 3.5: Validation and fallback for empty content ───────
        full_content_originally_empty = not full_content.strip()
        if full_content_originally_empty:
            logger.warning(
                "Agent returned an empty response for conv_id=%s. Using fallback message.",
                conversation_id,
            )
            full_content = "I'm sorry, I was unable to generate a response. Please try asking your question again or check your model configuration."
            yield StreamManager._sse_event("token", {"content": full_content})

        # ── Step 4: Extract citations from the agent's final answer ───
        retrieved_sources = source_tracker.get_sources()
        cited = self.citation_extractor.extract(full_content, retrieved_sources)
        sources_data = [
            {
                "document_id": s.document_id,
                "document_name": s.document_name,
                "page_index": s.page_index,
                "chunk_index": s.chunk_index,
                "content": s.content,
                "score": s.score,
            }
            for s in cited
        ]

        # ── Step 7: Yield sources + done events ───────────────────────
        yield StreamManager.sources_event(sources_data)
        yield StreamManager.done_event(full_content, sources_data)

        # ── Step 7b: Store in semantic cache for future short-circuits ─
        if not full_content_originally_empty:
            asyncio.create_task(
                self._try_save_llm_response(query, llm_model, full_content)
            )

        # ── Step 8: Fire background tasks ─────────────────────────────
        from app.services.rag.tasks import store_messages_task, generate_summary_task

        asyncio.create_task(
            store_messages_task(
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=query,
                assistant_content=full_content,
                sources=sources_data,
            )
        )
        if self.config.enable_auto_summary:
            asyncio.create_task(
                generate_summary_task(
                    orchestrator=self,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    history=history,
                    previous_summary=summary,
                )
            )

    # ── Semantic cache delegation ──────────────────────────────────────

    @staticmethod
    async def _try_llm_short_circuit(
        query: str,
        model: str,
    ) -> str | None:
        """Check the semantic cache for a direct LLM response (Strategy 1).

        Gracefully degrades — returns ``None`` if the cache is unavailable.
        """
        cache = RedisSemanticCache.get_instance()
        if not await cache.ensure_initialized():
            return None
        return await cache.get_llm_response(query, model)

    @staticmethod
    async def _try_save_llm_response(
        query: str,
        model: str,
        response: str,
    ) -> None:
        """Persist an LLM response in the semantic cache."""
        cache = RedisSemanticCache.get_instance()
        if not await cache.ensure_initialized():
            return
        await cache.set_llm_response(query, model, response)

    # ── Conversation context loading ───────────────────────────────────

    async def _load_conversation_context(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
        db: AsyncSession,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Load conversation history and summary efficiently.

        Uses a single ownership check + a limited SQL query for the last N
        messages to minimise DB load.
        """
        try:
            conv_service = ConversationService(db)
            conv = await conv_service.get_by_id(conversation_id, user_id)
            summary = conv.summary

            # Fetch only the most recent messages via SQL LIMIT
            msg_query = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(self.config.max_history_messages)
            )
            rows = (await db.execute(msg_query)).scalars().all()

            history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
            return history, summary
        except Exception:
            logger.exception("Failed to load context for conv_id=%s", conversation_id)
            return [], None

    # ── Utility ────────────────────────────────────────────────────────

    async def retrieve_context(
        self,
        query: str,
        user_id: int,
    ) -> list[SourceItem]:
        """Standalone retrieval — useful for debugging or direct access."""
        processed = await self.query_processor.process(query)
        return await self.retriever.retrieve(
            processed_query=processed,
            user_id=user_id,
        )
