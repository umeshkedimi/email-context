"""Small async factories for building test data directly through the ORM.

Each returns a flushed instance so foreign keys resolve; the caller commits when
the data needs to be visible to a separate session (i.e. the HTTP client)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.models.accountant import Accountant
from app.models.client import Client
from app.models.email import Email
from app.models.enums import EmailDirection, Role
from app.models.firm import Firm

_BASE = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)


async def make_firm(db, name: str = "Test Firm") -> Firm:
    firm = Firm(id=uuid.uuid4(), name=name)
    db.add(firm)
    await db.flush()
    return firm


async def make_accountant(
    db,
    firm: Firm | None,
    *,
    role: Role = Role.accountant,
    email: str | None = None,
    password: str = "secret-pw",
) -> Accountant:
    acc = Accountant(
        id=uuid.uuid4(),
        firm_id=firm.id if firm else None,
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        name="Test User",
        role=role,
        password_hash=hash_password(password),
    )
    db.add(acc)
    await db.flush()
    return acc


async def make_client(
    db, firm: Firm, *, name: str = "Test Client", email: str | None = None
) -> Client:
    client = Client(
        id=uuid.uuid4(),
        firm_id=firm.id,
        name=name,
        email=email or f"client-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(client)
    await db.flush()
    return client


async def make_email(
    db,
    client: Client,
    *,
    handler: Accountant | None = None,
    direction: EmailDirection = EmailDirection.inbound,
    day: int = 0,
    subject: str = "Question about my return",
    body: str = "Can you help me with my taxes?",
) -> Email:
    outbound = direction == EmailDirection.outbound
    email = Email(
        id=uuid.uuid4(),
        firm_id=client.firm_id,
        client_id=client.id,
        accountant_id=handler.id if (handler and outbound) else None,
        thread_id="thread-1",
        direction=direction,
        sender=(handler.email if (handler and outbound) else client.email),
        subject=subject,
        body=body,
        sent_at=_BASE + timedelta(days=day),
    )
    db.add(email)
    await db.flush()
    return email
