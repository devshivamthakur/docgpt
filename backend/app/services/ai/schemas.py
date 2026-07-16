import enum

from pydantic import BaseModel


class ChunkType(str, enum.Enum):
    """Type of content within a document chunk."""

    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"


class ProcessingStage(str, enum.Enum):
    """Stages of the document processing pipeline."""

    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"


class DocumentContent(BaseModel):
    texts: list[dict]  # Each dict contains 'page_index' and 'text'
    images: list[dict]  # Each dict contains 'page_index' and 'image_path'
    tables: list[dict]  # Each dict contains 'page_index', 'table_index', and 'table_df'


class DocumentChunk(BaseModel):
    page_index: int
    chunk_index: int
    content: str
    type: ChunkType
    metadata: dict  # Additional metadata, e.g., image_path, table_index, etc.
