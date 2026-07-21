"""ARQ worker configuration and Redis pool management.

Provides:
- ``WorkerSettings`` class for the ARQ worker process.
- ``init_arq_pool`` / ``shutdown_arq_pool`` for FastAPI lifespan management.
- ``enqueue_process_document`` helper to enqueue jobs from API endpoints.
"""

import logging

from arq import create_pool, func
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Redis connection settings ──────────────────────────────────────────
redis_settings = RedisSettings.from_dsn(settings.redis_url)

# Module-level pool singleton (initialised by FastAPI lifespan)
_arq_pool: ArqRedis | None = None


# ── Pool lifecycle (called from main.py lifespan) ──────────────────────


async def init_arq_pool() -> ArqRedis:
    """Create and return the ARQ Redis pool singleton."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(redis_settings)
        logger.info("ARQ Redis pool initialised")
    return _arq_pool


async def shutdown_arq_pool() -> None:
    """Close the ARQ Redis pool singleton."""
    global _arq_pool
    if _arq_pool:
        await _arq_pool.close()
        _arq_pool = None
        logger.info("ARQ Redis pool closed")


async def get_arq_pool() -> ArqRedis:
    """Return the existing ARQ Redis pool (must be initialised first)."""
    assert _arq_pool is not None, (
        "ARQ pool not initialised — call init_arq_pool() first"
    )
    return _arq_pool


# ── Enqueue helpers (called from API endpoints) ────────────────────────


async def enqueue_process_document(
    document_id: int,
    storage_path: str,
    original_filename: str,
) -> None:
    """Enqueue a document processing job on the ARQ worker."""
    pool = await get_arq_pool()
    await pool.enqueue_job(
        "process_document",
        document_id,
        storage_path,
        original_filename,
    )


async def enqueue_eval_and_email(
    admin_email: str,
) -> None:
    """Enqueue an evaluation and email job on the ARQ worker."""
    pool = await get_arq_pool()
    await pool.enqueue_job(
        "run_eval_and_email_task",
        admin_email,
    )


# ── Worker startup / shutdown hooks ────────────────────────────────────


async def worker_startup(ctx: dict) -> None:
    """Called once when the ARQ worker starts."""
    from app.core.logging import configure_logging
    from app.db.base import Base
    from sqlalchemy import create_engine

    configure_logging()
    logger.info("ARQ worker started")

    # Create a sync engine for DB writes inside tasks
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)
    ctx["db_engine"] = engine
    logger.info("ARQ worker sync DB engine created")

    # Initialise Langfuse client for document processing tracing
    if settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_PUBLIC_KEY:
        from app.core.langfuse import get_langfuse

        get_langfuse()
        logger.info("Langfuse client initialised in ARQ worker")


async def worker_shutdown(ctx: dict) -> None:
    """Called when the ARQ worker shuts down."""
    engine = ctx.get("db_engine")
    if engine:
        engine.dispose()
    logger.info("ARQ worker shut down")


# ── WorkerSettings — tells ARQ how to run the worker ───────────────────


class WorkerSettings:
    """Minimal ARQ worker configuration.

    Run with:  ``python -m arq app.tasks.arq_app.WorkerSettings``
    """

    functions: list = [
        func("app.tasks.document_tasks.process_document", name="process_document"),
        func("app.tasks.eval_tasks.run_eval_and_email_task", name="run_eval_and_email_task"),
    ]
    redis_settings = redis_settings
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    keep_result = 3600  # keep job results for 1 hour
    max_tries = 3  # default max retries per job
    job_timeout = 600  # 10 minutes max per job
    poll_delay = 0.5  # poll Redis every 500 ms
    concurrency = 5  # process up to 5 documents in parallel
    concurrency = 3
