"""Summary read/refresh flow, firm-scoped tenancy, and live staleness.

Uses the deterministic stub LLM (LLM_STUB_MODE=true), so refresh never hits the
network and always produces actors from the distinct senders."""

import uuid

from app.models.enums import EmailDirection, Role
from tests.conftest import auth_headers
from tests.factories import make_accountant, make_client, make_email, make_firm


def _summary_url(client_id) -> str:
    return f"/api/v1/clients/{client_id}/summary"


def _refresh_url(client_id) -> str:
    return f"/api/v1/clients/{client_id}/summary/refresh"


async def test_get_before_generation_is_stale_and_empty(client, db):
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    await make_email(db, c, day=0)
    await make_email(db, c, day=1)
    await db.commit()

    resp = await client.get(_summary_url(c.id), headers=auth_headers(acc))
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] is False
    assert body["payload"] is None
    assert body["total_emails_count"] == 2
    assert body["new_emails_count"] == 2
    assert body["is_stale"] is True


async def test_get_never_generates(client, db):
    """The read path must not create a summary as a side effect."""
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    await make_email(db, c)
    await db.commit()

    await client.get(_summary_url(c.id), headers=auth_headers(acc))
    second = await client.get(_summary_url(c.id), headers=auth_headers(acc))
    assert second.json()["generated"] is False


async def test_refresh_generates_summary(client, db):
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    await make_email(db, c, direction=EmailDirection.inbound, day=0)
    await make_email(db, c, handler=acc, direction=EmailDirection.outbound, day=1)
    await db.commit()

    resp = await client.post(_refresh_url(c.id), headers=auth_headers(acc))
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] is True
    assert body["model_used"] == "stub"
    assert body["new_emails_count"] == 0
    assert body["is_stale"] is False
    assert body["payload"]["actors"]  # stub derives actors from distinct senders


async def test_refresh_then_new_email_makes_it_stale(client, db):
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    await make_email(db, c, day=0)
    await make_email(db, c, day=1)
    await db.commit()

    await client.post(_refresh_url(c.id), headers=auth_headers(acc))

    # A new email arrives after the summary was generated.
    await make_email(db, c, day=2)
    await db.commit()

    resp = await client.get(_summary_url(c.id), headers=auth_headers(acc))
    body = resp.json()
    assert body["generated"] is True
    assert body["emails_analyzed_count"] == 2
    assert body["total_emails_count"] == 3
    assert body["new_emails_count"] == 1
    assert body["is_stale"] is True


async def test_refresh_roundtrips_through_decryption(client, db):
    """Refresh encrypts; a later GET must decrypt and return the same payload."""
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)
    await make_email(db, c)
    await db.commit()

    refreshed = (await client.post(_refresh_url(c.id), headers=auth_headers(acc))).json()
    fetched = (await client.get(_summary_url(c.id), headers=auth_headers(acc))).json()
    assert fetched["payload"] == refreshed["payload"]


async def test_cross_firm_access_returns_404(client, db):
    firm_a = await make_firm(db, name="Firm A")
    firm_b = await make_firm(db, name="Firm B")
    acc_b = await make_accountant(db, firm_b)
    client_a = await make_client(db, firm_a)
    await make_email(db, client_a)
    await db.commit()

    # Accountant in firm B tries to read firm A's client.
    resp = await client.get(_summary_url(client_a.id), headers=auth_headers(acc_b))
    assert resp.status_code == 404


async def test_unknown_client_returns_404(client, db):
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    await db.commit()

    resp = await client.get(_summary_url(uuid.uuid4()), headers=auth_headers(acc))
    assert resp.status_code == 404


async def test_refresh_with_no_emails_returns_400(client, db):
    firm = await make_firm(db)
    acc = await make_accountant(db, firm)
    c = await make_client(db, firm)  # no emails
    await db.commit()

    resp = await client.post(_refresh_url(c.id), headers=auth_headers(acc))
    assert resp.status_code == 400


async def test_superuser_can_read_any_firms_client(client, db):
    firm = await make_firm(db)
    su = await make_accountant(db, None, role=Role.superuser)
    c = await make_client(db, firm)
    await make_email(db, c)
    await db.commit()

    resp = await client.get(_summary_url(c.id), headers=auth_headers(su))
    assert resp.status_code == 200
