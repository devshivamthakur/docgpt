"""Document chunking package.

Splits parsed document content into discrete chunks suitable for
embedding and indexing. Three independent chunking strategies are
provided:

* :mod:`text_chunker` — pure-Python text splitting (no LLM calls).
* :mod:`table_chunker` — table caption generation via LLM.
* :mod:`image_chunker` — image caption generation via multimodal LLM.

Table and image captioning both hit the LLM and can be run in
parallel for better throughput (see :mod:`app.services.ai.processing`).
"""

from app.services.ai.chunking.text_chunker import TextChunker
from app.services.ai.chunking.table_chunker import TableChunker
from app.services.ai.chunking.image_chunker import ImageChunker

__all__ = [
    "TextChunker",
    "TableChunker",
    "ImageChunker",
]
