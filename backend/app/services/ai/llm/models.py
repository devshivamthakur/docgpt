"""Provider-agnostic LLM gateway with fallback support, retry logic, and timeouts.

Supports:
- Multiple providers: OpenAI, Anthropic, Google, local (Ollama/vLLM).
- Automatic fallback: if the primary provider fails, tries the next in the chain.
- Configurable timeouts and retries.
- Token tracking and context window management.
- Langfuse observability integration via :meth:`build_run_config`.
"""

import logging
from typing import Any

from app.core.config import settings
from app.core.constants import (
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_GOOGLE,
)


logger = logging.getLogger(__name__)

# Ordered list of (provider_name, config_key) fallback chains.
# The first provider with valid credentials is used.
PROVIDER_FALLBACK_CHAIN: list[tuple[str, str]] = [
    (PROVIDER_OPENAI, "OPENAI_API_KEY"),
    (
        PROVIDER_OPENAI_COMPATIBLE,
        "OPENAI_API_KEY",
    ),  # Generic OpenAI-compatible (vLLM, Ollama, etc.)
]

# Maximum number of retries per provider before falling back
MAX_RETRIES_PER_PROVIDER = 2


class LLM:
    """Language Model wrapper with provider fallback and retry logic.

    Usage::

        llm_wrapper = LLM(model_name="gpt-4o-mini", temperature=0.3)
        async for chunk in llm_wrapper.llm.astream(prompt):
            ...
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.7,
        provider: str | None = None,
        max_retries: int = MAX_RETRIES_PER_PROVIDER,
        request_timeout: float = 60.0,
        streaming: bool = False,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.provider = provider or settings.model_provider or PROVIDER_OPENAI
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.streaming = streaming
        self._llm: Any = None
        self.llm = self._initialize_with_fallback()

    def _initialize_with_fallback(self) -> Any:
        """Try providers in order until one succeeds.

        If the configured provider fails, falls back through the chain.
        """
        providers_to_try = self._build_provider_chain()
        last_error: Exception | None = None

        for provider_name in providers_to_try:
            try:
                logger.info(
                    "Attempting LLM init: provider=%s, model=%s",
                    provider_name,
                    self.model_name,
                )
                llm = self._init_provider(provider_name)
                if llm is not None:
                    logger.info(
                        "LLM initialized: provider=%s, model=%s",
                        provider_name,
                        self.model_name,
                    )
                    return llm
            except Exception as e:
                last_error = e
                logger.warning(
                    "Provider '%s' failed: %s. Trying next provider.",
                    provider_name,
                    e,
                )
                continue

        logger.critical("All LLM providers failed. Last error: %s", last_error)
        raise RuntimeError(
            f"Failed to initialize LLM with any provider. "
            f"Tried: {providers_to_try}. Last error: {last_error}"
        ) from last_error

    def _build_provider_chain(self) -> list[str]:
        """Build an ordered list of provider names to try."""
        chain = [self.provider]
        for prov_name, config_key in PROVIDER_FALLBACK_CHAIN:
            if prov_name != self.provider and self._has_credentials(config_key):
                chain.append(prov_name)
        return chain

    @staticmethod
    def _has_credentials(config_key: str) -> bool:
        """Check if credentials exist for a provider."""
        return bool(getattr(settings, config_key, None))

    def _init_provider(self, provider: str) -> Any:
        """Route to the appropriate provider initializer."""
        init_map = {
            PROVIDER_OPENAI: self._init_openai_llm,
            PROVIDER_OPENAI_COMPATIBLE: self._init_openai_compatible_llm,
            PROVIDER_GOOGLE: self._init_gemini_model,
        }
        initializer = init_map.get(provider)
        if initializer is None:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        return initializer()

    def _init_openai_llm(self) -> Any:
        """Initialize an OpenAI chat model with timeout."""
        from langchain_openai import ChatOpenAI

        logger.info(
            "Initializing OpenAI: model=%s, base_url=%s",
            self.model_name,
            settings.OPENAI_BASE_URL or "(default)",
        )
        return ChatOpenAI(
            model_name=self.model_name
            if self.model_name
            else settings.OPENAI_MODEL_NAME,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_BASE_URL or None,
            temperature=self.temperature,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
            streaming=self.streaming,
        )

    def _init_openai_compatible_llm(self) -> Any:
        """Initialize an OpenAI-compatible model (vLLM, Ollama, Together, etc.)."""
        from langchain_openai import ChatOpenAI

        base_url = settings.OPENAI_BASE_URL
        if not base_url:
            raise ValueError(
                "OPENAI_BASE_URL is required for openai_compatible provider"
            )

        logger.info(
            "Initializing OpenAI-compatible: model=%s, base_url=%s",
            self.model_name,
            base_url,
        )
        return ChatOpenAI(
            model_name=self.model_name,
            openai_api_key=settings.OPENAI_API_KEY or "no-key-required",
            openai_api_base=base_url,
            temperature=self.temperature,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
        )

    def _init_gemini_model(self) -> Any:
        from langchain_google_genai import ChatGoogleGenerativeAI

        logger.info(
            "Initializing OpenAI: model=%s, base_url=%s",
            self.model_name,
            settings.GEMINI_MODEL or "(default)",
        )
        return ChatGoogleGenerativeAI(
            model=self.model_name if self.model_name else settings.GEMINI_MODEL,
            api_key=settings.GEMINI_API_KEY,
            temperature=self.temperature,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
            streaming=self.streaming,
        )

    # ── Langfuse integration ──────────────────────────────────────────

    def build_run_config(
        self,
        user_id: int | str | None = None,
        session_id: str | None = None,
        trace_name: str = "llm_call",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a LangChain ``config`` dict with Langfuse tracing.

        Returns an empty dict (no tracing) if Langfuse is not configured.
        """
        if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
            return {}

        from app.core.langfuse import build_langfuse_config

        return build_langfuse_config(
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name,
            tags=tags,
        )
