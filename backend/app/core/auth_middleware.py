import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates JWT tokens on protected routes."""

    # Public routes that don't require authentication
    PUBLIC_PATHS = frozenset({
        "/health",
        "/api/auth/login",
        "/api/auth/register",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
        "/",
    })

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # ── Extract & validate Bearer token ──────────────────────────────
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            logger.warning("Missing authorization header: %s", request.url.path)
            return JSONResponse(
                status_code=401,
                content={"message": "Missing authentication token"},
            )

        token = authorization.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except Exception:
            logger.warning("Invalid token: %s", request.url.path)
            return JSONResponse(
                status_code=401,
                content={"message": "Invalid or expired token"},
            )

        # ── Resolve user from token ──────────────────────────────────────
        try:
            async with SessionLocal() as db:
                user_service = UserService(db)
                user = await user_service.get_by_id(int(payload.get("sub", 0)))
                if not user:
                    logger.warning("Token user not found: %s", request.url.path)
                    return JSONResponse(
                        status_code=401,
                        content={"message": "User not found"},
                    )
                request.state.user = user
        except Exception:
            logger.exception("Auth middleware error: %s", request.url.path)
            return JSONResponse(
                status_code=401,
                content={"message": "Authentication failed"},
            )

        return await call_next(request)
