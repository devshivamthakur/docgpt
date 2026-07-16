"""Converts document chunks to LangChain ``Document`` objects and indexes
them into Qdrant in batches.
"""

import logging

from langchain_core.documents import Document

from app.core.config import settings
from app.services.ai.schemas import ChunkType, DocumentChunk
from app.services.ai.embedding.qdrant import get_qdrant

logger = logging.getLogger(__name__)

# Number of documents to index in a single Qdrant batch.
BATCH_SIZE = 100


class Indexer:
    """Builds LangChain ``Document`` objects and indexes them into Qdrant.

    Separating this from the pipeline makes it easy to test the indexing
    step in isolation or swap the vector store later.
    """

    def __init__(
        self,
        document_id: int,
        user_id: int,
        original_filename: str,
    ) -> None:
        self.document_id = document_id
        self.user_id = user_id
        self.original_filename = original_filename

    def run(self, chunks: list[DocumentChunk]) -> None:
        """Convert chunks to LangChain Documents and index in batches.

        Args:
            chunks: The document chunks to embed and index.
        """
        if not chunks:
            logger.warning("No chunks to index for document_id=%d", self.document_id)
            return

        logger.debug(
            "Indexing %d chunks: document_id=%d",
            len(chunks),
            self.document_id,
        )

        try:
            docs = [self._to_langchain_doc(chunk) for chunk in chunks]

            for i in range(0, len(docs), BATCH_SIZE):
                batch = docs[i : i + BATCH_SIZE]
                get_qdrant().add_documents(batch)
                logger.debug(
                    "Indexed batch %d-%d for document_id=%d",
                    i,
                    i + len(batch) - 1,
                    self.document_id,
                )

            logger.info(
                "Indexing complete: %d chunks for document_id=%d",
                len(chunks),
                self.document_id,
            )
        except Exception:
            logger.exception("Indexing failed: document_id=%d", self.document_id)
            raise

    def _to_langchain_doc(self, chunk: DocumentChunk) -> Document:
        """Convert a ``DocumentChunk`` to a LangChain ``Document`` with metadata."""
        metadata: dict = {
            "type": chunk.type,
            "page_index": chunk.page_index,
            "file": self.original_filename,
            "document_id": self.document_id,
            "user_id": self.user_id,
            "model": settings.HUGGINGFACE_EMBEDDING_MODEL,
        }
        if chunk.type == ChunkType.IMAGE:
            metadata["image_index"] = chunk.chunk_index
        elif chunk.type == ChunkType.TABLE:
            metadata["table_index"] = chunk.chunk_index

        return Document(page_content=chunk.content, metadata=metadata)
