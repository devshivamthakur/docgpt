import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception — all custom exceptions inherit from this."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(self.message)


class BadRequestException(AppException):
    """400 Bad Request."""

    def __init__(self, message: str = "Bad request"):
        super().__init__(status_code=400, message=message)


class UnauthorizedException(AppException):
    """401 Unauthorized."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(status_code=401, message=message)


class ForbiddenException(AppException):
    """403 Forbidden."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(status_code=403, message=message)


class NotFoundException(AppException):
    """404 Not Found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(status_code=404, message=message)


class ConflictException(AppException):
    """409 Conflict."""

    def __init__(self, message: str = "Conflict"):
        super().__init__(status_code=409, message=message)


class InternalServerException(AppException):
    """500 Internal Server Error."""

    def __init__(self, message: str = "Internal server error"):
        super().__init__(status_code=500, message=message)


# ---------------------------------------------------------------------------
# Exception handlers — every response body uses ONLY the "message" key
# ---------------------------------------------------------------------------


async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom AppException subclasses."""
    logger.error(
        "%s: %s", exc.__class__.__name__, exc.message,
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle raw Starlette / FastAPI HTTPException (fallback)."""
    logger.warning(
        "HTTPException %s: %s", exc.status_code, exc.detail,
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic request validation errors — produce a single human-readable message."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc_parts = [
        str(p) for p in first.get("loc", [])
        if p not in ("body", "query", "path", "string")
    ]
    field = " -> ".join(loc_parts) if loc_parts else ""
    msg = first.get("msg", "Validation error")
    message = f"{field}: {msg}" if field else msg
    logger.warning("ValidationError: %s", message, extra={"path": request.url.path})
    return JSONResponse(status_code=422, content={"message": message})


async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — never leak internals."""
    logger.exception(
        "Unhandled exception: %s", str(exc),
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )
