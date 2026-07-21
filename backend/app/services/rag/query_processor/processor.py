"""Query understanding layer — rewriting, expansion, and normalisation.

Improves retrieval quality by transforming raw user queries into
more effective search queries before they reach the vector store.
"""

import logging
import re
from typing import Any

from app.core.constants import PROVIDER_OPENAI
from app.core.sanitization import Sanitizer
from app.services.rag.config import RagConfig
from app.services.rag.query_processor.schemas import ProcessedQuery

logger = logging.getLogger(__name__)

# Common conversational fillers that don't add semantic value
_FILLER_PATTERN = re.compile(
    r"\b(?:can you|could you|please|tell me|I want to know|"
    r"how about|what about|I need|I would like|"
    r"can I ask|do you know|could you tell)\b",
    re.IGNORECASE,
)

# Question type prefixes that help with retrieval
_QUESTION_PREFIXES = (
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "explain",
    "describe",
    "define",
    "compare",
    "list",
    "give me",
    "show me",
)


class QueryProcessor:
    """Transforms raw user queries into optimised search queries.

    Features:
    - **Normalisation**: lowercasing, punctuation stripping, filler removal.
    - **Rewrite**: condenses verbose questions into compact search queries.
    - **Expansion**: generates related terms for broader recall (HyDE-light).
    - **Sub-question decomposition**: breaks complex queries into parts.
    """

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()

    async def process(
        self,
        raw_query: str,
        history: list[dict] | None = None,
    ) -> "ProcessedQuery":
        """Run the full query processing pipeline.

        Args:
            raw_query: The original user message.
            history: Recent conversation history for context.

        Returns:
            A ``ProcessedQuery`` with the original, rewritten, and expanded forms.
        """
        normalised = self._normalise(raw_query)
        rewritten = normalised
        expanded_queries: list[str] = []
        is_question = self._is_question(normalised)

        # Step 1: Rewrite (if enabled and beneficial)
        if self.config.enable_query_rewriting:
            try:
                rewritten = await self._rewrite(raw_query, history)
            except Exception:
                logger.debug("Query rewriting failed, using normalised query")
                rewritten = normalised

        # Step 2: Expand (if enabled)
        if self.config.enable_query_expansion:
            try:
                expanded_queries = await self._expand(rewritten)
            except Exception:
                logger.debug("Query expansion failed, skipping")

        logger.debug(
            "Query processed: original=%.40s, rewritten=%.40s, expansions=%d",
            raw_query,
            rewritten,
            len(expanded_queries),
        )

        return ProcessedQuery(
            original=raw_query,
            normalised=normalised,
            rewritten=rewritten,
            expanded_queries=expanded_queries,
            is_question=is_question,
        )

    def _normalise(self, query: str) -> str:
        """Clean and normalise the query for consistent retrieval.

        Applies sanitization to neutralise any prompt injection patterns
        before the query reaches the retrieval or LLM stages.
        """
        q = query.strip()
        # Sanitize — neutralise injection patterns
        sanitized = Sanitizer.sanitize_query(q)
        q = sanitized.cleaned
        # Remove filler phrases
        q = _FILLER_PATTERN.sub("", q).strip()
        # Collapse whitespace
        q = re.sub(r"\s+", " ", q)
        return q

    def _is_question(self, query: str) -> bool:
        """Heuristic check — does this look like a question?"""
        return query.endswith("?") or query.lower().startswith(_QUESTION_PREFIXES)

    async def _rewrite(
        self,
        raw_query: str,
        history: list[dict] | None = None,
    ) -> str:
        """Rewrite a verbose or context-dependent query into a standalone search query.

        Uses LLM-based query rewriting if history is present, falling back to rule-based compression.
        """
        if history:
            return await self._llm_rewrite(raw_query, history)
        return self._compression_rewrite(raw_query)

    @property
    def llm(self) -> Any:
        if not hasattr(self, "_llm") or self._llm is None:
            from app.services.ai.llm.models import LLM
            from app.core.config import settings

            model = (
                self.config.query_rewrite_model
                or settings.OPENAI_MODEL_NAME
                or "gpt-4o-mini"
            )
            self._llm = LLM(
                model_name=model if self.config.query_rewrite_model else None,
                temperature=0.0,
                provider=PROVIDER_OPENAI,
            ).llm
        return self._llm

    async def _llm_rewrite(
        self,
        raw_query: str,
        history: list[dict],
    ) -> str:
        """Use LLM to rewrite query based on conversation history."""
        # Format the history
        formatted_history = []
        for msg in history[-5:]:  # Look at last 5 messages for context
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            formatted_history.append(f"{role}: {content}")
        history_str = "\n".join(formatted_history)

        from app.Prompt.QueryProcessorPrompt import build_query_rewrite_prompt

        prompt = build_query_rewrite_prompt(history_str, raw_query)

        try:
            response = await self.llm.ainvoke(prompt)
            from app.services.rag.utils import extract_chunk_content

            rewritten = extract_chunk_content(response.content).strip()
            rewritten = rewritten.strip("\"`'")
            if rewritten:
                logger.info(
                    "LLM query rewrite: raw_query='%s' -> rewritten='%s'",
                    raw_query,
                    rewritten,
                )
                return rewritten
        except Exception as e:
            logger.warning("Failed to run LLM query rewrite: %s", e)

        return self._compression_rewrite(raw_query)

    def _compression_rewrite(self, query: str) -> str:
        """Rule-based query compression.

        Strips conversational framing and extracts the core informational intent.
        """
        q = self._normalise(query)

        # Remove trailing question marks and polite endings
        q = q.rstrip("?.").strip()
        return q

    async def _expand(self, query: str) -> list[str]:
        """HyDE (Hypothetical Document Embedding) expansion.

        Generates a short hypothetical document passage that answers the
        query, then uses that passage as an additional search query.
        This improves recall because the hypothetical document is closer
        in embedding space to real relevant documents than the query itself.

        Falls back gracefully if the LLM call fails.
        """
        try:
            hyde_passage = await self._generate_hypothetical_document(query)
            if hyde_passage and len(hyde_passage) > 20:
                logger.debug(
                    "HyDE expansion: query='%.40s' -> passage='%.60s...'",
                    query,
                    hyde_passage[:60],
                )
                return [hyde_passage]
        except Exception as e:
            logger.debug("HyDE expansion failed for '%.40s': %s", query[:40], e)

        return []

    async def _generate_hypothetical_document(self, query: str) -> str | None:
        """Call an LLM to generate a hypothetical document passage.

        The prompt asks the LLM to write a concise, factual-sounding
        passage that would answer the query, as if it came from a
        real document.  This is the core HyDE idea.
        """
        hyde_prompt = (
            "Write a concise, informative passage (2-4 sentences) that would "
            "appear in a business or financial document answering the following "
            "question. Do not refer to the question itself — just write the "
            "passage as if it were extracted from a real document.\n\n"
            f"Question: {query}\n\nPassage:"
        )

        try:
            response = await self.llm.ainvoke(hyde_prompt)
            from app.services.rag.utils import extract_chunk_content

            passage = extract_chunk_content(response.content).strip()
            passage = passage.strip('"\' \n')
            return passage if len(passage) > 15 else None
        except Exception as e:
            logger.debug("HyDE LLM call failed: %s", e)
            return None
