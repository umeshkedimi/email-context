"""Login and current-user endpoint behavior, including enumeration protection."""

from app.models.enums import Role
from tests.conftest import auth_headers
from tests.factories import make_accountant, make_firm

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


async def test_login_success_returns_token(client, db):
    firm = await make_firm(db)
    await make_accountant(db, firm, email="jane@example.com", password="hunter2xyz")
    await db.commit()

    resp = await client.post(LOGIN, json={"email": "jane@example.com", "password": "hunter2xyz"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    me = await client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "jane@example.com"


async def test_wrong_password_and_unknown_email_are_indistinguishable(client, db):
    """Enumeration protection: both must return the same status and message."""
    firm = await make_firm(db)
    await make_accountant(db, firm, email="real@example.com", password="correct-pw")
    await db.commit()

    wrong_pw = await client.post(LOGIN, json={"email": "real@example.com", "password": "nope"})
    unknown = await client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope"})

    assert wrong_pw.status_code == 401
    assert unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


async def test_me_requires_a_token(client):
    resp = await client.get(ME)
    # HTTPBearer(auto_error=True) rejects a missing credential before our code runs.
    assert resp.status_code in (401, 403)


async def test_me_rejects_invalid_token(client):
    resp = await client.get(ME, headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


async def test_token_for_deleted_user_is_rejected(client, db):
    """A still-valid token whose user no longer exists must not authenticate."""
    firm = await make_firm(db)
    acc = await make_accountant(db, firm, role=Role.accountant)
    await db.commit()
    headers = auth_headers(acc)

    # Delete the account, then present its (cryptographically valid) token.
    await db.delete(acc)
    await db.commit()

    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 401


async def test_me_reflects_role_and_firm(client, db):
    firm = await make_firm(db, name="Acme CPA")
    acc = await make_accountant(db, firm, role=Role.firm_admin)
    await db.commit()

    resp = await client.get(ME, headers=auth_headers(acc))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "firm_admin"
    assert body["firm_id"] == str(firm.id)
