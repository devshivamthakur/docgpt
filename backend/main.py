import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.auth import router as auth_router
from app.core.auth_middleware import AuthMiddleware
from app.core.logging import configure_logging
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from app.db.base import Base
from app.db.session import engine

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs startup and shutdown logic."""
    logger.info("Starting up DocGPT API")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    yield
    logger.info("Shutting down DocGPT API")


app = FastAPI(
    title="DocGPT API",
      version="0.1.0", 
      lifespan=lifespan,
      
              
              )

# ── Middleware ──────────────────────────────────────────────────────────
app.add_middleware(AuthMiddleware)

# ── Exception handlers — every response uses {"message": "..."} ─────────
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ── Routers ─────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api")


@app.get("/health")
def health_check():
    """Health-check endpoint."""
    return {"status": "ok"}
