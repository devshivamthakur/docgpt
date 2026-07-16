"""Parser for plain-text-based document formats (TXT, MD).

Reads the entire file as a single text block and wraps it in a
:class:`~app.services.ai.schemas.DocumentContent` with no images
or tables.
"""

import asyncio
import logging

from app.services.ai.parsing.base import DocumentParser
from app.services.ai.schemas import DocumentContent

logger = logging.getLogger(__name__)


class TextParser(DocumentParser):
    """Parser for ``.txt`` and ``.md`` files.

    Reads the whole file synchronously via a thread executor to avoid
    blocking the event loop.
    """

    async def get_content(self) -> DocumentContent:
        """Read the text file and return its content."""
        logger.debug("Extracting text content from: %s", self.file_path)
        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._read_file)
            logger.info("Text extraction complete: %d characters", len(text))
            return DocumentContent(
                texts=[{"page_index": 0, "text": text}],
                images=[],
                tables=[],
            )
        except Exception:
            logger.exception("Failed to extract text content from: %s", self.file_path)
            raise

    def _read_file(self) -> str:
        """Synchronous file read — called via ``run_in_executor``."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            return f.read()
