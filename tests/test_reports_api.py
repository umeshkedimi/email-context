"""Firm and network reports: role gating, firm scoping, and correct rollups."""

import pytest

from app.models.enums import Role
from tests.conftest import auth_headers
from tests.factories import make_accountant, make_client, make_email, make_firm

FIRM_REPORT = "/api/v1/reports/firm"
NETWORK_REPORT = "/api/v1/reports/network"


@pytest.fixture
async def world(db):
    """Two firms with mixed client states, plus a superuser.

    Firm A: c1 (2 emails), c2 (1 email); Firm B: c3 (1 email); Empty firm: none.
    No summaries are generated, so every client is stale (never generated)."""
    firm_a = await make_firm(db, name="Firm A")
    firm_b = await make_firm(db, name="Firm B")
    firm_empty = await make_firm(db, name="Empty Firm")

    admin_a = await make_accountant(db, firm_a, role=Role.firm_admin)
    acc_a = await make_accountant(db, firm_a, role=Role.accountant)
    admin_b = await make_accountant(db, firm_b, role=Role.firm_admin)
    superuser = await make_accountant(db, None, role=Role.superuser)

    c1 = await make_client(db, firm_a, name="Client One")
    c2 = await make_client(db, firm_a, name="Client Two")
    c3 = await make_client(db, firm_b, name="Client Three")
    await make_email(db, c1, day=0)
    await make_email(db, c1, day=1)
    await make_email(db, c2, day=0)
    await make_email(db, c3, day=0)
    await db.commit()

    return {
        "firm_a": firm_a,
        "firm_b": firm_b,
        "firm_empty": firm_empty,
        "admin_a": admin_a,
        "acc_a": acc_a,
        "admin_b": admin_b,
        "superuser": superuser,
    }


async def test_firm_admin_reads_own_firm(client, world):
    resp = await client.get(FIRM_REPORT, headers=auth_headers(world["admin_a"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["firm_id"] == str(world["firm_a"].id)
    assert body["total_clients"] == 2
    assert body["total_emails"] == 3
    assert body["clients_with_summary"] == 0
    assert body["clients_stale"] == 2  # neither has a summary yet
    assert len(body["clients"]) == 2


async def test_firm_admin_ignores_firm_id_and_sees_own(client, world):
    # firm_admin passing another firm's id is treated as that firm not existing.
    resp = await client.get(
        FIRM_REPORT,
        params={"firm_id": str(world["firm_b"].id)},
        headers=auth_headers(world["admin_a"]),
    )
    assert resp.status_code == 404


async def test_accountant_forbidden_from_firm_report(client, world):
    resp = await client.get(FIRM_REPORT, headers=auth_headers(world["acc_a"]))
    assert resp.status_code == 403


async def test_superuser_firm_report_requires_firm_id(client, world):
    resp = await client.get(FIRM_REPORT, headers=auth_headers(world["superuser"]))
    assert resp.status_code == 400


async def test_superuser_firm_report_with_id(client, world):
    resp = await client.get(
        FIRM_REPORT,
        params={"firm_id": str(world["firm_b"].id)},
        headers=auth_headers(world["superuser"]),
    )
    assert resp.status_code == 200
    assert resp.json()["firm_id"] == str(world["firm_b"].id)
    assert resp.json()["total_clients"] == 1


async def test_superuser_unknown_firm_returns_404(client, world):
    import uuid

    resp = await client.get(
        FIRM_REPORT,
        params={"firm_id": str(uuid.uuid4())},
        headers=auth_headers(world["superuser"]),
    )
    assert resp.status_code == 404


async def test_network_report_aggregates_every_firm(client, world):
    resp = await client.get(NETWORK_REPORT, headers=auth_headers(world["superuser"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_firms"] == 3
    assert body["total_clients"] == 3
    assert body["total_emails"] == 4
    assert body["clients_stale"] == 3

    by_name = {f["firm_name"]: f for f in body["firms"]}
    # The empty firm must report zero across the board — no phantom stale client.
    assert by_name["Empty Firm"]["total_clients"] == 0
    assert by_name["Empty Firm"]["clients_stale"] == 0
    assert by_name["Empty Firm"]["total_emails"] == 0


async def test_network_report_forbidden_for_firm_admin(client, world):
    resp = await client.get(NETWORK_REPORT, headers=auth_headers(world["admin_a"]))
    assert resp.status_code == 403
