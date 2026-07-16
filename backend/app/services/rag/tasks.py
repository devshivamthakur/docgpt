"""Fire-and-forget background tasks for the RAG pipeline.

These tasks are spawned via ``asyncio.create_task`` so they don't block
the main SSE response stream. Each task uses its own dedicated DB session
to ensure isolation from the main request-response cycle.
"""

import logging
import uuid


from app.db.session import SessionLocal
from app.services.conversation_service import ConversationService
from app.services.rag.orchestrator import RagOrchestrator

logger = logging.getLogger(__name__)


async def store_messages_task(
    conversation_id: uuid.UUID,
    user_id: int,
    user_message: str,
    assistant_content: str,
    sources: list[dict],
) -> None:
    """Persist user + assistant messages in a dedicated DB session."""
    try:
        async with SessionLocal() as bg_db:
            svc = ConversationService(bg_db)
            await svc.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_message,
            )
            await svc.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=assistant_content,
                sources={"sources": sources},
            )
    except Exception:
        logger.exception("Failed to store messages for conv_id=%s", conversation_id)


async def generate_summary_task(
    orchestrator: RagOrchestrator,
    conversation_id: uuid.UUID,
    user_id: int,
    history: list[dict],
    previous_summary: str | None = None,
) -> None:
    """Generate and persist a conversation summary."""
    if not history:
        return

    try:
        prompt = orchestrator.prompt_builder.build_summary_prompt(
            history=history,
            previous_summary=previous_summary,
        )

        langfuse_config = orchestrator._build_llm_config(
            user_id=user_id,
            conversation_id=conversation_id,
            trace_name="rag_summary",
            tags=["rag", "summary"],
        )
        summary_parts: list[str] = []
        async for chunk in orchestrator.summary_llm.astream(
            prompt, config=langfuse_config
        ):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            if token:
                summary_parts.append(token)

        summary_text = "".join(summary_parts).strip()
        if not summary_text:
            return

        async with SessionLocal() as bg_db:
            conv_service = ConversationService(bg_db)
            await conv_service.update_summary(
                conversation_id,
                user_id,
                summary_text,
            )

        logger.info("Summary updated for conv_id=%s", conversation_id)
    except Exception:
        logger.exception("Failed to generate summary for conv_id=%s", conversation_id)
