"""Repository for Document model CRUD operations."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    """Data-access layer for the ``Document`` model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, doc_id: int) -> Document | None:
        """Fetch a document by primary key."""
        return await self.db.get(Document, doc_id)

    async def create(
        self,
        user_id: int,
        filename: str,
        original_filename: str,
        file_size: int,
        mime_type: str,
    ) -> Document:
        """Create a new document record in UPLOADING status."""
        doc = Document(
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            file_size=file_size,
            mime_type=mime_type,
            status=DocumentStatus.UPLOADING,
            progress=0,
        )
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def update_progress(
        self,
        doc_id: int,
        status: DocumentStatus,
        progress: int,
        error_message: str | None = None,
    ) -> Document:
        """Update document status, progress, and optional error."""
        doc = await self.db.get(Document, doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")
        doc.status = status
        doc.progress = progress
        doc.updated_at = datetime.utcnow()
        if error_message is not None:
            doc.error_message = error_message
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """List documents for a user with pagination (newest first)."""
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

    async def get_storage_usage(self, user_id: int) -> int:
        """Return total bytes used by a user's documents."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.user_id == user_id
            )
        )
        return result.scalar() or 0

    async def delete(self, doc: Document) -> None:
        """Delete a document record."""
        await self.db.delete(doc)
        await self.db.commit()
