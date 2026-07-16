from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams
from app.core.config import settings
from app.services.ai.llm.embedding import EmbeddingLLM

COLLECTION_NAME = "doc_gpt_collection"


class QdrantService:
    def __init__(self, force_recreate=False):
        self.client = QdrantClient(
            api_key=settings.QDRANT_API_KEY, url=settings.QDRANT_URL
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

    def _recreate_collection(self):
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )

    def _create_collection_if_not_exists(self):
        try:
            self.client.get_collection(
                collection_name=self.collection_name,
            )
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

    def _ensure_payload_indexes(self):
        """Create payload indexes for fields used in filters (e.g. user_id)."""
        info = self.client.get_collection(self.collection_name)
        existing = set(info.payload_schema.keys()) if info.payload_schema else set()
        # Metadata is nested under the "metadata" key in the Qdrant payload
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

    def get_qdrant_vector_store(self):
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
            embedding=self.embadding_model,
        )

    def delete_documents_from_collection(self, user_id: int, document_id: int):
        """Delete documents from the Qdrant collection based on user_id and document_id."""
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
# Now they are created on first access.

_qdrant_service: QdrantService | None = None
_qdrant_vector_store: QdrantVectorStore | None = None


def get_qdrant_service() -> QdrantService:
    """Return the singleton ``QdrantService``, creating it lazily."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service


def get_qdrant() -> QdrantVectorStore:
    """Return the singleton ``QdrantVectorStore``, creating it lazily."""
    global _qdrant_vector_store
    if _qdrant_vector_store is None:
        _qdrant_vector_store = get_qdrant_service().get_qdrant_vector_store()
    return _qdrant_vector_store
