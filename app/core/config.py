from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env.

    Secrets never have defaults that would be safe in production; the encryption
    key and Gemini key must be provided explicitly.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database & cache
    database_url: str = "postgresql+psycopg://ec_user:ec_pass@localhost:5432/email_context"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Encryption at rest
    summary_encryption_key: str = ""  # base64-encoded 32 bytes
    summary_encryption_key_version: int = 1

    # LLM
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_stub_mode: bool = False

    # Cache
    summary_cache_ttl_seconds: int = 3600

    # App
    env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
