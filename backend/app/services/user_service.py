from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories import UserRepository
from app.models.user import User
from app.core.security import hash_password, verify_password
from app.core.exceptions import ConflictException, UnauthorizedException


class UserService:
    """Business-logic layer for user management.

    Delegates all data access to ``UserRepository``.
    """

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def create_user(self, email: str, password: str, full_name: str) -> User:
        existing = await self.repo.get_by_email(email)
        if existing:
            raise ConflictException("Email already registered")

        return await self.repo.create(email, hash_password(password), full_name)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.repo.get_by_id(user_id)
