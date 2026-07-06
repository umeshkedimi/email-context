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

    if s.llm_provider == "openai":
        # Imported lazily so environments running only the stub don't need the SDK.
        from app.services.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=s.llm_api_key,
            model=s.llm_model,
            max_retries=s.llm_max_retries,
            timeout=s.llm_timeout_seconds,
            temperature=s.llm_temperature,
        )

    raise ValueError(f"unknown LLM_PROVIDER: {s.llm_provider!r}")
