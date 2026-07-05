"""OpenAI GPT implementation of LLMProvider.

Uses the SDK's structured-output parsing so the model is constrained to the
`SummaryPayload` schema (no brittle JSON string-parsing on our side). Transient
failures (network, rate limit, 5xx, timeout) are retried with exponential backoff;
a bad request or auth error is not retried — it would only fail again.
"""

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
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.schemas.summary import SummaryContext, SummaryPayload, SummaryResult
from app.services.llm.base import LLMProvider, build_prompt

log = structlog.get_logger("app.llm")

_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class OpenAIProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, max_retries: int, timeout: float):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._max_retries = max_retries

    async def summarize(self, context: SummaryContext) -> SummaryResult:
        system, user = build_prompt(context)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
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
                )

        payload = completion.choices[0].message.parsed
        if payload is None:  # model refused or produced no parseable content
            raise ValueError("LLM returned no parseable summary payload")
        return SummaryResult(payload=payload, model_used=self._model)
