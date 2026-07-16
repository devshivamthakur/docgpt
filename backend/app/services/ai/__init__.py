"""AI processing pipeline — document parsing, chunking, embedding, and indexing.

Provides a modular, scalable pipeline for processing uploaded documents
through the following stages:

1. **Parsing** — extract text, images, and tables from various file formats.
2. **Chunking** — split content into embedding-friendly chunks (text, table
   captions, image captions).
3. **Indexing** — embed and store chunks in Qdrant for semantic search.

Each stage lives in its own sub-package and exposes a clean interface,
making the system easy to extend, test, and maintain.
"""

from app.services.ai.schemas import (
    ChunkType,
    DocumentChunk,
    DocumentContent,
    ProcessingStage,
)
from app.services.ai.processing.pipeline import ProcessingPipeline
from app.services.ai.parsing.factory import create_parser
from app.services.ai.parsing.base import DocumentParser, ParsedDocument
from app.services.ai.chunking.text_chunker import TextChunker
from app.services.ai.chunking.table_chunker import TableChunker
from app.services.ai.chunking.image_chunker import ImageChunker
from app.services.ai.processing.indexing import Indexer

__all__ = [
    # Pipeline orchestrator
    "ProcessingPipeline",
    # Parsing
    "create_parser",
    "DocumentParser",
    "ParsedDocument",
    # Chunking
    "TextChunker",
    "TableChunker",
    "ImageChunker",
    # Indexing
    "Indexer",
    # Schemas
    "ChunkType",
    "DocumentChunk",
    "DocumentContent",
    "ProcessingStage",
]
