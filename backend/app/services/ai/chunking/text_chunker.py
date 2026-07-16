"""Pure-Python text chunking using ``RecursiveCharacterTextSplitter``.

This module is CPU-bound (no LLM calls) and safe to run synchronously
on the calling thread.
"""

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.ai.schemas import ChunkType, DocumentChunk

logger = logging.getLogger(__name__)


class TextChunker:
    """Splits text blocks into overlapping chunks for embedding.

    Uses LangChain's ``RecursiveCharacterTextSplitter`` which respects
    paragraph and sentence boundaries.
    """

    def __init__(self, chunk_size: int = 550, overlap: int = 80) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
        )

    def chunk(self, texts: list[dict]) -> list[DocumentChunk]:
        """Split a list of text blocks into smaller chunks.

        Args:
            texts: List of dicts with ``page_index`` and ``text`` keys.

        Returns:
            A flat list of ``DocumentChunk`` instances of type ``TEXT``.
        """
        documents: list[DocumentChunk] = []
        try:
            for item in texts:
                page_index = item["page_index"]
                chunks = self._splitter.split_text(item["text"])
                for chunk_index, chunk in enumerate(chunks):
                    documents.append(
                        DocumentChunk(
                            page_index=page_index,
                            chunk_index=chunk_index,
                            content=chunk,
                            type=ChunkType.TEXT,
                            metadata={},
                        )
                    )
            return documents
        except Exception:
            logger.exception("Failed to chunk text content")
            raise
