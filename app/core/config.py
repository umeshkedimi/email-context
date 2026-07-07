from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env.

    Secrets never have defaults that would be safe in production; the encryption
    key and LLM API key must be provided explicitly.
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

    # LLM (provider-neutral; kept pluggable behind the LLMProvider interface)
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_stub_mode: bool = False
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 30.0
    # 0 for grounded extraction: keep summaries faithful to the emails and
    # reproducible, rather than letting the model embellish.
    llm_temperature: float = 0.0

    # Context scaling — bound the LLM input so cost, latency, and quality stay
    # controlled as a client's email history grows (see docs/DESIGN.md).
    # Rough char/token heuristic keeps us tokenizer-free; the budget is a safety
    # cap on the prompt, well under gpt-4o-mini's 128k context window.
    summary_max_input_tokens: int = 60000
    # Once a client has at least this many analyzed emails and a prior summary,
    # a refresh only feeds the *new* emails (refine the running summary) instead
    # of re-reading the whole history. Below the threshold a full pass is cheap
    # and higher-quality, so we always do it.
    incremental_refresh: bool = True
    incremental_min_prior_emails: int = 20

    # Cache
    summary_cache_ttl_seconds: int = 3600

    # Observability — OpenTelemetry tracing. Disabled by default so the app runs
    # with no collector (local, tests, CI). Enable and point at an OTLP endpoint
    # to ship traces to Jaeger/Tempo/Datadog/Honeycomb without code changes.
    otel_enabled: bool = False
    otel_service_name: str = "email-context"
    otel_exporter_otlp_endpoint: str = ""  # e.g. http://localhost:4318
    otel_console_export: bool = False  # dev: print spans to stdout, no collector

    # App
    env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
