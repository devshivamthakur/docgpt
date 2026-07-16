"""HuggingFace embedding model wrapper with automatic fallback support.

Attempts the configured model first, then falls back through a list of
alternatives if the primary is unavailable or returns a server error.
Each model is tried with up to 3 retries and exponential back-off for
transient ``HfHubHTTPError`` (e.g. HTTP 500/503).
"""

import logging

from huggingface_hub.errors import HfHubHTTPError
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fallback embedding models tried in order if the primary model fails.
# NOTE: Qdrant was initialised with 768-dim dense vectors, so prefer
# fallbacks that also output 768-dimensions to avoid a collection rebuild.
FALLBACK_EMBEDDING_MODELS: list[str] = [
    "BAAI/bge-base-en-v1.5",  # 768-dim
    "BAAI/bge-small-en-v1.5",  # 384-dim (requires re-index)
]


def _create_hf_embedding(model_name: str) -> HuggingFaceEndpointEmbeddings:
    """Instantiate a HuggingFace endpoint embedding model."""
    if not settings.HUGGINGFACE_API_TOKEN:
        raise ValueError("HUGGINGFACE_API_TOKEN is not configured")
    return HuggingFaceEndpointEmbeddings(
        repo_id=model_name,
        huggingfacehub_api_token=settings.HUGGINGFACE_API_TOKEN,
    )


@retry(
    retry=retry_if_exception_type(HfHubHTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _create_embedding_with_retry(model_name: str) -> HuggingFaceEndpointEmbeddings:
    """Create an embedding model, retrying on transient server errors."""
    logger.info("Attempting to create embedding model: %s", model_name)
    return _create_hf_embedding(model_name)


class EmbeddingLLM:
    """HuggingFace embedding model wrapper with automatic fallback.

    Args:
        model_name: Primary model to use. Defaults to
            ``settings.HUGGINGFACE_EMBEDDING_MODEL``.
        fallback_models: Ordered list of fallback model names.
    """

    def __init__(
        self,
        model_name: str | None = None,
        fallback_models: list[str] | None = None,
    ):
        self.model_name = model_name or settings.HUGGINGFACE_EMBEDDING_MODEL
        self.fallback_models = fallback_models or FALLBACK_EMBEDDING_MODELS
        self.embedding_model = self._initialize()

    def _initialize(self) -> HuggingFaceEndpointEmbeddings:
        """Return a working embedding instance, trying fallbacks if needed."""
        if not settings.HUGGINGFACE_API_TOKEN:
            raise ValueError("HUGGINGFACE_API_TOKEN is not configured")

        models_to_try: list[str] = []
        if self.model_name:
            models_to_try.append(self.model_name)
        models_to_try.extend(m for m in self.fallback_models if m != self.model_name)

        last_error: Exception | None = None
        for model_name in models_to_try:
            try:
                logger.debug("Initializing embedding model: %s", model_name)
                model = _create_embedding_with_retry(model_name)
                logger.info("Embedding model initialized: %s", model_name)
                return model
            except HfHubHTTPError as e:
                last_error = e
                logger.warning(
                    "Embedding model %s failed with server error: %s",
                    model_name,
                    str(e),
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "Embedding model %s failed unexpectedly: %s",
                    model_name,
                    str(e),
                )

        logger.error("All embedding models failed. Tried: %s", models_to_try)
        raise RuntimeError(
            f"Failed to initialize any embedding model. "
            f"Tried: {models_to_try}. Last error: {last_error}"
        ) from last_error
