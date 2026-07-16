"""Langfuse observability integration for DocGPT.

Provides a single public entry point -- :func:`build_langfuse_config` --
that returns a LangChain ``config`` dict ready to pass to ``invoke``,
``astream``, or ``batch``.  All traces belong to the ``docgpt`` project
for easy filtering in the Langfuse dashboard.

Usage::

    from app.core.langfuse import build_langfuse_config

    config = build_langfuse_config(
        user_id=current_user.id,
        session_id=str(conversation_id),
        trace_name="rag_answer",
        tags=["rag", "streaming"],
    )
    async for chunk in llm.astream(prompt, config=config):
        ...
"""

import logging
from typing import Any

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_NAME = "docgpt"
"""Langfuse project name -- applied as a tag on every trace."""

_BASE_TAGS = ["docgpt", PROJECT_NAME]
"""Tags applied to every trace emitted by this module."""

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse:
    """Return the global ``Langfuse`` client singleton (lazily initialised)."""
    global _langfuse  # noqa: PLW0603
    if _langfuse is None:
        _langfuse = Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
            environment=settings.environment,
        )
        logger.info(
            "Langfuse client initialised (host=%s, env=%s)",
            settings.LANGFUSE_HOST,
            settings.environment,
        )
    return _langfuse


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_langfuse_config(
    user_id: int | str | None = None,
    session_id: str | None = None,
    trace_name: str = "docgpt_trace",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Build a LangChain ``config`` dict with Langfuse tracing.

    The returned dict has three keys that the LangChain runtime
    recognises::

        {"callbacks": [handler], "metadata": {...}, "tags": [...]}

    The ``metadata`` dict uses the ``langfuse_*`` keys that the
    ``CallbackHandler`` promotes to top-level trace attributes
    (``langfuse_user_id``, ``langfuse_session_id``,
    ``langfuse_trace_name``, ``langfuse_tags``).

    Parameters
    ----------
    user_id:
        Authenticated user identifier.  Attached to the trace as
        ``langfuse_user_id``.
    session_id:
        Logical session -- typically the conversation ID as a string.
        Attached as ``langfuse_session_id``.
    trace_name:
        Human-readable name shown in the Langfuse dashboard.
    tags:
        Additional tags merged with the project defaults (``docgpt``).
    """
    get_langfuse()

    merged_tags = list(set((tags or []) + _BASE_TAGS))

    metadata: dict[str, Any] = {}
    if user_id is not None:
        metadata["langfuse_user_id"] = str(user_id)
    if session_id is not None:
        metadata["langfuse_session_id"] = session_id
    if trace_name is not None:
        metadata["langfuse_trace_name"] = trace_name
    metadata["langfuse_tags"] = merged_tags

    return {
        "callbacks": [CallbackHandler()],
        "metadata": metadata,
        "tags": merged_tags,
    }
