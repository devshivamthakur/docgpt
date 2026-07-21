import asyncio
import os
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.middleware import get_current_user
from app.core.rate_limiter import rate_limit
from app.core.redis_cache import cached, invalidate_document_caches
from app.core.sanitization import Sanitizer
from app.core.websocket import listen_redis_progress, manager
from app.db.session import get_db
from app.models.document import DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    ReprocessResponse,
    StorageUsageResponse,
    UploadResponse,
)
from app.services.document_service import DocumentService
from app.tasks.arq_app import enqueue_process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("", response_model=UploadResponse, status_code=201)
@rate_limit(max_requests=30, window_seconds=60, scope="documents")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a document and trigger async processing.

    The file is saved to disk, a DB record is created with status="uploaded",
    and an ARQ job is enqueued. The frontend can then open a WebSocket
    to track real-time progress.
    """
    # ── Validate file ───────────────────────────────────────────────
    if not file.filename:
        raise BadRequestException("Filename is required")

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise BadRequestException(
            f"Unsupported file type: {file.content_type}. "
            f"Allowed: PDF, TXT, MD, DOC, DOCX"
        )

    # Read file content (with size limit)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise BadRequestException(
            f"File exceeds the maximum size of {settings.max_upload_size_mb} MB"
        )

    # Sanitize filename to prevent path traversal
    safe_filename = Sanitizer.sanitize_filename(file.filename)

    # ── Check storage quota ─────────────────────────────────────────
    service = DocumentService(db)
    current_usage = await service.get_storage_usage(current_user.id)
    remaining = settings.storage_quota_bytes - current_usage
    if len(contents) > remaining:
        remaining_mb = remaining / (1024 * 1024)
        file_mb = len(contents) / (1024 * 1024)
        raise BadRequestException(
            f"Insufficient storage space. You have {remaining_mb:.1f} MB remaining, "
            f"but this file is {file_mb:.1f} MB. "
            f"Your storage limit is {settings.storage_quota_bytes / (1024 * 1024 * 1024):.0f} GB."
        )

    # ── Create DB record ────────────────────────────────────────────
    doc, storage_path = await service.create_document(
        user_id=current_user.id,
        original_filename=safe_filename,
        file_size=len(contents),
        mime_type=file.content_type or "application/octet-stream",
    )

    # ── Save file to disk ───────────────────────────────────────────
    def _save_file_sync():
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        with open(storage_path, "wb") as f:
            f.write(contents)

    await asyncio.to_thread(_save_file_sync)

    # ── Mark as uploaded & queue processing ─────────────────────────
    await service.mark_uploaded(doc.id)

    # Dispatch ARQ job (fire-and-forget)
    await enqueue_process_document(
        doc.id, storage_path, original_filename=file.filename
    )

    # Invalidate list cache so the new document appears immediately
    await invalidate_document_caches(user_id=current_user.id)

    logger.info(
        "Document uploaded: id=%s, filename=%s, size=%d, user=%s",
        doc.id,
        file.filename,
        len(contents),
        current_user.id,
    )

    return UploadResponse(
        id=doc.id,
        filename=file.filename,
        status=DocumentStatus.UPLOADED,
        message="Document uploaded successfully. Processing has been queued.",
    )


@router.get("", response_model=DocumentListResponse)
@cached(ttl=3600, soft_ttl=60)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents for the authenticated user."""
    service = DocumentService(db)
    documents, total = await service.list_documents(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
@cached(ttl=3600, soft_ttl=60)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single document's details."""
    service = DocumentService(db)
    doc = await service.get_user_document(doc_id, current_user.id)
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}", response_model=DeleteResponse)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a document and its file."""
    service = DocumentService(db)
    await service.delete_document(doc_id, current_user.id)
    await invalidate_document_caches(user_id=current_user.id)
    return DeleteResponse(message="Document deleted successfully")


@router.post("/{doc_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reprocess a document that previously failed.

    Resets the document status to 'uploaded', clears the error,
    deletes any existing Qdrant vectors for this document, and
    enqueues a new ARQ processing job.
    """
    service = DocumentService(db)

    # Reset document state (validates ownership & failed status)
    doc = await service.reset_for_reprocess(doc_id, current_user.id)

    # Re-enqueue the ARQ processing job
    storage_path = os.path.join(settings.upload_dir, doc.filename)
    await enqueue_process_document(
        doc.id, storage_path, original_filename=doc.original_filename
    )

    # Invalidate caches so the updated status appears immediately
    await invalidate_document_caches(user_id=current_user.id)

    logger.info(
        "Document reprocess queued: id=%s, filename=%s, user=%s",
        doc.id,
        doc.original_filename,
        current_user.id,
    )

    return ReprocessResponse(
        id=doc.id,
        filename=doc.original_filename,
        status=doc.status,
        message="Document reprocessing has been queued.",
    )


@cached(ttl=1100, soft_ttl=60)
@router.get("/storage/usage", response_model=StorageUsageResponse)
async def get_storage_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get storage usage for the authenticated user (quota: 1 GB)."""
    service = DocumentService(db)
    total_used = await service.get_storage_usage(current_user.id)
    quota = await service.get_storage_quota_bytes()
    return StorageUsageResponse(
        total_used_bytes=total_used,
        quota_bytes=quota,
        used_percent=round((total_used / quota) * 100, 2) if quota > 0 else 0,
    )


@router.websocket("/{doc_id}/progress-ws")
async def document_progress_ws(
    websocket: WebSocket,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for real-time document processing progress.

    After uploading a document, the frontend connects here to receive
    live status updates (parsing → chunking → embedding → indexing → ready).

    Authentication is done via the first WebSocket message
    (``{"type": "auth", "token": "..."}``) rather than a query param,
    to avoid leaking tokens in server logs or referrer headers.
    """
    # Accept the connection first — we authenticate via the first message
    await manager.connect(doc_id, websocket)

    try:
        # Wait for the auth message (timeout to prevent hung connections)
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)

        if not isinstance(message, dict) or message.get("type") != "auth":
            await websocket.close(code=4001, reason="Invalid auth handshake")
            return

        token = message.get("token")
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return

        # Validate token and check document ownership
        from app.core.security import decode_token
        from jose import JWTError

        try:
            payload = decode_token(token)
            user_id = int(payload.get("sub", 0))
        except JWTError, ValueError, TypeError:
            await websocket.close(code=4001, reason="Invalid token")
            return

        service = DocumentService(db)
        try:
            doc = await service.get_document(doc_id)
        except Exception:
            await websocket.close(code=4004, reason="Document not found")
            return

        if doc.user_id != user_id:
            await websocket.close(code=4004, reason="Document not found")
            return

        # Send current state immediately
        await websocket.send_json(
            {
                "status": doc.status,
                "progress": doc.progress,
                "message": "",
            }
        )

        # If already in a terminal state, no need to listen
        if doc.status in (DocumentStatus.READY, DocumentStatus.FAILED):
            return

        # Listen for Redis pub/sub updates from the ARQ worker
        await listen_redis_progress(doc_id, websocket)

    except asyncio.TimeoutError:
        logger.warning("WS auth timeout for document %s", doc_id)
        await websocket.close(code=4001, reason="Auth timeout")
    except WebSocketDisconnect:
        logger.info("WS disconnected for document %s", doc_id)
    except RuntimeError as e:
        # "Expected ASGI message 'websocket.send' or 'websocket.close'…"
        # happens when the socket is already closed/accepted — just log and exit
        logger.warning("WS runtime error for document %s: %s", doc_id, e)
    except Exception:
        logger.exception("WS error for document %s", doc_id)
    finally:
        manager.disconnect(doc_id, websocket)
