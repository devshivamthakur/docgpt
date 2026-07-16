"""Business-logic layer for conversations and messages.

Delegates all data access to ``ConversationRepository``.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ForbiddenException
from app.db.repositories import ConversationRepository
from app.models.conversation import Conversation, Message


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.repo = ConversationRepository(db)

    # ── Conversations ────────────────────────────────────────────────

    async def create(
        self, user_id: int, title: str = "New conversation"
    ) -> Conversation:
        return await self.repo.create(user_id, title)

    async def get_by_id(self, conv_id: uuid.UUID, user_id: int) -> Conversation:
        conv = await self.repo.get_by_id(conv_id)
        if not conv:
            raise NotFoundException("Conversation not found")
        if conv.user_id != user_id:
            raise ForbiddenException("Access denied")
        return conv

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Conversation], int]:
        return await self.repo.list_by_user(user_id, skip=skip, limit=limit)

    async def update_title(
        self, conv_id: uuid.UUID, user_id: int, title: str
    ) -> Conversation:
        conv = await self.get_by_id(conv_id, user_id)
        return await self.repo.update_title(conv.id, title)

    async def delete(self, conv_id: uuid.UUID, user_id: int) -> None:
        conv = await self.get_by_id(conv_id, user_id)
        await self.repo.delete(conv)

    # ── Messages ─────────────────────────────────────────────────────

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
        role: str,
        content: str,
        sources: dict | None = None,
    ) -> Message:
        """Add a message to a conversation after verifying ownership."""
        await self.get_by_id(conversation_id, user_id)
        return await self.repo.add_message(
            conversation_id, role=role, content=content, sources=sources
        )

    async def get_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
    ) -> list[Message]:
        """Get all messages for a conversation (must be owner)."""
        await self.get_by_id(conversation_id, user_id)
        return await self.repo.get_messages(conversation_id)

    async def get_last_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
        limit: int = 10,
    ) -> list[Message]:
        """Get the last N messages for a conversation (must be owner)."""
        await self.get_by_id(conversation_id, user_id)
        return await self.repo.get_last_messages(conversation_id, limit=limit)

    async def get_summary(self, conversation_id: uuid.UUID, user_id: int) -> str | None:
        """Get the summary of a conversation (must be owner)."""
        conv = await self.get_by_id(conversation_id, user_id)
        return conv.summary

    async def update_summary(
        self, conversation_id: uuid.UUID, user_id: int, summary: str
    ) -> Conversation:
        """Update the summary of a conversation (must be owner)."""
        conv = await self.get_by_id(conversation_id, user_id)
        return await self.repo.update_summary(conv.id, summary)
