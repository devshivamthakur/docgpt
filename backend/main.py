import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.conversations import router as conversations_router
from app.api.Evalapi import router as eval_router
from app.core.auth_middleware import AuthMiddleware
from app.core.logging import configure_logging
from app.core.rate_limiter import RateLimitMiddleware, init_rate_limiter
from fastapi.middleware.cors import CORSMiddleware
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from app.db.base import Base
from app.db.session import engine
from app.core.config import settings
from app.tasks.arq_app import init_arq_pool, shutdown_arq_pool

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs startup and shutdown logic."""
    logger.info("Starting up DocGPT API")
    # Initialise ARQ Redis pool for job enqueuing
    await init_arq_pool()
    logger.info("ARQ Redis pool initialised")

    # Initialise Langfuse client for LLM observability
    if settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_PUBLIC_KEY:
        from app.core.langfuse import get_langfuse

        get_langfuse()
        logger.info("Langfuse client initialised (host=%s)", settings.LANGFUSE_HOST)
    else:
        logger.warning(
            "Langfuse not configured — LLM observability disabled. "
            "Set LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY in .env"
        )

    # Initialise rate-limiter Redis connection
    await init_rate_limiter()

    # Initialise semantic cache (graceful if HuggingFace is not configured)
    try:
        from app.services.ai.semantic_cache.cache import RedisSemanticCache

        sc = RedisSemanticCache.get_instance()
        if await sc.ensure_initialized():
            logger.info("RedisSemanticCache initialised for the RAG pipeline")
        else:
            logger.warning(
                "RedisSemanticCache not available — "
                "semantic caching strategies will be skipped. "
                "Set HUGGINGFACE_API_TOKEN and HUGGINGFACE_EMBEDDING_MODEL in .env"
            )
    except Exception:
        logger.warning(
            "RedisSemanticCache initialisation failed — "
            "semantic caching will be disabled"
        )

    yield
    await shutdown_arq_pool()
    logger.info("ARQ Redis pool closed")
    logger.info("Shutting down DocGPT API")


app = FastAPI(title="DocGPT API", version="0.1.0", lifespan=lifespan)

# ── OpenAPI Customization for Swagger Security ───────────────────────────
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="DocGPT API",
        version="0.1.0",
        routes=app.routes,
    )
    
    # Define BearerAuth security scheme
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token (e.g., Bearer <token>)"
        }
    }
    
    # Define public paths that do not require BearerAuth
    public_paths = {
        "/health",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
        "/",
    }
    
    # Apply security schema to all non-public paths
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path not in public_paths:
            for method in path_item:
                if isinstance(path_item[method], dict):
                    path_item[method]["security"] = [{"BearerAuth": []}]
                    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ── Middleware ──────────────────────────────────────────────────────────
# AuthMiddleware runs first so request.state.user is populated
app.add_middleware(AuthMiddleware)
# RateLimitMiddleware runs after auth to apply per-user global rate limits
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers — every response uses {"message": "..."} ─────────
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
# ── Routers ─────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(eval_router, prefix="/api")


@app.get("/health")
def health_check():
    """Health-check endpoint."""
    return {"status": "ok"}


# ── Import models so they are registered with SQLAlchemy metadata ──────
from app.models import document  # noqa: F401
from app.models import conversation  # noqa: F401
