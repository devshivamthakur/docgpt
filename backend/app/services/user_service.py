from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.security import hash_password, verify_password
from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.redis_cache import cached


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, email: str, password: str, full_name: str) -> User:
        existing = await self.db.scalar(select(User).where(User.email == email))
        if existing:
            raise ConflictException("Email already registered")

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.db.scalar(select(User).where(User.email == email))
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")
        return user

    @cached(ttl=3600, soft_ttl=60)
    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)
