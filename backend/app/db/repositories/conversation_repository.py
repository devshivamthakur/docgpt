"""Repository for Conversation and Message model CRUD operations."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class ConversationRepository:
    """Data-access layer for the ``Conversation`` and ``Message`` models."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Conversations ──────────────────────────────────────────────────

    async def get_by_id(self, conv_id: uuid.UUID) -> Conversation | None:
        """Fetch a conversation by primary key."""
        return await self.db.get(Conversation, conv_id)

    async def create(
        self, user_id: int, title: str = "New conversation"
    ) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(user_id=user_id, title=title)
        self.db.add(conv)
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Conversation], int]:
        """List conversations for a user with pagination (most recent first)."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        count_stmt = select(func.count()).where(Conversation.user_id == user_id)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        return list(rows), total

    async def update_title(self, conv_id: uuid.UUID, title: str) -> Conversation:
        """Update the title of a conversation."""
        conv = await self.db.get(Conversation, conv_id)
        if conv is None:
            raise ValueError(f"Conversation {conv_id} not found")
        conv.title = title
        conv.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def update_summary(self, conv_id: uuid.UUID, summary: str) -> Conversation:
        """Update the summary of a conversation."""
        conv = await self.db.get(Conversation, conv_id)
        if conv is None:
            raise ValueError(f"Conversation {conv_id} not found")
        conv.summary = summary
        conv.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def delete(self, conv: Conversation) -> None:
        """Delete a conversation record."""
        await self.db.delete(conv)
        await self.db.commit()

    # ── Messages ───────────────────────────────────────────────────────

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        sources: dict | None = None,
    ) -> Message:
        """Add a message to a conversation and update its timestamp."""
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
        )
        self.db.add(msg)

        # Bump conversation timestamp
        conv = await self.db.get(Conversation, conversation_id)
        if conv:
            conv.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def get_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        """Get all messages for a conversation in chronological order."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        rows = (await self.db.execute(query)).scalars().all()
        return list(rows)

    async def get_last_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int = 10,
    ) -> list[Message]:
        """Get the last N messages in chronological order."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(query)).scalars().all()
        return list(reversed(rows))
