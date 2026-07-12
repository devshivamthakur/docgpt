import os
import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, BadRequestException, ForbiddenException
from app.models.document import Document, DocumentStatus


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

        doc = Document(
            user_id=user_id,
            filename=relative_path,
            original_filename=original_filename,
            file_size=file_size,
            mime_type=mime_type,
            status=DocumentStatus.UPLOADING,
            progress=0,
        )
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)

        return doc, absolute_path

    async def mark_uploaded(self, doc_id: int) -> Document:
        """Mark document as uploaded and queue for processing."""
        doc = await self.get_document(doc_id)
        doc.status = DocumentStatus.UPLOADED
        doc.progress = 0
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def get_document(self, doc_id: int) -> Document:
        """Get a document by ID, raise NotFoundException if missing."""
        doc = await self.db.get(Document, doc_id)
        if not doc:
            raise NotFoundException("Document not found")
        return doc

    async def get_user_document(self, doc_id: int, user_id: int) -> Document:
        """Get a document, ensuring it belongs to the user."""
        doc = await self.get_document(doc_id)
        if doc.user_id != user_id:
            raise ForbiddenException("Access denied")
        return doc

    async def list_documents(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """List documents for a user with pagination."""
        query = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        count_query = select(func.count()).where(Document.user_id == user_id)

        rows = (await self.db.execute(query)).scalars().all()
        total = (await self.db.execute(count_query)).scalar() or 0

        return list(rows), total

    async def delete_document(self, doc_id: int, user_id: int) -> None:
        """Delete a document (file + DB record)."""
        doc = await self.get_user_document(doc_id, user_id)

        # Remove physical file
        abs_path = os.path.join(settings.upload_dir, doc.filename)
        if os.path.exists(abs_path):
            os.remove(abs_path)

        await self.db.delete(doc)
        await self.db.commit()

    async def update_progress(
        self,
        doc_id: int,
        status: DocumentStatus,
        progress: int,
        error_message: str | None = None,
    ) -> Document:
        """Update document status and progress (used by ARQ worker)."""
        doc = await self.db.get(Document, doc_id)
        if not doc:
            raise NotFoundException("Document not found")
        doc.status = status
        doc.progress = progress
        doc.updated_at = datetime.utcnow()
        if error_message is not None:
            doc.error_message = error_message
        await self.db.commit()
        await self.db.refresh(doc)
        return doc
