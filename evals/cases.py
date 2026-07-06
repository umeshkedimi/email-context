"""Shared eval corpus: small, hand-verified client threads with a known ground truth.

One place for both eval styles to reason about the same inputs:
  * the structural grounding checks (`test_grounding.py`), and
  * the LLM-as-judge (`test_judge.py`).

Each thread is deliberately tiny and unambiguous so the "right" summary is
obvious to a human reviewer — which is what lets us assert on the output.
"""

from datetime import UTC, datetime

from app.schemas.summary import EmailForSummary, SummaryContext


def _email(sender: str, direction: str, subject: str, body: str, day: int) -> EmailForSummary:
    return EmailForSummary(
        sender=sender,
        direction=direction,
        subject=subject,
        body=body,
        sent_at=datetime(2026, 1, day, 9, 0, tzinfo=UTC),
    )


# A clear open action item: the client still owes their W-2s.
W2_THREAD = SummaryContext(
    client_name="Jane Hartley",
    client_email="jane.hartley@example.com",
    emails=[
        _email(
            "diane.sterling@sterlingvance.com",
            "outbound",
            "Kicking off your 2024 return",
            "Hi Jane, to begin your 2024 tax return please send your W-2 forms when you can.\n"
            "Best,\nDiane Sterling",
            5,
        ),
        _email(
            "jane.hartley@example.com",
            "inbound",
            "Re: Kicking off your 2024 return",
            "Thanks Diane. I'll send the W-2 by Friday. We are filing jointly with my husband "
            "this year.\nJane Hartley",
            6,
        ),
    ],
)

# A concluded decision: file an extension; nothing owed by the client right now.
EXTENSION_THREAD = SummaryContext(
    client_name="Grant Okafor",
    client_email="grant.okafor@example.com",
    emails=[
        _email(
            "grant.okafor@example.com",
            "inbound",
            "Brokerage forms delayed",
            "Hi Marcus, I don't think I'll have my brokerage 1099s in time. Can we file an "
            "extension?\nThanks,\nGrant Okafor",
            5,
        ),
        _email(
            "marcus.webb@sterlingvance.com",
            "outbound",
            "Re: Brokerage forms delayed",
            "Yes, we'll file Form 4868 for a six-month extension. No action needed from you now.\n"
            "Best,\nMarcus Webb",
            6,
        ),
    ],
)

# (id, context) pairs for parametrized evals.
ALL_CASES: list[tuple[str, SummaryContext]] = [
    ("w2", W2_THREAD),
    ("extension", EXTENSION_THREAD),
]
