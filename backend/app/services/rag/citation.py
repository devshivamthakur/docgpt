"""Fast citation extraction from LLM-generated text.

Uses pre-compiled regex patterns and early-exit strategies to efficiently
determine which retrieved sources are cited in the generated answer.
"""

import logging
import re

from app.schemas.conversation import SourceItem

logger = logging.getLogger(__name__)

# Pre-compiled regex for the standard citation format
_CITATION_PATTERN = re.compile(
    r"\[Source:\s*(.+?)\s*(?:\(page\s*(\d+)\))?\s*\]",
    re.IGNORECASE,
)


class CitationExtractor:
    """Extracts cited sources from LLM-generated text.

    Supports two modes:
    1. **Explicit citations**: ``[Source: document_name (page N)]``.
    2. **Name mentions**: plain document name references.

    The extractor uses pre-compiled regex patterns for performance and
    avoids redundant checks by tracking already-matched sources.
    """

    def __init__(self):
        # Cache of compiled name patterns keyed by source ID
        self._name_patterns: dict[str, re.Pattern] = {}
        self._pattern_hits: int = 0

    def extract(
        self,
        text: str,
        sources: list[SourceItem],
    ) -> list[SourceItem]:
        """Find which of the given sources are cited in the generated text.

        Args:
            text: The LLM-generated answer text.
            sources: The full list of retrieved source items.

        Returns:
            A subset of ``sources`` that are cited in the text, in order
            of first appearance.
        """
        if not text or not sources:
            return []

        cited: list[SourceItem] = []
        seen_ids: set[tuple[int, int | None]] = set()

        # Phase 1: Extract explicit [Source: ...] citations
        explicit_citations = self._extract_explicit_citations(text)

        # Phase 2: Map citations back to source items
        for src in sources:
            key = (src.document_id, src.chunk_index)
            if key in seen_ids:
                continue

            # Check explicit citations
            if self._is_explicitly_cited(src, explicit_citations):
                seen_ids.add(key)
                cited.append(src)
                continue

            # Fallback: check plain name mention (slower, skip if already matched)
            if self._is_name_mentioned(text, src):
                seen_ids.add(key)
                cited.append(src)

        return cited

    def _extract_explicit_citations(self, text: str) -> list[tuple[str, int | None]]:
        """Parse all ``[Source: name (page N)]`` tags from the text.

        Returns:
            A list of ``(document_name, page_index)`` tuples.
        """
        matches = _CITATION_PATTERN.findall(text)
        results: list[tuple[str, int | None]] = []
        for name, page_str in matches:
            page = int(page_str) if page_str and page_str.isdigit() else None
            results.append((name.strip(), page))
        return results

    @staticmethod
    def _is_explicitly_cited(
        src: SourceItem,
        explicit_citations: list[tuple[str, int | None]],
    ) -> bool:
        """Check if a source appears in the explicit citation list."""
        for cited_name, cited_page in explicit_citations:
            # Check document name match (case-insensitive)
            if src.document_name.lower() == cited_name.lower():
                # If page is specified, it must match
                if cited_page is None or src.page_index == cited_page:
                    return True
        return False

    def _is_name_mentioned(self, text: str, src: SourceItem) -> bool:
        """Check if the document name is mentioned in plain text."""
        pattern = self._get_name_pattern(src.document_name)
        return bool(pattern.search(text))

    def _get_name_pattern(self, document_name: str) -> re.Pattern:
        """Get or create a pre-compiled regex for a document name.

        Caches patterns to avoid re-compilation for repeated names.
        """
        if document_name not in self._name_patterns:
            escaped = re.escape(document_name)
            self._name_patterns[document_name] = re.compile(
                escaped,
                re.IGNORECASE,
            )
        return self._name_patterns[document_name]

    def reset(self) -> None:
        """Clear the name pattern cache (e.g., between conversations)."""
        self._name_patterns.clear()
        self._pattern_hits = 0
