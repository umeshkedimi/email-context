"""Context-scaling behavior: token budgeting + incremental refresh.

These guard the machinery that keeps the LLM input bounded as a client's email
history grows — the budget-limited selection, the incremental-vs-full decision,
and the end-to-end refresh contract. All run against the deterministic stub LLM.
"""

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.schemas.summary import EmailForSummary, SummaryContext, SummaryPayload
from app.services.llm.base import build_prompt
from app.services.summary_service import _CHARS_PER_TOKEN, SummaryService
from tests.conftest import auth_headers
from tests.factories import make_accountant, make_client, make_email, make_firm

_BASE = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)


def _efs(day: int, body: str) -> EmailForSummary:
    return EmailForSummary(
        sender="client@example.com",
        direction="inbound",
        sent_at=_BASE + timedelta(days=day),
        subject="s",
        body=body,
    )


def _refresh_url(client_id) -> str:
    return f"/api/v1/clients/{client_id}/summary/refresh"


# --- token budgeting -------------------------------------------------------- #


async def test_within_budget_keeps_most_recent_within_cap(db):
    svc = SummaryService(db)
    # Shrink the budget so only the two newest emails fit. Each body of 40 chars
    # costs 40/4 + 40 overhead = 50 tokens; a 100-token budget admits exactly two.
    svc.settings = get_settings().model_copy(update={"summary_max_input_tokens": 100})
    emails = [_efs(day=d, body="x" * 40) for d in range(5)]  # oldest-first

    kept = svc._within_budget(emails)

    assert len(kept) == 2
    assert [e.sent_at for e in kept] == [emails[3].sent_at, emails[4].sent_at]  # newest kept


async def test_within_budget_keeps_all_when_under_cap(db):
    svc = SummaryService(db)
    emails = [_efs(day=d, body="short") for d in range(5)]
    assert svc._within_budget(emails) == emails


def test_estimate_tokens_is_char_heuristic():
    assert SummaryService._estimate_tokens("a" * 400) == 400 // _CHARS_PER_TOKEN


# --- incremental-vs-full decision ------------------------------------------- #


async def test_build_context_incremental_above_threshold(db):
    firm = await make_firm(db)
    c = await make_client(db, firm)
    emails = [await make_email(db, c, day=d) for d in range(25)]
    svc = SummaryService(db)
    prior = SummaryPayload(overview="prior state")

    ctx, mode, sent = svc._build_refresh_context(c, emails, prior, analyzed=23)

    assert mode == "incremental"
    assert sent == 2  # only the 2 emails after the high-water mark
    assert ctx.prior_summary is prior
    assert len(ctx.emails) == 2


async def test_build_context_full_below_threshold(db):
    firm = await make_firm(db)
    c = await make_client(db, firm)
    emails = [await make_email(db, c, day=d) for d in range(10)]
    svc = SummaryService(db)
    prior = SummaryPayload(overview="prior state")

    # Only 5 analyzed — below the incremental threshold, so a full pass is used.
    ctx, mode, sent = svc._build_refresh_context(c, emails, prior, analyzed=5)

    assert mode == "full"
    assert ctx.prior_summary is None
    assert sent == 10


async def test_build_context_full_when_no_prior(db):
    firm = await make_firm(db)
    c = await make_client(db, firm)
    emails = [await make_email(db, c, day=d) for d in range(30)]
    svc = SummaryService(db)

    ctx, mode, sent = svc._build_refresh_context(c, emails, prior=None, analyzed=0)

    assert mode == "full"
    assert sent == 30


# --- prompt shape ----------------------------------------------------------- #


def test_build_prompt_incremental_carries_prior_and_new_emails():
    ctx = SummaryContext(
        client_name="Acme",
        client_email="acme@example.com",
        emails=[_efs(day=0, body="new email body")],
        prior_summary=SummaryPayload(overview="prev overview text"),
    )
    system, user = build_prompt(ctx)
    assert "running summary" in system.lower()
    assert "PREVIOUS SUMMARY" in user
    assert "prev overview text" in user
    assert "NEW EMAILS" in user


def test_build_prompt_full_has_no_prior_section():
    ctx = SummaryContext(
        client_name="Acme",
        client_email="acme@example.com",
        emails=[_efs(day=0, body="only email")],
    )
    _, user = build_prompt(ctx)
    assert "PREVIOUS SUMMARY" not in user


# --- end-to-end refresh contract -------------------------------------------- #


async def test_incremental_flow_rolls_analyzed_count_forward(client, db):
    """After a full pass, a delta of new emails must refresh incrementally and
    leave the summary reflecting the entire history (analyzed == total)."""
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    for d in range(22):  # past the incremental threshold
        await make_email(db, c, day=d)
    await db.commit()

    first = (await client.post(_refresh_url(c.id), headers=auth_headers(acc))).json()
    assert first["emails_analyzed_count"] == 22

    await make_email(db, c, day=22)
    await make_email(db, c, day=23)
    await db.commit()

    resp = await client.post(_refresh_url(c.id), headers=auth_headers(acc))
    body = resp.json()
    assert resp.status_code == 200
    assert body["emails_analyzed_count"] == 24  # summary now covers all emails
    assert body["total_emails_count"] == 24
    assert body["new_emails_count"] == 0
    assert body["is_stale"] is False
    assert body["payload"]["actors"]  # stub still produced a valid payload
