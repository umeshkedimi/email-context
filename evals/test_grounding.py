"""Grounding evals for the real LLM summarizer.

Opt-in and OUTSIDE the hermetic unit suite (`testpaths = ["tests"]`), because
evals exercise the *actual* model — they cost tokens and aren't fully
deterministic. Run them with a real key configured:

    RUN_LLM_EVALS=1 uv run pytest evals -v      # uses the configured provider

They assert two properties that matter for summarizing sensitive client mail:

  * **grounding** — every extracted actor traces back to the emails (no invented
    people);
  * **coverage** — an obvious action item / decision in the thread is captured.

Checks are lenient on wording (a proxy for a full judge/human-label eval) and
tight on hallucination.
"""

import os
import re
from datetime import UTC, datetime

import pytest

from app.schemas.summary import EmailForSummary, SummaryContext
from app.services.llm.factory import get_llm_provider

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_EVALS") != "1",
    reason="LLM evals are opt-in: set RUN_LLM_EVALS=1 with a real LLM_API_KEY configured.",
)


def _email(sender: str, direction: str, subject: str, body: str, day: int) -> EmailForSummary:
    return EmailForSummary(
        sender=sender,
        direction=direction,
        subject=subject,
        body=body,
        sent_at=datetime(2026, 1, day, 9, 0, tzinfo=UTC),
    )


W2_THREAD = SummaryContext(
    client_name="Jane Hartley",
    client_email="jane.hartley@example.com",
    emails=[
        _email(
            "diane.sterling@sterlingvance.com",
            "outbound",
            "Kicking off your 2024 return",
            "Hi Jane, to begin your 2024 tax return please send your W-2 forms when you can.",
            5,
        ),
        _email(
            "jane.hartley@example.com",
            "inbound",
            "Re: Kicking off your 2024 return",
            "Thanks Diane. I'll send the W-2 by Friday. We are filing jointly with my husband "
            "this year.",
            6,
        ),
    ],
)

EXTENSION_THREAD = SummaryContext(
    client_name="Grant Okafor",
    client_email="grant.okafor@example.com",
    emails=[
        _email(
            "grant.okafor@example.com",
            "inbound",
            "Brokerage forms delayed",
            "I don't think I'll have my brokerage 1099s in time. Can we file an extension?",
            5,
        ),
        _email(
            "marcus.webb@sterlingvance.com",
            "outbound",
            "Re: Brokerage forms delayed",
            "Yes, we'll file Form 4868 for a six-month extension. No action needed from you now.",
            6,
        ),
    ],
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
