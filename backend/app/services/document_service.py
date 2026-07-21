import os
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    NotFoundException,
    ForbiddenException,
)
from app.db.repositories import DocumentRepository
from app.models.document import Document, DocumentStatus
from app.services.ai.embedding.qdrant import get_qdrant_service
import asyncio


class DocumentService:
    """Business-logic layer for document management.

    Delegates all data access to ``DocumentRepository``.
    """

    def __init__(self, db: AsyncSession):
        self.repo = DocumentRepository(db)

    async def create_document(
        self,
        user_id: int,
        original_filename: str,
        file_size: int,
        mime_type: str,
    ) -> tuple[Document, str]:
        """Create a document record and return (doc, stored_path)."""
        # Generate a unique stored filename to prevent collisions
        ext = os.path.splitext(original_filename)[1]
        stored_name = f"{uuid.uuid4().hex}{ext}"
        relative_path = f"{user_id}/{stored_name}"
        absolute_path = os.path.join(settings.upload_dir, relative_path)

        doc = await self.repo.create(
            user_id=user_id,
            filename=relative_path,
            original_filename=original_filename,
            file_size=file_size,
            mime_type=mime_type,
        )
        return doc, absolute_path

    async def mark_uploaded(self, doc_id: int) -> Document:
        """Mark document as uploaded and queue for processing."""
        return await self.repo.update_progress(
            doc_id, status=DocumentStatus.UPLOADED, progress=0
        )

    async def get_document(self, doc_id: int) -> Document:
        """Get a document by ID, raise NotFoundException if missing."""
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            raise NotFoundException("Document not found")
        return doc

    async def get_user_document(self, doc_id: int, user_id: int) -> Document:
        """Get a document, ensuring it belongs to the user."""
        doc = await self.get_document(doc_id)
        if doc.user_id != user_id:
            raise ForbiddenException("Access denied")
        return doc

    async def get_storage_usage(self, user_id: int) -> int:
        """Get total storage used by a user in bytes."""
        return await self.repo.get_storage_usage(user_id)

    async def get_storage_quota_bytes(self) -> int:
        """Return the storage quota per user in bytes."""
        return settings.storage_quota_bytes

    async def list_documents(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """List documents for a user with pagination."""
        return await self.repo.list_by_user(user_id, skip=skip, limit=limit)

    async def delete_document(self, doc_id: int, user_id: int) -> None:
        """Delete a document (file + DB record)."""
        doc = await self.get_user_document(doc_id, user_id)

        # Remove physical file in a non-blocking background thread
        abs_path = os.path.join(settings.upload_dir, doc.filename)

        def _remove_file_sync():
            if os.path.exists(abs_path):
                os.remove(abs_path)

        await asyncio.to_thread(_remove_file_sync)

        asyncio.create_task(
            asyncio.to_thread(
                get_qdrant_service().delete_documents_from_collection,
                user_id=user_id,
                document_id=doc_id,
            )
        )

        await self.repo.delete(doc)

    async def update_progress(
        self,
        doc_id: int,
        status: DocumentStatus,
        progress: int,
        error_message: str | None = None,
    ) -> Document:
        """Update document status and progress (used by ARQ worker)."""
        return await self.repo.update_progress(
            doc_id, status=status, progress=progress, error_message=error_message
        )

    async def reset_for_reprocess(self, doc_id: int, user_id: int) -> Document:
        """Reset a failed document back to UPLOADED state for reprocessing.

        Deletes existing Qdrant vectors first, then clears the error state.
        """
        doc = await self.get_user_document(doc_id, user_id)

        if doc.status != DocumentStatus.FAILED:
            raise BadRequestException(
                f"Cannot reprocess document with status '{doc.status.value}'. "
                "Only failed documents can be reprocessed."
            )

        # Delete existing vectors from Qdrant before re-indexing
        asyncio.create_task(
            asyncio.to_thread(
                get_qdrant_service().delete_documents_from_collection,
                user_id=user_id,
                document_id=doc_id,
            )
        )

        return await self.repo.update_progress(
            doc_id,
            status=DocumentStatus.UPLOADED,
            progress=0,
            error_message=None,
        )
