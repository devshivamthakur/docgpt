"""Orchestrates the end-to-end document processing pipeline.

Stages (with parallelism for LLM-bound operations)::

    Parse ──┬── chunk_text (fast, CPU-bound) ──┐
            ├── chunk_tables (LLM) ─────────────┤── index
            └── chunk_images (LLM) ────────────┘

Text chunking is pure-Python and runs synchronously. Table and image
captioning both hit the LLM — they run **in parallel** via
:func:`asyncio.gather` to cut wall-clock time in half.
"""

import asyncio
import logging

from app.core.config import settings
from app.services.ai.schemas import (
    DocumentChunk,
    DocumentContent,
    ProcessingStage,
)
from app.services.ai.parsing.factory import create_parser
from app.services.ai.chunking.text_chunker import TextChunker
from app.services.ai.chunking.table_chunker import TableChunker
from app.services.ai.chunking.image_chunker import ImageChunker
from app.services.ai.processing.indexing import Indexer
from app.services.ai.llm.models import LLM
from app.core.constants import PROVIDER_OPENAI

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """Orchestrates document processing from raw file to indexed vectors.

    Usage::

        pipeline = ProcessingPipeline(
            document_id=42,
            file_path="/uploads/1/report.pdf",
            original_filename="report.pdf",
            user_id=1,
        )
        chunks = await pipeline.run(callback=my_progress_fn)
    """

    def __init__(
        self,
        document_id: int,
        file_path: str,
        original_filename: str | None = None,
        user_id: int | None = None,
    ) -> None:
        self.document_id = document_id
        self.file_path = file_path
        self.original_filename = original_filename or file_path.rsplit("/", 1)[-1]
        self.user_id = user_id

        # Lazy initialisation
        self._llm: LLM | None = None
        self._chunk_llm = None  # raw BaseChatModel for chunking
        self.imageProcessingLLm = None

    # ── Public API ──────────────────────────────────────────────────

    async def run(
        self,
        callback: callable | None = None,
    ) -> list[DocumentChunk]:
        """Execute the full processing pipeline.

        Args:
            callback: Optional async callable invoked after each stage
                      with ``(stage: ProcessingStage, document_id: int)``.

        Returns:
            The complete list of ``DocumentChunk`` instances produced.
        """
        logger.info(
            "Starting pipeline: document_id=%d, file_path=%s",
            self.document_id,
            self.file_path,
        )

        try:
            # ── Stage 1: Parse ──────────────────────────────────────
            parsed = await self._parse()
            await self._notify(callback, ProcessingStage.PARSING)

            # ── Stage 2: Chunk ──────────────────────────────────────
            chunks = await self._chunk(parsed)
            await self._notify(callback, ProcessingStage.CHUNKING)

            # ── Stage 3: Index ──────────────────────────────────────
            await self._index(chunks)
            await self._notify(callback, ProcessingStage.INDEXING)

            logger.info(
                "Pipeline finished: document_id=%d, %d chunks",
                self.document_id,
                len(chunks),
            )
            return chunks
        except Exception:
            logger.exception("Pipeline failed: document_id=%d", self.document_id)
            raise

    # ── Stage implementations ───────────────────────────────────────

    async def _parse(self) -> DocumentContent:
        """Parse the document using the appropriate parser."""
        parser = create_parser(self.file_path)
        return await parser.get_content()

    async def _chunk(self, parsed: DocumentContent) -> list[DocumentChunk]:
        """Run all chunking strategies and merge results."""
        # Text chunking is pure-Python, no LLM needed
        text_chunker = TextChunker()
        text_chunks = text_chunker.chunk(parsed.texts)
        logger.debug(
            "Text chunks: %d for document_id=%d", len(text_chunks), self.document_id
        )

        # Table & image captioning hit the LLM — run in parallel
        table_chunks: list[DocumentChunk] = []
        image_chunks: list[DocumentChunk] = []

        if parsed.tables or parsed.images:
            llm_raw = await self._get_chunking_llm()
            image_llm_raw = await self._get_image_processing_llm()

            table_coro = asyncio.to_thread(self._chunk_tables, llm_raw, parsed.tables)
            image_coro = asyncio.to_thread(
                self._chunk_images, image_llm_raw, parsed.images
            )
            table_chunks, image_chunks = await asyncio.gather(table_coro, image_coro)

            logger.debug(
                "LLM chunks: %d tables + %d images for document_id=%d",
                len(table_chunks),
                len(image_chunks),
                self.document_id,
            )

        return text_chunks + table_chunks + image_chunks

    def _chunk_tables(self, llm, tables: list[dict]) -> list[DocumentChunk]:
        """Run table captioning (blocking, called via thread)."""
        chunker = TableChunker(llm)
        config = self._build_langfuse_config(
            "table_captioning", ["document_processing", "table"]
        )
        return chunker.chunk(tables, config=config)

    def _chunk_images(self, llm, images: list[dict]) -> list[DocumentChunk]:
        """Run image captioning (blocking, called via thread)."""
        chunker = ImageChunker(llm)
        config = self._build_langfuse_config(
            "image_captioning", ["document_processing", "image"]
        )
        return chunker.chunk(images, config=config)

    async def _index(self, chunks: list[DocumentChunk]) -> None:
        """Embed and index all chunks into Qdrant."""
        indexer = Indexer(
            document_id=self.document_id,
            user_id=self.user_id or 0,
            original_filename=self.original_filename,
        )
        await asyncio.to_thread(indexer.run, chunks)

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_chunking_llm(self):
        """Lazily initialise and return the raw chat model for chunking."""
        if self._chunk_llm is None:
            if self._llm is None:
                self._llm = LLM(
                    model_name=settings.OPENAI_MODEL_NAME, provider=PROVIDER_OPENAI
                )
            self._chunk_llm = self._llm.llm
        return self._chunk_llm

    async def _get_image_processing_llm(self):
        if self.imageProcessingLLm is None:
            self.imageProcessingLLm = LLM(provider=settings.model_provider).llm
        return self.imageProcessingLLm

    def _build_langfuse_config(
        self,
        trace_name: str,
        tags: list[str],
    ) -> dict | None:
        """Build a LangChain config dict with Langfuse tracing."""
        if self._llm is None:
            return None
        return self._llm.build_run_config(
            user_id=self.user_id,
            session_id=str(self.document_id) if self.document_id else None,
            trace_name=trace_name,
            tags=tags,
        )

    @staticmethod
    async def _notify(
        callback: callable | None,
        stage: ProcessingStage,
    ) -> None:
        """Invoke the progress callback if set."""
        if callback is None:
            return
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(stage, None)
            else:
                callback(stage, None)
        except Exception:
            logger.warning("Progress callback failed for stage=%s", stage)
