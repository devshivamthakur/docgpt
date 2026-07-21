from __future__ import annotations

from app.schemas.conversation import SourceItem


class SourceTracker:
    """Collect and deduplicate sources for a single RAG run.

    This replaces ad-hoc module-level state with an explicit object that can
    be injected into the tool execution context and later consumed by the
    orchestrator after streaming completes.
    """

    def __init__(self) -> None:
        self._sources: list[SourceItem] = []
        self._seen: set[tuple[int, int | None]] = set()

    def add_sources(self, sources: list[SourceItem]) -> None:
        """Append sources in order while deduplicating by document/chunk key."""
        for source in sources:
            key = (source.document_id, source.chunk_index)
            if key in self._seen:
                continue
            self._seen.add(key)
            self._sources.append(source)

    def get_sources(self) -> list[SourceItem]:
        """Return the accumulated sources for the current run."""
        return list(self._sources)

    def reset(self) -> None:
        """Clear accumulated state for a new run."""
        self._sources.clear()
        self._seen.clear()
