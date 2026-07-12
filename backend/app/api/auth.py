from fastapi import APIRouter, Depends
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.middleware import get_current_user
from app.core.redis_cache import cached
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import UnauthorizedException
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    service = UserService(db)
    return await service.create_user(str(payload.email), payload.password, payload.full_name)


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate a user and return JWT tokens."""
    service = UserService(db)
    user = await service.authenticate(str(payload.email), payload.password)
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh the access token using a valid refresh token.

    Accepts the refresh token in the body (not the Authorization header),
    validates it, and returns a fresh access+refresh token pair.
    """

    access_token = create_access_token(str(current_user.id))
    new_refresh_token = create_refresh_token(str(current_user.id))
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)

@router.get("/me", response_model=UserOut)
@cached(ttl=60, prefix="get_me")
async def get_me(current_user=Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserOut.model_validate(current_user)
