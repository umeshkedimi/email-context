"""Cross-vendor LLM-as-judge evals.

The configured provider (OpenAI, prod-like) generates a summary; Gemini grades it.
Using a different vendor as judge avoids the self-preference bias that inflates
scores when a model evaluates its own output.

Doubly opt-in — costs tokens on two vendors and needs two keys:

    RUN_LLM_EVALS=1 GEMINI_API_KEY=... uv run pytest evals/test_judge.py -v

Skips cleanly (not fails) when either flag/key is absent, so `make eval` still
runs the cheap structural checks with just an OpenAI key.
"""

import os

import pytest

from app.services.llm.factory import get_llm_provider
from evals.cases import ALL_CASES, W2_THREAD
from evals.judge import GeminiJudge

_GEMINI_KEY = os.getenv("GEMINI_API_KEY")

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_LLM_EVALS") != "1",
        reason="LLM evals are opt-in: set RUN_LLM_EVALS=1.",
    ),
    pytest.mark.skipif(
        not _GEMINI_KEY,
        reason="LLM-as-judge needs a Gemini key: set GEMINI_API_KEY.",
    ),
]

# Threshold for a "good" summary on the judge's 1-5 scale. 4 leaves room for
# harmless phrasing differences while still failing on real quality regressions.
_MIN_SCORE = 4


@pytest.fixture
def judge() -> GeminiJudge:
    # Function-scoped on purpose: the Gemini client holds an async transport bound
    # to the event loop it's first used on, and pytest-asyncio gives each test its
    # own loop — a module-scoped client would break on the second test.
    return GeminiJudge(
        api_key=_GEMINI_KEY,
        model=os.getenv("JUDGE_MODEL", "gemini-2.0-flash"),
    )


@pytest.mark.parametrize("ctx", [c for _, c in ALL_CASES], ids=[i for i, _ in ALL_CASES])
async def test_generated_summary_is_faithful(judge: GeminiJudge, ctx) -> None:
    """An independent judge should find no invented people and high faithfulness."""
    result = await get_llm_provider().summarize(ctx)
    verdict = await judge.evaluate(ctx, result.payload)
    assert verdict.hallucinated_actors == [], (
        f"judge flagged invented actors {verdict.hallucinated_actors}: {verdict.rationale}"
    )
    assert verdict.faithfulness >= _MIN_SCORE, (
        f"low faithfulness ({verdict.faithfulness}/5): {verdict.rationale}"
    )


async def test_generated_summary_has_coverage(judge: GeminiJudge) -> None:
    """The W-2 thread has one obvious open item; the judge should score coverage high."""
    result = await get_llm_provider().summarize(W2_THREAD)
    verdict = await judge.evaluate(W2_THREAD, result.payload)
    assert verdict.coverage >= _MIN_SCORE, (
        f"low coverage ({verdict.coverage}/5): {verdict.rationale}"
    )
