import logging

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingLLM:
    """HuggingFace embedding model wrapper for generating vector embeddings."""

    def __init__(
        self,
        model_name: str | None = None,
    ):
        self.model_name = (
            model_name or settings.HUGGINGFACE_EMBEDDING_MODEL
        )
        self.embedding_model = self._initialize_embedding_model()

    def _initialize_embedding_model(self) -> HuggingFaceEndpointEmbeddings:
        """Create and return the HuggingFace embeddings model."""
        logger.debug(
            "Initializing embedding model: %s", self.model_name
        )
        try:
            if not self.model_name:
                raise ValueError(
                    "No embedding model name provided and HUGGINGFACE_EMBEDDING_MODEL is not set"
                )
            if not settings.HUGGINGFACE_API_TOKEN:
                raise ValueError("HUGGINGFACE_API_TOKEN is not configured")

            model = HuggingFaceEndpointEmbeddings(
                repo_id=self.model_name,
                huggingfacehub_api_token=settings.HUGGINGFACE_API_TOKEN,
            )
            logger.info(
                "Embedding model initialized: %s", self.model_name
            )
            return model
        except Exception:
            logger.exception(
                "Failed to initialize embedding model: %s",
                self.model_name,
            )
            raise
