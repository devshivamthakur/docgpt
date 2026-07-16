"""Query understanding layer — rewriting, expansion, and normalisation.

Improves retrieval quality by transforming raw user queries into
more effective search queries before they reach the vector store.
"""

import logging
import re


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

        Uses rule-based compression for speed — no LLM call needed for most queries.
        Falls back to the normalised form on any error.
        """
        return self._compression_rewrite(raw_query)

    def _compression_rewrite(self, query: str) -> str:
        """Rule-based query compression.

        Strips conversational framing and extracts the core informational intent.
        """
        q = self._normalise(query)

        # Remove trailing question marks and polite endings
        q = q.rstrip("?.").strip()

        # If query is already short (< 6 words), keep as-is
        if len(q.split()) <= 6:
            return q

        # For longer queries, try to extract the core question
        # Pattern: "What/How/Why ... [topic]?" → keep the core
        match = re.match(
            r"(what|how|why|when|where|who|which|explain|describe|define|compare)\s+"
            r"((?:\w+\s+){0,10}\w+)",
            q,
            re.IGNORECASE,
        )
        if match:
            return f"{match.group(1)} {match.group(2)}"

        return q

    async def _expand(self, query: str) -> list[str]:
        """Generate related search terms for broader recall.

        This is a simplified HyDE-light approach using keyword expansion.
        """
        # Extract key nouns/phrases for keyword-level expansion
        words = query.lower().split()
        # Filter stop words
        stop_words = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "shall",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "because",
            "until",
            "while",
            "about",
            "against",
            "among",
            "throughout",
            "upon",
            "down",
            "in",
            "out",
            "on",
            "off",
            "over",
            "under",
            "up",
            "down",
            "and",
            "but",
            "if",
            "or",
            "because",
            "as",
            "while",
            "of",
            "at",
            "by",
            "for",
            "with",
            "about",
            "against",
        }
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords
