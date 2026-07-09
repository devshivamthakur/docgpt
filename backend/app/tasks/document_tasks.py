"""Celery tasks for asynchronous document processing pipeline.

Each stage updates the DB record and broadcasts progress via Redis pub/sub
so that the WebSocket handler can forward it to the frontend in real time.
"""

import logging
import time
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.tasks.celery_app import celery_app, publish_progress

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_sync_engine():
    """Lazy-initialized synchronous engine for Celery workers.

    Uses psycopg (v3) instead of the default psycopg2, which is not installed.
    Created lazily so that import-time DB driver resolution does not fail
    when the Celery worker process starts before the database is ready.
    """
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url)


def _update_db(document_id: int, **kwargs) -> None:
    """Update document fields in the database synchronously."""
    engine = _get_sync_engine()
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.warning("Document %s not found in DB — skipping", document_id)
            return
        for key, value in kwargs.items():
            setattr(doc, key, value)
        session.commit()


def _simulate_stage(
    document_id: int,
    status: DocumentStatus,
    progress: int,
    duration: float,
    message: str,
) -> None:
    """Update status, broadcast progress, then sleep to simulate work."""
    _update_db(document_id, status=status.value, progress=progress)
    publish_progress(document_id, status.value, progress, message)
    time.sleep(duration)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_document(self, document_id: int) -> None:
    """Run the full document processing pipeline.

    Called immediately after a file is uploaded.
    Stages: Parsing → Chunking → Embedding → Indexing → Ready
    """
    try:
        # ── Stage 1: Parsing (extract text + OCR) ────────────────
        _simulate_stage(
            document_id,
            DocumentStatus.PARSING,
            25,
            duration=2.0,
            message="Parsing document content…",
        )

        # ── Stage 2: Chunking (split into semantic chunks) ───────
        _simulate_stage(
            document_id,
            DocumentStatus.CHUNKING,
            50,
            duration=2.0,
            message="Splitting into semantic chunks…",
        )

        # ── Stage 3: Embedding (generate vectors) ────────────────
        _simulate_stage(
            document_id,
            DocumentStatus.EMBEDDING,
            75,
            duration=2.5,
            message="Generating vector embeddings…",
        )

        # ── Stage 4: Indexing (add to vector database) ───────────
        _simulate_stage(
            document_id,
            DocumentStatus.INDEXING,
            90,
            duration=1.5,
            message="Adding to vector index…",
        )

        # ── Done ─────────────────────────────────────────────────
        _update_db(document_id, status=DocumentStatus.READY.value, progress=100)
        publish_progress(document_id, DocumentStatus.READY.value, 100, "Document ready")

        logger.info("Document %s processed successfully", document_id)

    except Exception as exc:
        logger.exception("Document %s processing failed", document_id)
        _update_db(
            document_id,
            status=DocumentStatus.FAILED.value,
            progress=0,
            error_message=str(exc),
        )
        publish_progress(
            document_id,
            DocumentStatus.FAILED.value,
            0,
            f"Processing failed: {exc}",
        )
        raise self.retry(exc=exc)
