import os

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import PROVIDER_OPENAI


class Settings(BaseSettings):
    app_name: str = "DocGPT API"
    api_v1_prefix: str = "/api"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://docgpt:docgpt@localhost:5432/docgpt"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    max_upload_size_mb: int = 50
    storage_quota_bytes: int = 1_073_741_824  # 1 GB per user
    upload_dir: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads"
    )
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    OPENAI_MODEL_NAME: str = ""
    model_provider: str = PROVIDER_OPENAI
    HUGGINGFACE_API_TOKEN: str = ""
    HUGGINGFACE_EMBEDDING_MODEL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_URL: str = ""
    GEMINI_MODEL: str = ""
    GEMINI_API_KEY: str = ""

    # ── Computed ───────────────────────────────────────────────────────
    @computed_field
    @property
    def selected_model(self) -> str:
        """Return the active model name based on the current provider."""
        if self.model_provider == PROVIDER_OPENAI:
            return self.OPENAI_MODEL_NAME
        return self.GEMINI_MODEL

    # ── Langfuse Observability ─────────────────────────────────────────
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://us.cloud.langfuse.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")


settings = Settings()

# Ensure the upload directory exists
os.makedirs(settings.upload_dir, exist_ok=True)
