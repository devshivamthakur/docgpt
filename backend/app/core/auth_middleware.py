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
    PUBLIC_PATHS = frozenset(
        {
            "/health",
            "/api/auth/login",
            "/api/auth/register",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
            "/",
        }
    )

    async def dispatch(self, request: Request, call_next):
        # Skip auth for WebSocket upgrade requests — they authenticate via query param
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        if request.url.path in "/api/auth/refresh":
            # extract refresh token from request body
            try:
                body = await request.json()
                refresh_token = body.get("refresh_token")
                if not refresh_token:
                    logger.warning("Missing refresh token: %s", request.url.path)
                    return JSONResponse(
                        status_code=401,
                        content={"message": "Missing refresh token"},
                    )
                payload = decode_token(refresh_token)
                if payload.get("type") != "refresh":
                    logger.warning("Invalid refresh token type: %s", request.url.path)
                    return JSONResponse(
                        status_code=401,
                        content={"message": "Invalid refresh token"},
                    )
            except Exception:
                logger.warning("Invalid refresh token: %s", request.url.path)
                return JSONResponse(
                    status_code=401,
                    content={"message": "Invalid or expired refresh token"},
                )
        else:
            # ── Extract & validate Bearer token ──────────────────────────────
            authorization = request.headers.get("authorization", "")
            token: str | None = None
            if authorization.startswith("Bearer "):
                token = authorization.split(" ", 1)[1]
            else:
                # Fallback for EventSource / SSE — cannot set custom headers
                token = request.query_params.get("token")

            if not token:
                logger.warning("Missing authentication token: %s", request.url.path)
                return JSONResponse(
                    status_code=401,
                    content={"message": "Missing authentication token"},
                )
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
