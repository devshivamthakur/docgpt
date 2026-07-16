"""Dataclasses for the query processing pipeline."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcessedQuery:
    """Output of the query processing pipeline.

    Carries multiple query variants for multi-stage retrieval strategies.
    """

    original: str
    """The raw, unaltered user query."""

    normalised: str
    """Sanitized, lowercased, and filler-free query."""

    rewritten: str
    """Condensed, standalone query (may be same as normalised)."""

    expanded_queries: list[str] = field(default_factory=list)
    """Additional related queries (for HyDE-style expansion)."""

    is_question: bool = False
    """Heuristic flag — does the query look like a question?"""

    def all_queries(self) -> list[str]:
        """Return a unique list of all query variants for retrieval."""
        queries = [self.rewritten] + self.expanded_queries
        return list(dict.fromkeys(q for q in queries if q))
