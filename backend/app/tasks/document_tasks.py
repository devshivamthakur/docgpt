"""ARQ tasks for asynchronous document processing pipeline.

Each stage updates the DB record and broadcasts progress via Redis pub/sub
so that the WebSocket handler can forward it to the frontend in real time.

Performance notes:
    * A single DB session is reused for all progress updates within a job
      (avoids 4× session create/commit/close overhead).
    * A single Redis connection is reused for all progress publications
      (avoids 4× TCP connect/close overhead).
"""

import json
import logging

import redis as sync_redis
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.core.config import settings
from app.services.ai.processing.pipeline import ProcessingPipeline
from app.services.ai.schemas import ProcessingStage

logger = logging.getLogger(__name__)


def _get_sync_engine(ctx: dict):
    """Return the synchronous DB engine stored in the ARQ worker context."""
    return ctx["db_engine"]


async def process_document(
    ctx: dict, document_id: int, storage_path: str, original_filename: str
) -> None:
    """Run the full document processing pipeline.

    Called by the ARQ worker when a job is dequeued.
    Stages: Parsing → Chunking (parallelised) → Indexing → Ready
    """
    engine = _get_sync_engine(ctx)

    # ── Reusable resources for the lifetime of this job ───────────────
    # Open one DB session and one Redis connection instead of creating
    # new ones on every progress update.
    redis_client = sync_redis.from_url(settings.redis_url)

    with Session(engine) as session:
        try:
            # ── Look up user_id from the document record ────────────
            doc = session.get(Document, document_id)
            if doc is None:
                logger.warning("Document %s not found in DB — skipping", document_id)
                return
            user_id = doc.user_id

            # ── Langfuse trace for the full job ─────────────────────
            lf_span = None
            try:
                from app.core.langfuse import get_langfuse

                lf = get_langfuse()
                if lf is not None:
                    lf_span = lf.start_as_current_observation(
                        name="process_document_job",
                        as_type="span",
                        end_on_exit=True,
                        metadata={
                            "document_id": document_id,
                            "original_filename": original_filename,
                            "user_id": user_id,
                            "storage_path": storage_path,
                        },
                    )
                    lf_span.__enter__()
            except Exception:
                lf_span = None

            try:
                # Build a progress callback that reuses the shared session + redis
                callback = _make_progress_callback(session, redis_client, document_id)

                pipeline = ProcessingPipeline(
                    document_id=document_id,
                    file_path=storage_path,
                    original_filename=original_filename,
                    user_id=user_id,
                )
                await pipeline.run(callback=callback)

                # Final: mark READY
                doc = session.get(Document, document_id)
                if doc is not None:
                    doc.status = DocumentStatus.READY.value
                    doc.progress = 100
                    session.commit()

                _publish(
                    redis_client,
                    document_id,
                    DocumentStatus.READY.value,
                    100,
                    "Document ready",
                )
                logger.info("Document %s processed successfully", document_id)

            except Exception as exc:
                logger.exception("Document %s processing failed", document_id)
                doc = session.get(Document, document_id)
                if doc is not None:
                    doc.status = DocumentStatus.FAILED.value
                    doc.progress = 0
                    doc.error_message = str(exc)
                    session.commit()

                _publish(
                    redis_client,
                    document_id,
                    DocumentStatus.FAILED.value,
                    0,
                    f"Processing failed: {exc}",
                )
                raise  # ARQ handles retries via max_tries

            finally:
                if lf_span is not None:
                    try:
                        lf_span.__exit__(None, None, None)
                    except Exception:
                        pass

        finally:
            redis_client.close()


# ── Internal helpers ───────────────────────────────────────────────────


def _update_doc(session: Session, document_id: int, **kwargs) -> None:
    """Update document fields using the **shared** session and commit."""
    doc = session.get(Document, document_id)
    if doc is None:
        logger.warning("Document %s not found in DB — skipping", document_id)
        return
    for key, value in kwargs.items():
        setattr(doc, key, value)
    session.commit()


def _publish(
    redis_client: sync_redis.Redis,
    document_id: int,
    status: str,
    progress: int,
    message: str = "",
) -> None:
    """Publish a progress update on the **shared** Redis connection.

    This replaces the previous pattern of creating a new connection per
    call (which incurred TCP connect/close overhead for every stage).
    """
    try:
        channel = f"document:{document_id}:progress"
        payload = json.dumps(
            {"status": status, "progress": progress, "message": message}
        )
        redis_client.publish(channel, payload)
    except Exception:
        logger.exception("Failed to publish progress to Redis")


def _make_progress_callback(
    session: Session,
    redis_client: sync_redis.Redis,
    document_id: int,
):
    """Build a progress callback closure bound to the shared DB + Redis resources."""

    def _callback(progress_status, _doc_id):
        _id = document_id
        if progress_status == ProcessingStage.PARSING:
            _update_doc(session, _id, status=DocumentStatus.PARSING.value, progress=25)
            _publish(
                redis_client,
                _id,
                DocumentStatus.PARSING.value,
                25,
                "Parsing document content…",
            )
        elif progress_status == ProcessingStage.CHUNKING:
            _update_doc(session, _id, status=DocumentStatus.CHUNKING.value, progress=50)
            _publish(
                redis_client,
                _id,
                DocumentStatus.CHUNKING.value,
                50,
                "Splitting into semantic chunks…",
            )
        elif progress_status == ProcessingStage.EMBEDDING:
            _update_doc(
                session, _id, status=DocumentStatus.EMBEDDING.value, progress=75
            )
            _publish(
                redis_client,
                _id,
                DocumentStatus.EMBEDDING.value,
                75,
                "Generating vector embeddings…",
            )
        elif progress_status == ProcessingStage.INDEXING:
            _update_doc(session, _id, status=DocumentStatus.INDEXING.value, progress=90)
            _publish(
                redis_client,
                _id,
                DocumentStatus.INDEXING.value,
                90,
                "Adding to vector index…",
            )

    return _callback
