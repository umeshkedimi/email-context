"""Google Gemini implementation of LLMProvider.

Mirrors `OpenAIProvider`: the model is constrained to the `SummaryPayload` schema
via Gemini's structured-output support (`response_schema`), so we never parse a
JSON string ourselves. Transient failures (5xx, rate limit, connection/timeout)
are retried with exponential backoff; a bad request or auth error is not retried.
The same `llm_summarize` observability line is emitted, so switching providers
does not change the log/metrics surface.
"""

import time

import httpx
import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.schemas.summary import SummaryContext, SummaryPayload, SummaryResult
from app.services.llm.base import LLMProvider, build_prompt

log = structlog.get_logger("app.llm")


def _is_retryable(exc: BaseException) -> bool:
    """Retry only transient faults: 5xx, rate limiting (429), and network hiccups.

    A 4xx other than 429 (bad request, auth) is a permanent error — retrying it
    would just fail the same way and waste tokens/latency.
    """
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError) and getattr(exc, "code", None) == 429:
        return True
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _log_retry(state: RetryCallState) -> None:
    """Emit one line per retried attempt so rate-limit/timeout patterns are visible."""
    exc = state.outcome.exception() if state.outcome else None
    log.warning(
        "llm_summarize_retry",
        attempt=state.attempt_number,
        error=type(exc).__name__ if exc else None,
    )


class GeminiProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, max_retries: int, timeout: float):
        # Gemini's HttpOptions timeout is in milliseconds.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )
        self._model = model
        self._max_retries = max_retries

    async def summarize(self, context: SummaryContext) -> SummaryResult:
        system, user = build_prompt(context)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=SummaryPayload,
        )
        start = time.perf_counter()

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries + 1),
                wait=wait_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception(_is_retryable),
                before_sleep=_log_retry,
                reraise=True,
            ):
                with attempt:
                    response = await self._client.aio.models.generate_content(
                        model=self._model,
                        contents=user,
                        config=config,
                    )
        except Exception as exc:
            log.error(
                "llm_summarize_failed",
                model=self._model,
                email_count=len(context.emails),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
                error=type(exc).__name__,
            )
            raise

        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        usage = getattr(response, "usage_metadata", None)
        payload = response.parsed

        if not isinstance(payload, SummaryPayload):  # blocked, refused, or unparseable
            log.error("llm_summarize_empty", model=self._model, latency_ms=latency_ms)
            raise ValueError("LLM returned no parseable summary payload")

        # Structured observability: cost (tokens), latency, and shape of the result,
        # on the same log stream that already carries the HTTP request_id.
        log.info(
            "llm_summarize",
            model=self._model,
            email_count=len(context.emails),
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            completion_tokens=getattr(usage, "candidates_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
            actors=len(payload.actors),
            open_action_items=len(payload.open_action_items),
        )
        return SummaryResult(payload=payload, model_used=self._model)
