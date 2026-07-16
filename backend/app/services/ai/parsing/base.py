"""Abstract base class for all document parsers.

Each parser implementation must be async-safe — CPU-bound operations
(like PDF parsing via PyMuPDF) should be offloaded to a thread executor
so the event loop is never blocked.
"""

from abc import ABC, abstractmethod

from app.services.ai.schemas import DocumentContent


class ParsedDocument(DocumentContent):
    """Alias for backward compatibility — identical to ``DocumentContent``.

    In the future this type may carry additional metadata (parsing
    duration, page count, etc.) without breaking callers.
    """

    pass


class DocumentParser(ABC):
    """Interface that all document parsers must implement.

    Each subclass handles a specific file format and is responsible for
    extracting ``texts``, ``images``, and ``tables`` from the source file.

    Usage::

        parser = PdfParser(file_path="/tmp/doc.pdf")
        content = await parser.get_content()
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    @abstractmethod
    async def get_content(self) -> DocumentContent:
        """Parse the document and return extracted content.

        Returns:
            A :class:`~app.services.ai.schemas.DocumentContent` instance
            containing lists of texts, images, and tables extracted from
            the document.
        """
        ...
