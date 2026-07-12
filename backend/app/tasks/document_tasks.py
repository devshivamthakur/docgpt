"""ARQ tasks for asynchronous document processing pipeline.

Each stage updates the DB record and broadcasts progress via Redis pub/sub
so that the WebSocket handler can forward it to the frontend in real time.
"""

import logging
import time

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.tasks.utils import publish_progress
from app.services.AIServices.AiDocumentProcess import AiDocumentProcess
from app.services.AIServices.schemas import ProcessingStage

logger = logging.getLogger(__name__)


def _get_sync_engine(ctx: dict):
    """Return the synchronous DB engine stored in the ARQ worker context."""
    return ctx["db_engine"]


def _update_db(ctx: dict, document_id: int, **kwargs) -> None:
    """Update document fields in the database synchronously."""
    engine = _get_sync_engine(ctx)
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.warning("Document %s not found in DB — skipping", document_id)
            return
        for key, value in kwargs.items():
            setattr(doc, key, value)
        session.commit()


def _make_progress_callback(ctx: dict, document_id: int):
    """Build a progress callback closure bound to the ARQ worker context."""
    def _callback(progress_status, _doc_id):
        _id = document_id
        if progress_status == ProcessingStage.PARSING:
            _update_db(ctx, _id, status=DocumentStatus.PARSING.value, progress=25)
            publish_progress(_id, DocumentStatus.PARSING.value, 25, "Parsing document content…")
            time.sleep(2.0)
        elif progress_status == ProcessingStage.CHUNKING:
            _update_db(ctx, _id, status=DocumentStatus.CHUNKING.value, progress=50)
            publish_progress(_id, DocumentStatus.CHUNKING.value, 50, "Splitting into semantic chunks…")
            time.sleep(2.0)
        elif progress_status == ProcessingStage.EMBEDDING:
            _update_db(ctx, _id, status=DocumentStatus.EMBEDDING.value, progress=75)
            publish_progress(_id, DocumentStatus.EMBEDDING.value, 75, "Generating vector embeddings…")
            time.sleep(2.5)
        elif progress_status == ProcessingStage.INDEXING:
            _update_db(ctx, _id, status=DocumentStatus.INDEXING.value, progress=90)
            publish_progress(_id, DocumentStatus.INDEXING.value, 90, "Adding to vector index…")
            time.sleep(1.5)
    return _callback


async def process_document(ctx: dict, document_id: int, storage_path: str, original_filename: str) -> None:
    """Run the full document processing pipeline.

    Called by the ARQ worker when a job is dequeued.
    Stages: Parsing → Chunking → Embedding → Indexing → Ready
    """
    try:
        callback = _make_progress_callback(ctx, document_id)
        documentProcessor = AiDocumentProcess(
            document_id,
            storage_path,
            callback=callback,
            original_filename=original_filename,
        )
        documentProcessor.process()

        _update_db(ctx, document_id, status=DocumentStatus.READY.value, progress=100)
        publish_progress(document_id, DocumentStatus.READY.value, 100, "Document ready")
        logger.info("Document %s processed successfully", document_id)

    except Exception as exc:
        logger.exception("Document %s processing failed", document_id)
        _update_db(
            ctx,
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
        raise  # ARQ handles retries via max_tries
