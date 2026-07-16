"""Utility functions for ARQ worker tasks — no imports from other task modules."""

import json
import logging

import redis as sync_redis

from app.core.config import settings

logger = logging.getLogger(__name__)


def publish_progress(
    document_id: int, status: str, progress: int, message: str = ""
) -> None:
    """Publish a progress update to Redis pub/sub for the WebSocket.

    Called synchronously from within ARQ worker tasks.
    """
    try:
        r = sync_redis.from_url(settings.redis_url)
        channel = f"document:{document_id}:progress"
        payload = json.dumps(
            {"status": status, "progress": progress, "message": message}
        )
        r.publish(channel, payload)
        r.close()
    except Exception:
        logger.exception("Failed to publish progress to Redis")
