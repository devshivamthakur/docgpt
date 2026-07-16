"""Efficient prompt construction with smart context window management.

Builds the full LLM prompt by assembling system instructions, retrieved
context, conversation history, and the user query — while respecting
character/token limits and applying intelligent truncation strategies.
"""

import logging
from typing import Literal

from app.core.sanitization import Sanitizer
from app.schemas.conversation import SourceItem
from app.services.rag.config import RagConfig
from app.Prompt.RagPrompt import CONVERSATION_SUMMARY_PROMPT, CONVERSATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# ── System prompt template ─────────────────────────────────────────────


class PromptBuilder:
    """Builds optimised LLM prompts from retrieved context, history, and queries.

    Features:
    - Smart truncation of context and history within configurable limits.
    - ``head`` / ``tail`` / ``middle`` truncation strategies.
    - Pre-compiled template for fast rendering.
    - Token-aware character budgeting.
    """

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()

    def build(
        self,
        query: str,
        sources: list[SourceItem],
        history: list[dict] | None = None,
        summary: str | None = None,
    ) -> str:
        """Assemble the full RAG prompt with prompt injection defences.

        Args:
            query: The user's question (processed/rewritten).
            sources: Retrieved context sources.
            history: Recent conversation history.
            summary: Optional conversation summary.

        Returns:
            A fully-formatted prompt string ready for the LLM.
        """
        context_str = self._format_context(sources)
        history_str = self._format_history(history or [])
        summary_str = (summary or "No previous summary.").strip()

        # Sanitize document context to neutralize any embedded injections
        sanitized_context = Sanitizer.sanitize_context(context_str)
        safe_context = Sanitizer.wrap_context(
            sanitized_context.cleaned, source_label="retrieved context"
        )

        # Build the base prompt with safe content
        prompt = CONVERSATION_SYSTEM_PROMPT.format(
            context=safe_context,
            history=history_str,
            summary=summary_str,
            query=query,
        )

        # Append injection defence instructions to the system portion
        prompt = Sanitizer.build_safe_system_prompt(prompt)

        return prompt

    def build_summary_prompt(
        self,
        history: list[dict],
        previous_summary: str | None = None,
    ) -> str:
        """Build the prompt for conversation summary generation."""
        history_str = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in history
        )
        return CONVERSATION_SUMMARY_PROMPT.format(
            history=history_str,
            summary=previous_summary or "No previous summary.",
        )

    # ── Context formatting ─────────────────────────────────────────────

    def _format_context(self, sources: list[SourceItem]) -> str:
        """Format retrieved sources into a context block.

        Each source is sanitised individually to remove/neutralise any
        embedded prompt injection attempts. Applies truncation if the
        total exceeds ``max_context_chars``.
        """
        if not sources:
            return "No relevant documents found."

        context_parts: list[str] = []
        for i, src in enumerate(sources, start=1):
            if isinstance(src, str):
                logger.warning("Skipping string source at index %d: %.50s", i, src)
                context_parts.append(f"[Source {i}]: {src}")
                continue
            header = f"[Source {i}]: {src.document_name}" + (
                f" (page {src.page_index})" if src.page_index is not None else ""
            )
            # Sanitize individual source content to prevent injection via documents
            safe_content = Sanitizer.sanitize_context(src.content).cleaned
            context_parts.append(f"{header}\n{safe_content}")

        context_str = "\n\n".join(context_parts)

        if len(context_str) > self.config.max_context_chars:
            context_str = self._truncate(
                context_str,
                self.config.max_context_chars,
                strategy=self.config.context_truncation_strategy,
            )

        return context_str

    def _format_history(self, history: list[dict]) -> str:
        """Format conversation history, respecting history character limits.

        Only the most recent messages (up to ``max_history_messages``) are
        included, and the total is capped at ``max_history_chars``.
        """
        if not history:
            return "No previous messages."

        # Take only the most recent N messages
        recent = history[-self.config.max_history_messages :]

        lines: list[str] = []
        char_count = 0
        for msg in recent:
            line = f"{msg['role'].capitalize()}: {msg['content']}"
            char_count += len(line)
            if char_count > self.config.max_history_chars:
                break
            lines.append(line)

        return "\n".join(lines)

    # ── Truncation ─────────────────────────────────────────────────────

    @staticmethod
    def _truncate(
        text: str,
        max_chars: int,
        strategy: Literal["head", "tail", "middle"] = "tail",
    ) -> str:
        """Truncate text to ``max_chars`` using the given strategy.

        - ``head``: Keep the beginning, drop the end.
        - ``tail``: Keep the end, drop the beginning.
        - ``middle``: Keep the beginning and end, drop the middle.
        """
        if len(text) <= max_chars:
            return text

        if strategy == "head":
            return text[:max_chars] + "\n\n[Context truncated...]"

        if strategy == "tail":
            return "[Context truncated...]\n\n" + text[-max_chars:]

        # Middle truncation
        half = max_chars // 2
        return text[: half - 20] + "\n\n[... truncated ...]\n\n" + text[-(half - 20) :]
