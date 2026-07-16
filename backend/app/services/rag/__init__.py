"""Production-grade RAG pipeline package.

Provides a modular, scalable retrieval-augmented generation system.
"""

from app.services.rag.orchestrator import RagOrchestrator
from app.services.rag.retriever.retrieval import RetrievalPipeline
from app.services.rag.query_processor.processor import QueryProcessor
from app.services.rag.prompt.builder import PromptBuilder
from app.services.rag.citation import CitationExtractor
from app.services.rag.streaming import StreamManager

__all__ = [
    "RagOrchestrator",
    "RetrievalPipeline",
    "QueryProcessor",
    "PromptBuilder",
    "CitationExtractor",
    "StreamManager",
]
