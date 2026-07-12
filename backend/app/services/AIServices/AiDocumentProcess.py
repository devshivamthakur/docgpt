import logging

from langchain_core.documents import Document

from app.services.AIServices.DocumentChunking import DocumentChunker
from app.services.AIServices.DocumentParser import DocumentParser
from app.services.AIServices.schemas import ChunkType, DocumentChunk, DocumentContent, ProcessingStage
from app.services.AIServices.EmbaddingService.Qdrant import qdrant
logger = logging.getLogger(__name__)


class AiDocumentProcess:
    """Orchestrates the document processing pipeline: parse → chunk → embed → index."""

    def __init__(
        self, document_id: int, 
        file_path: str, 
        callback: callable = None, 
        original_filename: str = None
    ):
        self.document_id = document_id
        self.file_path = file_path
        self.file_extension = file_path.rsplit(".", 1)[-1].lower()
        self.callback = callback
        self.original_filename = original_filename

    def process(self) -> list[DocumentChunk]:
        """Run the full document processing pipeline."""
        logger.info(
            "Starting document processing: document_id=%d, file_path=%s",
            self.document_id,
            self.file_path,
        )
        try:
            # Stage 1: Parse
            parsed_document = self._parse()
            logger.debug("Parsing complete for document_id=%d", self.document_id)
            self._notify(ProcessingStage.PARSING)

            # Stage 2: Chunk
            chunks = self._chunk(parsed_document)
            logger.debug(
                "Chunking complete: %d chunks for document_id=%d",
                len(chunks),
                self.document_id,
            )
            self._notify(ProcessingStage.CHUNKING)

            # Stage 3: Embed
            documents = self._embed(chunks)
            logger.debug("Embedding complete for document_id=%d", self.document_id)
            self._notify(ProcessingStage.EMBEDDING)

            # Stage 4: Index
            self._index(documents)
            logger.debug("Indexing complete for document_id=%d", self.document_id)
            self._notify(ProcessingStage.INDEXING)

            logger.info(
                "Document processing finished: document_id=%d", self.document_id
            )
            return chunks
        except Exception:
            logger.exception(
                "Document processing failed: document_id=%d", self.document_id
            )
            raise

    def _notify(self, stage: ProcessingStage) -> None:
        """Invoke the progress callback if set."""
        if self.callback:
            try:
                self.callback(stage, self.document_id)
            except Exception:
                logger.warning(
                    "Progress callback failed for stage=%s, document_id=%d",
                    stage,
                    self.document_id,
                )

    def _parse(self) -> DocumentContent:
        """Parse the document file into structured content."""
        logger.debug(
            "Parsing document: document_id=%d, extension=%s",
            self.document_id,
            self.file_extension,
        )
        try:
            parser = DocumentParser(self.file_path, self.file_extension)
            return parser.get_content()
        except Exception:
            logger.exception(
                "Parse failed: document_id=%d", self.document_id
            )
            raise

    def _chunk(self, document_content: DocumentContent) -> list[DocumentChunk]:
        """Split parsed content into smaller chunks."""
        if not document_content:
            raise ValueError(
                f"Document content is empty for document_id={self.document_id}"
            )
        logger.debug(
            "Chunking document: document_id=%d", self.document_id
        )
        try:
            chunker = DocumentChunker(document_content)
            return chunker.chunk()
        except Exception:
            logger.exception(
                "Chunking failed: document_id=%d", self.document_id
            )
            raise

    def _embed(self, chunks: list[DocumentChunk]) -> list[Document]:
        """Convert document chunks into LangChain Document objects (prepares for vector storage)."""
        logger.debug(
            "Preparing %d chunks for embedding: document_id=%d",
            len(chunks),
            self.document_id,
        )
        docs: list[Document] = []
        try:
            for item in chunks:
                metadata: dict = {
                    "type": item.type,
                    "page_index": item.page_index,
                    "file": self.original_filename or "unknown",
                    "document_id": self.document_id,
                }
                if item.type == ChunkType.IMAGE:
                    metadata["image_index"] = item.chunk_index
                elif item.type == ChunkType.TABLE:
                    metadata["table_index"] = item.chunk_index

                docs.append(
                    Document(page_content=item.content, metadata=metadata)
                )

            logger.debug(
                "Prepared %d LangChain documents for document_id=%d",
                len(docs),
                self.document_id,
            )

            return docs
        except Exception:
            logger.exception(
                "Embedding preparation failed: document_id=%d",
                self.document_id,
            )
            raise

    def _index(self, docs: list[Document]) -> None:
        """Index the document chunks into the vector store (to be implemented)."""
        BATCH_SIZE = 100
        logger.debug(
            "Indexing %d documents in batches of %d: document_id=%d",
            len(docs),
            BATCH_SIZE,
            self.document_id,
        )
        try:
            for i in range(0, len(docs), BATCH_SIZE):
                batch = docs[i:i + BATCH_SIZE]
                qdrant.add_documents(batch)
                logger.debug(
                    "Indexed batch %d-%d for document_id=%d",
                    i,
                    i + len(batch) - 1,
                    self.document_id,
                )
        except Exception:
            logger.exception(
                "Indexing failed: document_id=%d", self.document_id
            )
            raise  

           