"""Repository pattern — encapsulates all raw database operations.

Each repository provides a focused CRUD interface for a single entity,
leaving business logic and orchestration to the service layer.
"""

from app.db.repositories.user_repository import UserRepository
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.conversation_repository import ConversationRepository

__all__ = [
    "UserRepository",
    "DocumentRepository",
    "ConversationRepository",
]
