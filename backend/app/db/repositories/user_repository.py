"""Repository for User model CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Data-access layer for the ``User`` model.

    All methods accept an active DB session — the caller is responsible
    for committing/refreshing when needed (see service layer).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        """Fetch a user by primary key."""
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str, full_name: str) -> User:
        """Create a new user record."""
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
