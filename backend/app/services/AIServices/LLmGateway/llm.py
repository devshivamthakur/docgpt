import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLM:
    """Language Model wrapper supporting multiple providers (OpenAI, Google, etc.)."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.7,
        provider: str = "openai",
    ):
        self.model_name = model_name or settings.OPENAI_MODEL_NAME or "gpt-4o-mini"
        self.temperature = temperature
        self.provider = provider
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        """Create the underlying LLM instance based on the provider type."""
        logger.info(
            "Initializing LLM: provider=%s, model=%s, temperature=%s",
            self.provider,
            self.model_name,
            self.temperature,
        )
        try:
            if self.provider == "openai":
                return self._init_openai_llm()
            elif self.provider == "google":
                logger.warning("Google LLM provider is not yet implemented")
                # from langchain_google import ChatGoogleGenerativeAI
                # return ChatGoogleGenerativeAI(model=self.model_name, temperature=self.temperature)
                raise ValueError(f"Google LLM provider is not yet implemented")
            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
        except Exception:
            logger.exception(
                "Failed to initialize LLM: provider=%s, model=%s",
                self.provider,
                self.model_name,
            )
            raise

    def _init_openai_llm(self):
        """Initialize an OpenAI-compatible chat model."""
        from langchain_openai import ChatOpenAI

        logger.info(
            "Initializing OpenAI LLM: model=%s, base_url=%s",
            self.model_name,
            settings.OPENAI_BASE_URL,
        )
        try:
            return ChatOpenAI(
                model_name=self.model_name,
                openai_api_key=settings.OPENAI_API_KEY,
                openai_api_base=settings.OPENAI_BASE_URL,
                temperature=self.temperature,
            )
        except Exception:
            logger.exception("Failed to initialize OpenAI LLM")
            raise
