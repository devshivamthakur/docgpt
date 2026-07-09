import os

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    max_upload_size_mb: int = 4
    upload_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")


settings = Settings()

# Ensure the upload directory exists
os.makedirs(settings.upload_dir, exist_ok=True)
