"""Parser factory — selects the right parser implementation by file extension.

New parsers can be registered here without changing any calling code.
"""

import logging

from app.services.ai.parsing.base import DocumentParser
from app.services.ai.parsing.pdf_parser import PdfParser
from app.services.ai.parsing.text_parser import TextParser

logger = logging.getLogger(__name__)

# Registry mapping file extensions to parser classes.
# Add new parsers here as they are implemented.
_PARSER_REGISTRY: dict[str, type[DocumentParser]] = {
    ".pdf": PdfParser,
    ".txt": TextParser,
    ".md": TextParser,
    ".docx": TextParser,  # fallback — dedicated DocxParser pending
    ".doc": TextParser,  # fallback
}


def create_parser(file_path: str) -> DocumentParser:
    """Return the appropriate parser for *file_path* based on its extension.

    Args:
        file_path: Absolute or relative path to the document.

    Returns:
        A :class:`DocumentParser` subclass instance.

    Raises:
        ValueError: If the file extension is not supported.
    """
    import os

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    parser_cls = _PARSER_REGISTRY.get(ext)
    if parser_cls is None:
        supported = ", ".join(sorted(_PARSER_REGISTRY))
        raise ValueError(
            f"Unsupported file extension '{ext}' for: {file_path}. "
            f"Supported extensions: {supported}"
        )

    logger.debug("Created parser %s for: %s", parser_cls.__name__, file_path)
    return parser_cls(file_path)
