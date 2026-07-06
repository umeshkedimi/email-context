"""Structural grounding evals for the real LLM summarizer.

Opt-in and OUTSIDE the hermetic unit suite (`testpaths = ["tests"]`), because
evals exercise the *actual* model — they cost tokens and aren't fully
deterministic. Run them with a real key configured:

    RUN_LLM_EVALS=1 uv run pytest evals -v      # uses the configured provider

They assert two properties that matter for summarizing sensitive client mail:

  * **grounding** — every extracted actor traces back to the emails (no invented
    people);
  * **coverage** — an obvious action item / decision in the thread is captured.

Checks here are cheap and deterministic-ish: they compare the output against the
email text by string overlap. That's a tight hallucination guard but a blunt
quality signal — `test_judge.py` adds the semantic, cross-vendor view.
"""

import os
import re

import pytest

from app.schemas.summary import SummaryContext
from app.services.llm.factory import get_llm_provider
from evals.cases import EXTENSION_THREAD, W2_THREAD

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_EVALS") != "1",
    reason="LLM evals are opt-in: set RUN_LLM_EVALS=1 with a real LLM_API_KEY configured.",
)


def _corpus(ctx: SummaryContext) -> str:
    parts = [ctx.client_name, ctx.client_email]
    for e in ctx.emails:
        parts += [e.sender, e.subject or "", e.body]
    return " ".join(parts).lower()


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3]


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


@pytest.mark.parametrize("ctx", [W2_THREAD, EXTENSION_THREAD], ids=["w2", "extension"])
async def test_actors_are_grounded(ctx: SummaryContext) -> None:
    """Every extracted actor must trace back to the emails — no invented people."""
    result = await get_llm_provider().summarize(ctx)
    corpus = _corpus(ctx)
    assert result.payload.actors, "expected at least one actor"
    for actor in result.payload.actors:
        toks = _name_tokens(actor.name)
        assert toks and any(t in corpus for t in toks), (
            f"actor {actor.name!r} is not grounded in the emails (possible hallucination)"
        )


async def test_open_item_coverage_w2() -> None:
    """The clear open item (send W-2s) should be captured."""
    result = await get_llm_provider().summarize(W2_THREAD)
    haystack = _normalized(
        " ".join(i.description for i in result.payload.open_action_items)
        + " "
        + result.payload.overview
    )
    assert "w2" in haystack, "expected the W-2 action item to be captured"


async def test_decision_coverage_extension() -> None:
    """The concluded decision (file an extension) should be captured."""
    result = await get_llm_provider().summarize(EXTENSION_THREAD)
    haystack = (
        " ".join(result.payload.concluded_discussions) + " " + result.payload.overview
    ).lower()
    assert "extension" in haystack, "expected the extension decision to be captured"
