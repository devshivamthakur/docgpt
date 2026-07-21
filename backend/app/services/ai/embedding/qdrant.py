from __future__ import annotations

import logging

from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

from app.core.config import settings
from app.services.ai.llm.embedding import EmbeddingLLM

logger = logging.getLogger(__name__)

COLLECTION_NAME = "doc_gpt_collection"


class QdrantService:
    """Singleton service wrapping a shared ``QdrantClient`` connection.

    Usage
    -----
    >>> from app.services.ai.embedding.qdrant import get_qdrant_service, get_qdrant
    >>> svc = get_qdrant_service()       # QdrantService singleton
    >>> store = get_qdrant()              # QdrantVectorStore singleton
    >>> svc.delete_documents_from_collection(user_id=1, document_id=42)

    The underlying ``QdrantClient`` is created once and reused for the
    entire application lifetime.  The ``QdrantVectorStore`` is also
    created once and shared, avoiding redundant embedding-model
    initialisation.
    """

    _instance: QdrantService | None = None
    _vector_store_instance: QdrantVectorStore | None = None

    def __new__(cls, force_recreate: bool = False) -> QdrantService:
        """Return the singleton ``QdrantService``, creating it on first call."""
        if cls._instance is None:
            logger.info("Creating singleton QdrantService instance")
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(self, force_recreate: bool = False) -> None:
        """Initialise the Qdrant client and collection (idempotent after first call).

        Args:
            force_recreate: If ``True``, drop and recreate the collection
                (only has effect on the very first call).
        """
        if self._initialized:
            return

        self.client = QdrantClient(
            api_key=settings.QDRANT_API_KEY, url=settings.QDRANT_URL, timeout=60.0
        )
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        self.collection_name = COLLECTION_NAME
        self.embadding_model = EmbeddingLLM(
            model_name=settings.HUGGINGFACE_EMBEDDING_MODEL
        ).embedding_model

        if force_recreate:
            self._recreate_collection()
        else:
            self._create_collection_if_not_exists()

        self._initialized = True

    def _recreate_collection(self) -> None:
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )

    def _create_collection_if_not_exists(self) -> None:
        try:
            self.client.get_collection(collection_name=self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(size=768, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False)
                    )
                },
            )

        # Ensure payload indexes exist for filtered fields
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Create payload indexes for fields used in filters (e.g. user_id)."""
        info = self.client.get_collection(self.collection_name)
        existing = set(info.payload_schema.keys()) if info.payload_schema else set()

        if "metadata.user_id" not in existing:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.user_id",
                field_type=models.PayloadSchemaType.INTEGER,
            )

        if "metadata.document_id" not in existing:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.document_id",
                field_type=models.PayloadSchemaType.INTEGER,
            )

    def get_qdrant_vector_store(self) -> QdrantVectorStore:
        """Return (or create) the shared ``QdrantVectorStore`` singleton."""
        if QdrantService._vector_store_instance is None:
            QdrantService._vector_store_instance = QdrantVectorStore(
                client=self.client,
                collection_name=self.collection_name,
                sparse_embedding=self.sparse_embeddings,
                retrieval_mode=RetrievalMode.HYBRID,
                vector_name="dense",
                sparse_vector_name="sparse",
                embedding=self.embadding_model,
            )
        return QdrantService._vector_store_instance

    def delete_documents_from_collection(self, user_id: int, document_id: int) -> None:
        """Delete vectors for a specific document from the Qdrant collection."""
        filter_criteria = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.user_id", match=models.MatchValue(value=user_id)
                ),
                models.FieldCondition(
                    key="metadata.document_id",
                    match=models.MatchValue(value=document_id),
                ),
            ]
        )
        self.client.delete(
            collection_name=self.collection_name, points_selector=filter_criteria
        )


# ── Lazy singleton accessors ────────────────────────────────────────
# The module used to eagerly initialise these at import time, which caused
# startup failures when the HuggingFace embedding endpoint was unavailable.
# Now they are created on first access via QdrantService's own singleton.


def get_qdrant_service() -> QdrantService:
    """Return the singleton ``QdrantService``, creating it lazily."""
    return QdrantService()


def get_qdrant() -> QdrantVectorStore:
    """Return the singleton ``QdrantVectorStore``, creating it lazily."""
    return get_qdrant_service().get_qdrant_vector_store()
