from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams
from app.core.config import settings

COLLECTION_NAME = "doc_gpt_documents"

class QdrantService:
    def __init__(self):
        self.client = QdrantClient(
            api_key=settings.QDRANT_API_KEY,
            url=settings.QDRANT_URL,
        )
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        self.collection_name = COLLECTION_NAME
        self._create_collection_if_not_exists()

    def _recreate_collection(self):
        self.client.delete_collection(collection_name=self.collection_name)
        self._create_collection_if_not_exists()

    def _create_collection_if_not_exists(self):
        try:
            self.client.get_collection(collection_name=self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
                }
            )

    def get_qdrant_vector_store(self):
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
        )

# Instantiate the service
qdrant_service = QdrantService()
qdrant = qdrant_service.get_qdrant_vector_store()

