from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_token
from app.db.session import get_db
from app.schemas.auth import RefreshRequest
from app.services.user_service import UserService


async def get_current_user(
    request: Request,
):
    """Dependency that returns the current user from ``request.state.user``.

    The user is already resolved and attached by ``AuthMiddleware``, so this
    is a lightweight lookup with no additional DB query or JWT decoding.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


async def get_current_user_from_refresh_token(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Dependency that resolves the current user from a refresh token sent in the request body.

    Validates the token, verifies it is a refresh-type token, looks up the user,
    and returns the user object. Raises ``HTTPException(401)`` on any failure.
    """
    try:
        token_data = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if token_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_service = UserService(db)
    user = await user_service.get_by_id(int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
