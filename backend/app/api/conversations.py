"""Chat & conversation API endpoints with SSE streaming for RAG.

Uses the production-grade ``RagService`` from ``app.services.rag``
for scalable retrieval-augmented generation.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import get_current_user
from app.core.rate_limiter import rate_limit
from app.core.redis_cache import cached, invalidate_conversation_caches
from app.core.sanitization import Sanitizer
from app.db.session import get_db, SessionLocal
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    DeleteResponse,
    MessageResponse,
)
from app.services.conversation_service import ConversationService
from app.services.rag.orchestrator import RagOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ── CRUD endpoints ────────────────────────────────────────────────────


@router.post("", response_model=ConversationResponse, status_code=201)
@rate_limit(max_requests=60, window_seconds=60, scope="conversations")
async def create_conversation(
    request: Request,
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new conversation."""
    service = ConversationService(db)
    conv = await service.create(
        user_id=current_user.id,
        title=payload.title,
    )
    # Invalidate list cache so the new conversation appears immediately
    asyncio.create_task(invalidate_conversation_caches(user_id=current_user.id))
    return ConversationResponse.model_validate(conv)


@router.get("", response_model=ConversationListResponse)
@cached(ttl=60, soft_ttl=30)
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all conversations for the authenticated user."""
    service = ConversationService(db)
    convs, total = await service.list_by_user(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return ConversationListResponse(
        conversations=[ConversationResponse.model_validate(c) for c in convs],
        total=total,
    )


@router.get("/{conv_id}", response_model=ConversationDetailResponse)
@cached(ttl=120, soft_ttl=60)
async def get_conversation(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a conversation with all its messages."""
    service = ConversationService(db)
    conv = await service.get_by_id(conv_id, current_user.id)
    messages = await service.get_messages(conv_id, current_user.id)
    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.delete("/{conv_id}", response_model=DeleteResponse)
async def delete_conversation(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    service = ConversationService(db)
    await service.delete(conv_id, current_user.id)
    # Invalidate caches so deleted conversation disappears immediately
    asyncio.create_task(invalidate_conversation_caches(user_id=current_user.id))
    return DeleteResponse(message="Conversation deleted successfully")


# ── SSE streaming endpoint ────────────────────────────────────────────


async def _stream_response(
    conv_id: uuid.UUID,
    user_id: int,
    user_message: str,
    db: AsyncSession,
):
    """Internal generator that produces SSE ``data: ...`` lines.

    Delegates to ``RagService.stream_answer_v2`` which handles the full
    pipeline: query processing → hybrid retrieval → prompt building →
    LLM streaming → citation extraction → background persistence.

    The connection closes immediately after the last event. The frontend
    closes ``EventSource`` upon receiving the ``done`` event, and the
    ``completedRef`` guard suppresses the reconnect ``error`` handler.
    """
    rag = RagOrchestrator()

    async for sse_event in rag.stream_answer(
        query=user_message,
        user_id=user_id,
        conversation_id=conv_id,
        db=db,
    ):
        # stream_answer_v2 already yields fully-formatted SSE events
        # (data: <json>\n\n), so we pass them through as-is.
        yield sse_event

    # Invalidate conversation caches after stream completes
    asyncio.create_task(invalidate_conversation_caches(user_id=user_id))


async def _prepare_stream(
    conv_id: uuid.UUID,
    user_message: str,
    current_user: User,
    db: AsyncSession,
) -> str:
    """Validate and sanitize input (shared by POST & GET).

    Auto-titling is deferred to a background task so it doesn't delay
    the first token.
    """
    if not user_message or not user_message.strip():
        from app.core.exceptions import BadRequestException

        raise BadRequestException("Message content is required")

    # Sanitize user input — strip dangerous patterns
    sanitized = Sanitizer.sanitize_query(user_message)
    if sanitized.is_rejected:
        from app.core.exceptions import BadRequestException

        raise BadRequestException("Your message was flagged as potentially unsafe.")
    user_message = sanitized.cleaned

    # Auto-title the conversation in the background (don't block first token)
    conv_service = ConversationService(db)
    try:
        conv = await conv_service.get_by_id(conv_id, current_user.id)
        if conv.title == "New conversation":
            new_title = Sanitizer.sanitize_title(user_message[:50])
            if len(user_message) > 50:
                new_title += "…"
            asyncio.create_task(
                _auto_title_background(conv_id, current_user.id, new_title)
            )
    except Exception:
        logger.debug("Could not auto-title conversation %s", conv_id)

    return user_message


async def _auto_title_background(
    conv_id: uuid.UUID,
    user_id: int,
    new_title: str,
) -> None:
    """Auto-title a conversation in a dedicated DB session.

    Runs as a fire-and-forget background task to avoid sharing the
    request-scoped DB session with the RAG pipeline, which would cause
    ``asyncpg.InterfaceError: another operation is in progress``.
    """
    try:
        async with SessionLocal() as bg_db:
            svc = ConversationService(bg_db)
            await svc.update_title(conv_id, user_id, new_title)
    except Exception:
        logger.debug("Could not auto-title conversation %s", conv_id)


def _stream_headers() -> dict[str, str]:
    """Common SSE response headers."""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/event-stream",
    }


@router.post("/{conv_id}/stream")
@rate_limit(max_requests=60, window_seconds=60, scope="conversations")
async def stream_conversation(
    conv_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream a RAG-powered response using Server-Sent Events (SSE).

    The request body should be a JSON object with a ``content`` field
    containing the user's message.

    Returns a ``text/event-stream`` response that emits:

    - ``data: {"type":"token","content":"..."}`` — each token from the LLM
    - ``data: {"type":"sources","sources":[...]}`` — extracted source citations
    - ``data: {"type":"done","content":"...","sources":[...]}`` — streaming complete
    - ``data: {"type":"error","message":"..."}`` — error occurred
    """
    # Parse the JSON body
    try:
        body = await request.json()
        user_message = body.get("content", "")
    except Exception:
        from app.core.exceptions import BadRequestException

        raise BadRequestException('Invalid JSON body. Expected {"content": "..."}')

    user_message = await _prepare_stream(conv_id, user_message, current_user, db)

    return StreamingResponse(
        _stream_response(conv_id, current_user.id, user_message, db),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.get("/{conv_id}/stream")
async def stream_conversation_get(
    conv_id: uuid.UUID,
    content: str = Query(..., min_length=1, description="The user's message"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream a RAG response via GET — used by ``EventSource`` clients.

    Same as the POST endpoint but accepts ``content`` as a query parameter
    and the JWT token as ``?token=...`` (since EventSource cannot set
    custom request headers).
    """
    user_message = await _prepare_stream(conv_id, content, current_user, db)

    return StreamingResponse(
        _stream_response(conv_id, current_user.id, user_message, db),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )
