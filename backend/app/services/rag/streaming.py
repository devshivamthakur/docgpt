"""Streaming utilities for SSE-based RAG response delivery.

Provides:
- ``StreamManager``: orchestrates the token stream and emits structured
  SSE events (tokens, sources, done, error) with timeout protection.
- Helper functions for JSON-encoding SSE ``data:`` lines.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from app.services.rag.config import RagConfig

logger = logging.getLogger(__name__)


class StreamTimeoutError(Exception):
    """Raised when the stream exceeds a timeout threshold."""

    pass


class StreamManager:
    """Manages the lifecycle of an SSE RAG response stream.

    Wraps the LLM token generator with:
    - Per-token timeout (stall detection).
    - Total stream timeout.
    - Structured event emission.
    - Exception safety.
    """

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()

    async def stream_events(
        self,
        token_generator: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """Wrap a raw LLM token generator with SSE formatting and timeouts.

        Yields ``data: <json>\n\n`` formatted SSE strings for:
        - ``token`` — each token chunk.
        - ``error`` — if an error occurs.
        """
        start_time = time.monotonic()
        last_token_time = start_time

        try:
            async for token in token_generator:
                # Check total timeout
                elapsed = time.monotonic() - start_time
                if elapsed > self.config.stream_total_timeout:
                    raise StreamTimeoutError(
                        f"Stream exceeded total timeout of "
                        f"{self.config.stream_total_timeout}s"
                    )

                # Check per-token stall timeout
                token_elapsed = time.monotonic() - last_token_time
                if token_elapsed > self.config.stream_chunk_timeout:
                    raise StreamTimeoutError(
                        f"Stream stalled for {token_elapsed:.1f}s "
                        f"(timeout={self.config.stream_chunk_timeout}s)"
                    )

                last_token_time = time.monotonic()
                yield self._sse_event("token", {"content": token})

        except asyncio.CancelledError:
            logger.info("Stream cancelled by client")
            yield self._sse_error("Stream cancelled")
        except StreamTimeoutError as e:
            logger.warning("Stream timeout: %s", e)
            yield self._sse_error(str(e))
        except Exception:
            logger.exception("Unexpected stream error")
            yield self._sse_error("An unexpected error occurred during generation")

    @staticmethod
    def sources_event(sources: list[dict]) -> str:
        """Create an SSE event for source citations."""
        return StreamManager._sse_event("sources", {"sources": sources})

    @staticmethod
    def done_event(
        content: str,
        sources: list[dict],
    ) -> str:
        """Create an SSE event for stream completion."""
        return StreamManager._sse_event(
            "done",
            {
                "content": content,
                "sources": sources,
            },
        )

    @staticmethod
    def error_event(message: str) -> str:
        """Create an SSE error event."""
        return StreamManager._sse_error(message)

    # ── SSE formatting ─────────────────────────────────────────────────

    @staticmethod
    def _sse_event(event_type: str, data: dict[str, Any]) -> str:
        """Format a JSON payload as an SSE ``data:`` line."""
        payload = {"type": event_type, **data}
        return f"data: {json.dumps(payload)}\n\n"

    @staticmethod
    def _sse_error(message: str) -> str:
        """Format an error as an SSE ``data:`` line."""
        return StreamManager._sse_event("error", {"message": message})
