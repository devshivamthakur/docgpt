"""Document parsing package.

Provides a modular, strategy-based document parsing system that supports
multiple file formats (PDF, TXT, MD, DOCX). Each parser implements a common
interface defined in :mod:`base`, and the :func:`factory.create_parser`
function selects the right implementation by file extension.
"""

from app.services.ai.parsing.base import DocumentParser, ParsedDocument

__all__ = [
    "DocumentParser",
    "ParsedDocument",
]
