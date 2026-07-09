import json
import logging
import time

import redis as sync_redis

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "docgpt",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def publish_progress(document_id: int, status: str, progress: int, message: str = "") -> None:
    """Publish a progress update to Redis pub/sub for the WebSocket.

    Called synchronously from within Celery tasks.
    """
    try:
        r = sync_redis.from_url(settings.redis_url)
        channel = f"document:{document_id}:progress"
        payload = json.dumps({"status": status, "progress": progress, "message": message})
        r.publish(channel, payload)
        r.close()
    except Exception:
        logger.exception("Failed to publish progress to Redis")
