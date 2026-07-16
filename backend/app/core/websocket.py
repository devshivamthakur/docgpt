import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per document ID."""

    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, document_id: int, websocket: WebSocket) -> None:
        # Only accept if not already accepted
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()
        self.active_connections.setdefault(document_id, set()).add(websocket)
        logger.info(
            "WS connected for document %s (%d active)",
            document_id,
            len(self.active_connections[document_id]),
        )

    def disconnect(self, document_id: int, websocket: WebSocket) -> None:
        if document_id in self.active_connections:
            self.active_connections[document_id].discard(websocket)
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]

    async def broadcast(self, document_id: int, data: dict) -> None:
        """Send a JSON payload to all connections for a document."""
        if document_id not in self.active_connections:
            return
        payload = json.dumps(data)
        stale = set()
        for ws in self.active_connections[document_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.add(ws)
        # Clean up dead connections
        if stale:
            self.active_connections[document_id] -= stale
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]

    @property
    def active_count(self) -> int:
        return sum(len(ws) for ws in self.active_connections.values())


manager = ConnectionManager()


async def listen_redis_progress(document_id: int, websocket: WebSocket) -> None:
    """Subscribe to Redis pub/sub for document progress and forward to WS.

    Runs inside the WebSocket handler as a long-lived listener.
    """
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"document:{document_id}:progress"
        await pubsub.subscribe(channel)
        logger.info("Subscribed to Redis channel: %s", channel)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await websocket.send_json(data)
                # Terminal states — close the subscription
                if data.get("status") in ("ready", "failed"):
                    break
            except WebSocketDisconnect, RuntimeError:
                # Client disconnected or already closed — stop listening
                break
            except Exception:
                logger.exception("Error forwarding Redis message to WS")
    except Exception:
        logger.exception("Redis pub/sub listener error")
    finally:
        await pubsub.unsubscribe(channel)
        await redis_client.close()
