
import logging

from langchain_classic.text_splitter import RecursiveCharacterTextSplitter

from app.services.AIServices.LLmGateway.llm import LLM
from app.services.AIServices.schemas import ChunkType, DocumentChunk, DocumentContent
from app.Prompt.DocumentParsingPrompt import image_caption_prompt, table_caption_prompt
from app.core.config import settings

logger = logging.getLogger(__name__)

class DocumentChunker:
    """Splits parsed document content into manageable chunks for embedding."""

    def __init__(
        self,
        file_content: DocumentContent,
        chunk_size: int = 550,
        overlap: int = 80,
    ):
        self.file_content = file_content
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
        )
        self.image_llm = LLM(model_name=settings.OPENAI_MODEL_NAME).llm
        self.table_llm = LLM(model_name=settings.OPENAI_MODEL_NAME).llm

    def chunk(self) -> list[DocumentChunk]:
        """Split the document content into chunks with overlap."""
        logger.info(
            "Starting chunking: chunk_size=%d, overlap=%d",
            self.chunk_size,
            self.overlap,
        )
        documents: list[DocumentChunk] = []

        try:
            # Chunk text content
            logger.debug("Chunking %d text blocks", len(self.file_content.texts))
            text_chunks = self._chunk_text(self.file_content.texts)
            documents.extend(text_chunks)
            logger.debug("Produced %d text chunks", len(text_chunks))

            # Chunk table content
            logger.debug("Chunking %d tables", len(self.file_content.tables))
            table_chunks = self._chunk_table(self.file_content.tables)
            documents.extend(table_chunks)
            logger.debug("Produced %d table chunks", len(table_chunks))

            # Chunk image content
            logger.debug("Chunking %d images", len(self.file_content.images))
            image_chunks = self._chunk_image(self.file_content.images)
            documents.extend(image_chunks)
            logger.debug("Produced %d image chunks", len(image_chunks))

            logger.info(
                "Chunking complete: %d total chunks produced", len(documents)
            )
            return documents
        except Exception:
            logger.exception("Chunking failed")
            raise

    def _chunk_text(self, texts: list[dict]) -> list[DocumentChunk]:
        """Split text blocks into smaller chunks with overlap."""
        documents: list[DocumentChunk] = []
        try:
            for _text in texts:
                page_index = _text["page_index"]
                text = _text["text"]
                chunks = self.text_splitter.split_text(text)
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

    def _chunk_table(self, tables: list[dict]) -> list[DocumentChunk]:
        """Generate captions for tables and return them as chunks."""
        documents: list[DocumentChunk] = []
        if not tables:
            return documents

        try:
            logger.debug("Generating captions for %d tables", len(tables))
            table_prompts = [
                table_caption_prompt.format(
                    table_description=t["table_df"].to_string()
                )
                for t in tables
            ]
            table_captions = self.table_llm.batch(table_prompts)
            for t, caption in zip(tables, table_captions):
                documents.append(
                    DocumentChunk(
                        page_index=t["page_index"],
                        chunk_index=t["table_index"],
                        content=caption.content
                        if hasattr(caption, "content")
                        else caption,
                        type=ChunkType.TABLE,
                        metadata={"table_index": t["table_index"]},
                    )
                )
            logger.debug("Generated %d table chunks", len(documents))
            return documents
        except Exception:
            logger.exception("Failed to chunk table content")
            raise

    def _chunk_image(self, images: list[dict]) -> list[DocumentChunk]:
        """Generate captions for images and return them as chunks."""
        documents: list[DocumentChunk] = []
        if not images:
            return documents

        try:
            logger.debug("Generating captions for %d images", len(images))
            image_prompts = [
                image_caption_prompt.format(image_description=img["image_base64"])
                for img in images
            ]
            image_captions = self.image_llm.batch(image_prompts)
            for img, caption in zip(images, image_captions):
                documents.append(
                    DocumentChunk(
                        page_index=img["page_index"],
                        chunk_index=img["image_index"],
                        content=caption.content
                        if hasattr(caption, "content")
                        else caption,
                        type=ChunkType.IMAGE,
                        metadata={"image_index": img["image_index"]},
                    )
                )
            logger.debug("Generated %d image chunks", len(documents))
            return documents
        except Exception:
            logger.exception("Failed to chunk image content")
            raise
