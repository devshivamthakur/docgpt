import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.schemas.conversation import SourceItem
from app.services.rag.retriever.helpers import retrieve as retrieve_module
from app.services.rag.source_tracking import SourceTracker


class StubQueryProcessor:
    async def process(self, query, history=None):
        return f"processed:{query}"


class StubRetriever:
    async def retrieve(self, processed_query, user_id):
        return [
            SourceItem(
                id=uuid.uuid4(),
                document_id=1,
                document_name="Alpha Report",
                page_index=2,
                chunk_index=0,
                content="Alpha content",
                score=0.91,
            )
        ]


def test_source_tracker_deduplicates_and_preserves_order():
    tracker = SourceTracker()
    first = SourceItem(
        id=uuid.uuid4(),
        document_id=1,
        document_name="Alpha Report",
        page_index=2,
        chunk_index=0,
        content="Alpha content",
        score=0.91,
    )
    second = SourceItem(
        id=uuid.uuid4(),
        document_id=2,
        document_name="Beta Report",
        page_index=5,
        chunk_index=1,
        content="Beta content",
        score=0.87,
    )

    tracker.add_sources([first, second])
    tracker.add_sources([first])

    assert [source.document_id for source in tracker.get_sources()] == [1, 2]


def test_retrieve_documents_appends_sources_to_tracker(monkeypatch):
    tracker = SourceTracker()

    monkeypatch.setattr(
        retrieve_module, "RetrievalPipeline", lambda config: StubRetriever()
    )
    monkeypatch.setattr(
        retrieve_module, "QueryProcessor", lambda config: StubQueryProcessor()
    )

    config = {"configurable": {"user_id": 7, "history": [], "source_tracker": tracker}}

    async def run_test():
        result = await retrieve_module.retrieve_documents.coroutine(
            "find alpha", config
        )
        assert "Alpha Report" in result
        assert [source.document_name for source in tracker.get_sources()] == [
            "Alpha Report"
        ]

    asyncio.run(run_test())
