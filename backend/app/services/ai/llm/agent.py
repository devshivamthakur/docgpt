"""Agent creation utilities using langchain's ``create_agent`` API.

Provides factory functions for creating LangGraph-based agents
with the new ``create_agent`` API from ``langchain.agents``.
"""

from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph


def create_rag_agent(
    model: BaseChatModel | str,
    tools: Sequence[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    name: str | None = "rag_agent",
    **kwargs: Any,
) -> CompiledStateGraph:
    """Create a RAG agent using langchain's ``create_agent``.

    The resulting :class:`~langgraph.graph.state.CompiledStateGraph` runs a
    tool-calling loop: the model generates responses or tool calls, tools are
    executed, and the loop continues until the model produces a final answer.

    Args:
        model: The chat model (instance or name string).
        tools: Tools available to the agent (e.g. retrieval tools).
        system_prompt: System prompt that defines agent behaviour.
        name: Name for the compiled graph (visible in traces).
        **kwargs: Extra arguments forwarded to ``create_agent``.

    Returns:
        A compiled LangGraph state graph ready for streaming.
    """
    return create_agent(
        model=model,
        tools=tools if tools else [],
        system_prompt=system_prompt,
        name=name,
        **kwargs,
    )
