"""Hermetic tests for LLM provider selection and the Gemini retry policy.

No network: constructing a provider only builds a client object, and the retry
classifier is pure logic. These lock in the pluggable-provider wiring — the
factory picks the right backend from config, and only transient faults retry.
"""

import httpx
import pytest
from google.genai import errors as genai_errors

from app.core import config
from app.services.llm import factory
from app.services.llm.gemini_provider import GeminiProvider, _is_retryable
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.stub import StubProvider


@pytest.fixture
def _clear_caches():
    """Both settings and the provider are lru_cached; reset around each case."""
    config.get_settings.cache_clear()
    factory.get_llm_provider.cache_clear()
    yield
    config.get_settings.cache_clear()
    factory.get_llm_provider.cache_clear()


def _select(monkeypatch, **env) -> object:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    factory.get_llm_provider.cache_clear()
    return factory.get_llm_provider()


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("openai", OpenAIProvider), ("gemini", GeminiProvider)],
)
def test_factory_selects_configured_provider(monkeypatch, _clear_caches, provider, expected):
    got = _select(
        monkeypatch,
        LLM_STUB_MODE="false",
        LLM_PROVIDER=provider,
        LLM_API_KEY="dummy-key",
        LLM_MODEL="test-model",
    )
    assert isinstance(got, expected)


def test_factory_falls_back_to_stub_without_key(monkeypatch, _clear_caches):
    got = _select(monkeypatch, LLM_STUB_MODE="false", LLM_PROVIDER="gemini", LLM_API_KEY="")
    assert isinstance(got, StubProvider)


def test_factory_rejects_unknown_provider(monkeypatch, _clear_caches):
    with pytest.raises(ValueError, match="unknown LLM_PROVIDER"):
        _select(monkeypatch, LLM_STUB_MODE="false", LLM_PROVIDER="bogus", LLM_API_KEY="dummy-key")


def test_gemini_retries_only_transient_faults():
    # Transient -> retry
    assert _is_retryable(httpx.TimeoutException("t")) is True
    assert _is_retryable(httpx.ConnectError("c")) is True
    assert _is_retryable(genai_errors.APIError(429, {"error": {"message": "rate"}})) is True
    # Permanent -> do not retry
    assert _is_retryable(genai_errors.APIError(400, {"error": {"message": "bad"}})) is False
    assert _is_retryable(ValueError("nope")) is False
