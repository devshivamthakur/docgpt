"""Document processing pipeline.

Orchestrates the end-to-end flow: parse → chunk (with parallelism) → index.
"""

from app.services.ai.processing.pipeline import ProcessingPipeline
from app.services.ai.processing.indexing import Indexer

__all__ = [
    "ProcessingPipeline",
    "Indexer",
]
