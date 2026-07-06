"""OpenAI GPT implementation of LLMProvider.

Uses the SDK's structured-output parsing so the model is constrained to the
`SummaryPayload` schema (no brittle JSON string-parsing on our side). Transient
failures (network, rate limit, 5xx, timeout) are retried with exponential backoff;
a bad request or auth error is not retried — it would only fail again.
"""

import time

import structlog
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.schemas.summary import SummaryContext, SummaryPayload, SummaryResult
from app.services.llm.base import LLMProvider, build_prompt

log = structlog.get_logger("app.llm")

_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def _log_retry(state: RetryCallState) -> None:
    """Emit one line per retried attempt so rate-limit/timeout patterns are visible."""
    exc = state.outcome.exception() if state.outcome else None
    log.warning(
        "llm_summarize_retry",
        attempt=state.attempt_number,
        error=type(exc).__name__ if exc else None,
    )


class OpenAIProvider(LLMProvider):
    def __init__(
        self, *, api_key: str, model: str, max_retries: int, timeout: float, temperature: float
    ):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._max_retries = max_retries
        self._temperature = temperature

    async def summarize(self, context: SummaryContext) -> SummaryResult:
        system, user = build_prompt(context)
        start = time.perf_counter()

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries + 1),
                wait=wait_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception_type(_RETRYABLE),
                before_sleep=_log_retry,
                reraise=True,
            ):
                with attempt:
                    completion = await self._client.beta.chat.completions.parse(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        response_format=SummaryPayload,
                        temperature=self._temperature,
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
        usage = getattr(completion, "usage", None)
        payload = completion.choices[0].message.parsed

        if payload is None:  # model refused or produced no parseable content
            log.error("llm_summarize_empty", model=self._model, latency_ms=latency_ms)
            raise ValueError("LLM returned no parseable summary payload")

        # Structured observability: cost (tokens), latency, and shape of the result,
        # on the same log stream that already carries the HTTP request_id.
        log.info(
            "llm_summarize",
            model=self._model,
            email_count=len(context.emails),
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            actors=len(payload.actors),
            open_action_items=len(payload.open_action_items),
        )
        return SummaryResult(payload=payload, model_used=self._model)
