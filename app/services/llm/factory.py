"""Selects the LLM provider from configuration.

Falls back to the stub whenever stub mode is on or no API key is present, so the
system always runs — a missing key degrades to deterministic summaries rather
than crashing. Cached so the (client-holding) provider is built once per process.
"""

from functools import lru_cache

import structlog

from app.core.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.stub import StubProvider

log = structlog.get_logger("app.llm")


@lru_cache
def get_llm_provider() -> LLMProvider:
    s = get_settings()

    if s.llm_stub_mode or s.llm_provider == "stub" or not s.llm_api_key:
        if not s.llm_stub_mode and not s.llm_api_key:
            log.warning("llm_no_api_key_falling_back_to_stub")
        return StubProvider()

    # Providers are imported lazily so environments running only the stub (tests,
    # no-key demos) don't need any vendor SDK installed/loaded.
    if s.llm_provider == "openai":
        from app.services.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=s.llm_api_key,
            model=s.llm_model,
            max_retries=s.llm_max_retries,
            timeout=s.llm_timeout_seconds,
        )

    if s.llm_provider == "gemini":
        from app.services.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=s.llm_api_key,
            model=s.llm_model,
            max_retries=s.llm_max_retries,
            timeout=s.llm_timeout_seconds,
        )

    raise ValueError(f"unknown LLM_PROVIDER: {s.llm_provider!r}")
