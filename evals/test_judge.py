"""LLM-as-judge evals.

The configured provider generates a summary (`gpt-4o-mini` in prod); a stronger
model grades it (`gpt-4o` by default). Both use the same OpenAI key already
configured, so this needs no extra credential — just the opt-in flag:

    RUN_LLM_EVALS=1 uv run pytest evals/test_judge.py -v

Override the judge model with JUDGE_MODEL. Costs tokens (two calls per case),
so it stays out of CI.
"""

import os

import pytest

from app.core.config import get_settings
from app.services.llm.factory import get_llm_provider
from evals.cases import ALL_CASES, W2_THREAD
from evals.judge import OpenAIJudge

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_EVALS") != "1",
    reason="LLM evals are opt-in: set RUN_LLM_EVALS=1 with a real LLM_API_KEY configured.",
)

# Threshold for a "good" summary on the judge's 1-5 scale. 4 leaves room for
# harmless phrasing differences while still failing on real quality regressions.
_MIN_SCORE = 4


@pytest.fixture
def judge() -> OpenAIJudge:
    # Function-scoped on purpose: the async client holds a transport bound to the
    # event loop it's first used on, and pytest-asyncio gives each test its own
    # loop — a module-scoped client would break on the second test.
    s = get_settings()
    return OpenAIJudge(
        api_key=s.llm_api_key,
        model=os.getenv("JUDGE_MODEL", "gpt-4o"),
        timeout=s.llm_timeout_seconds,
    )


@pytest.mark.parametrize("ctx", [c for _, c in ALL_CASES], ids=[i for i, _ in ALL_CASES])
async def test_generated_summary_is_faithful(judge: OpenAIJudge, ctx) -> None:
    """A stronger judge model should find no invented people and high faithfulness."""
    result = await get_llm_provider().summarize(ctx)
    verdict = await judge.evaluate(ctx, result.payload)
    assert verdict.hallucinated_actors == [], (
        f"judge flagged invented actors {verdict.hallucinated_actors}: {verdict.rationale}"
    )
    assert verdict.faithfulness >= _MIN_SCORE, (
        f"low faithfulness ({verdict.faithfulness}/5): {verdict.rationale}"
    )


async def test_generated_summary_has_coverage(judge: OpenAIJudge) -> None:
    """The W-2 thread has one obvious open item; the judge should score coverage high."""
    result = await get_llm_provider().summarize(W2_THREAD)
    verdict = await judge.evaluate(W2_THREAD, result.payload)
    assert verdict.coverage >= _MIN_SCORE, (
        f"low coverage ({verdict.coverage}/5): {verdict.rationale}"
    )
