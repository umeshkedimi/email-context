"""Seed the database with a realistic, demo-ready dataset.

Idempotent: it wipes the app tables and re-inserts a fresh, deterministic-looking
world of two CPA firms, their staff, clients, and ~40 tax-season emails, then
pre-generates a few summaries through the *real* SummaryService so the reports
and dashboard have something to show on first boot.

Client states are chosen to exercise every path a reviewer will click:
  - summaries that are fresh (analyzed == total),
  - one summary that is stale (a late email arrives after it was generated),
  - clients with no summary yet.

Summaries are produced by whatever LLM provider is configured — the deterministic
stub when no API key is set (so the seed runs keyless), or the real model if a
key is present.

Run from the repo root:  uv run python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Standalone script: make the repo root importable regardless of the caller's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.accountant import Accountant  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.email import Email  # noqa: E402
from app.models.email_summary import EmailSummary  # noqa: E402
from app.models.enums import EmailDirection, Role  # noqa: E402
from app.models.firm import Firm  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402
from app.services.summary_service import SummaryService  # noqa: E402

# Demo accounts only — this is throwaway seed data, not a real credential.
DEMO_PASSWORD = "Demo1234!"

# Tax season 2025 filings land in early 2026; anchor the threads there.
BASE = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Static dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PersonSpec:
    key: str
    name: str
    email: str
    role: Role


@dataclass(frozen=True)
class FirmSpec:
    key: str
    name: str
    people: list[PersonSpec]


@dataclass(frozen=True)
class EmailSpec:
    day: int
    from_client: bool  # inbound (client -> firm) if True, else outbound
    subject: str
    body: str


@dataclass(frozen=True)
class ClientSpec:
    key: str
    firm_key: str
    handler_key: str  # accountant who corresponds with them
    name: str
    email: str
    thread_id: str
    emails: list[EmailSpec]
    pregenerate: bool = False
    # Emails that "arrive" after the summary is generated — used to make a client
    # deliberately stale so live-staleness is visible in the reports.
    late_emails: list[EmailSpec] = field(default_factory=list)


FIRMS = [
    FirmSpec(
        key="sterling",
        name="Sterling & Vance CPAs",
        people=[
            PersonSpec(
                "diane", "Diane Sterling", "diane.sterling@sterlingvance.com", Role.firm_admin
            ),
            PersonSpec("marcus", "Marcus Webb", "marcus.webb@sterlingvance.com", Role.accountant),
            PersonSpec("priya", "Priya Nair", "priya.nair@sterlingvance.com", Role.accountant),
        ],
    ),
    FirmSpec(
        key="northwind",
        name="Northwind Tax Group",
        people=[
            PersonSpec("alan", "Alan Brooks", "alan.brooks@northwindtax.com", Role.firm_admin),
            PersonSpec("sofia", "Sofia Reyes", "sofia.reyes@northwindtax.com", Role.accountant),
        ],
    ),
]

FIRMS_BY_KEY = {f.key: f for f in FIRMS}

# Not bound to any firm — operates across the whole Ascend network.
SUPERUSER = PersonSpec("ascend", "Ascend Platform Ops", "platform@ascendcpa.com", Role.superuser)


CLIENTS = [
    ClientSpec(
        key="brightwave",
        firm_key="sterling",
        handler_key="marcus",
        name="Brightwave Design LLC",
        email="jordan@brightwavedesign.com",
        thread_id="brightwave-2026-estimates",
        pregenerate=True,
        emails=[
            EmailSpec(
                0,
                True,
                "Q1 estimated payment for Brightwave",
                "Hi Marcus, we had a strong Q4 and I want to make sure our Q1 2026 "
                "estimated payment is right. How much should Brightwave send in?",
            ),
            EmailSpec(
                1,
                False,
                "Re: Q1 estimated payment for Brightwave",
                "Happy to help, Jordan. Can you send your latest year-to-date P&L and "
                "the current owner payroll figures so I can size the estimate?",
            ),
            EmailSpec(
                2,
                True,
                "Re: Q1 estimated payment for Brightwave",
                "Sure — revenue is about $220k year to date and my salary through the "
                "S-corp is running at $60k annually.",
            ),
            EmailSpec(
                3,
                False,
                "Re: Q1 estimated payment for Brightwave",
                "Thanks. Based on that I estimate roughly $9,500 in federal estimated tax "
                "for Q1. Pay via EFTPS by April 15; I'll email the voucher details.",
            ),
            EmailSpec(
                5,
                True,
                "Re: Q1 estimated payment for Brightwave",
                "Paid — thank you. Separately, am I taking enough salary? I've heard the "
                "IRS cares about reasonable compensation for S-corp owners.",
            ),
            EmailSpec(
                6,
                False,
                "Re: Q1 estimated payment for Brightwave",
                "Good instinct. For your revenue and role I'd raise the salary to about "
                "$85k to be defensible on reasonable comp. We'd adjust payroll going forward.",
            ),
            EmailSpec(
                8,
                True,
                "Re: Q1 estimated payment for Brightwave",
                "Makes sense, let's do $85k. Can you coordinate the change with our "
                "bookkeeper, Dana?",
            ),
            EmailSpec(
                9,
                False,
                "Re: Q1 estimated payment for Brightwave",
                "Will do — I'll reach out to Dana to update the payroll run. I think we've "
                "settled the reasonable-comp question.",
            ),
        ],
    ),
    ClientSpec(
        key="hartley",
        firm_key="sterling",
        handler_key="priya",
        name="Hartley Family",
        email="tom.hartley@gmail.com",
        thread_id="hartley-1040-2025",
        pregenerate=True,
        emails=[
            EmailSpec(
                0,
                True,
                "Received an IRS CP2000 notice",
                "Priya, we got a CP2000 notice from the IRS for our 2024 return. It says we "
                "underreported about $4,200 of brokerage income. We're worried — can you look?",
            ),
            EmailSpec(
                1,
                False,
                "Re: Received an IRS CP2000 notice",
                "Don't worry, these are common and usually resolvable. Please forward the "
                "notice PDF and your 2024 1099-B from the broker.",
            ),
            EmailSpec(
                2,
                True,
                "Re: Received an IRS CP2000 notice",
                "Attached. The broker was Fidelity. I'm fairly sure we already reported those "
                "sales when we filed.",
            ),
            EmailSpec(
                3,
                False,
                "Re: Received an IRS CP2000 notice",
                "You did report the sales — but the 1099-B was missing cost basis, so the IRS "
                "assumed a $0 basis and taxed the full proceeds. I'll draft a response with the "
                "correct basis showing only a small gain.",
            ),
            EmailSpec(
                5,
                False,
                "Re: Received an IRS CP2000 notice",
                "Here's the drafted CP2000 response letter with a basis schedule. Please review "
                "and sign, and I'll mail it to the IRS.",
            ),
            EmailSpec(
                6,
                True,
                "Re: Received an IRS CP2000 notice",
                "Signed and returned. Thank you! While we're at it, when should we start our "
                "2025 return?",
            ),
            EmailSpec(
                7,
                False,
                "Re: Received an IRS CP2000 notice",
                "Great — response is going in the mail today. Your 2025 return is on track; "
                "I'll send the organizer next week.",
            ),
        ],
        late_emails=[
            EmailSpec(
                14,
                True,
                "Re: Received an IRS CP2000 notice",
                "Priya — the IRS just sent another letter saying they need 30 more days to "
                "process our response. Is that normal? Do we need to do anything?",
            ),
        ],
    ),
    ClientSpec(
        key="ridgeline",
        firm_key="sterling",
        handler_key="marcus",
        name="Ridgeline Contractors Inc",
        email="bob@ridgelinecontractors.com",
        thread_id="ridgeline-1120-rd-credit",
        pregenerate=False,
        emails=[
            EmailSpec(
                0,
                True,
                "Exploring the R&D tax credit",
                "Marcus, we do a lot of custom fabrication and prototyping. A vendor mentioned "
                "we might qualify for the R&D tax credit. Is that something you can help with?",
            ),
            EmailSpec(
                1,
                False,
                "Re: Exploring the R&D tax credit",
                "Very likely yes. Qualifying work has to meet a four-part test. To scope it, "
                "can you send the wages and a breakdown of projects that involved developing or "
                "improving a product or process?",
            ),
            EmailSpec(
                3,
                True,
                "Re: Exploring the R&D tax credit",
                "We have three engineers, roughly $310k in combined wages. A big chunk of their "
                "time went into designing custom welding jigs and prototyping new assemblies.",
            ),
            EmailSpec(
                4,
                False,
                "Re: Exploring the R&D tax credit",
                "That profile looks promising — a rough estimate is around $25k of federal "
                "credit. The catch is you need contemporaneous documentation to support it.",
            ),
            EmailSpec(
                6,
                True,
                "Re: Exploring the R&D tax credit",
                "What counts as documentation? We don't want to lose the credit on a technicality.",
            ),
            EmailSpec(
                7,
                False,
                "Re: Exploring the R&D tax credit",
                "Time tracking by project, design notes, and test/iteration logs all help. I'd "
                "suggest we run a short R&D study to capture it properly before we file.",
            ),
        ],
    ),
    ClientSpec(
        key="vasquez",
        firm_key="sterling",
        handler_key="priya",
        name="Elena Vasquez",
        email="elena.vasquez@outlook.com",
        thread_id="vasquez-2025-extension",
        pregenerate=True,
        emails=[
            EmailSpec(
                0,
                True,
                "I might need a tax extension",
                "Hi Priya, some of my 1099s won't arrive before April and I don't want to file "
                "wrong. Can we get an extension?",
            ),
            EmailSpec(
                1,
                False,
                "Re: I might need a tax extension",
                "Absolutely — I'll file Form 4868 for you. Note an extension is to file, not to "
                "pay, so we should send an estimated payment to avoid penalties.",
            ),
            EmailSpec(
                2,
                True,
                "Re: I might need a tax extension",
                "Got it. How much should I pay so I'm safe?",
            ),
            EmailSpec(
                3,
                False,
                "Re: I might need a tax extension",
                "Based on last year's safe harbor, paying about $3,000 now should keep you "
                "penalty-free. I'll send the payment instructions.",
            ),
            EmailSpec(
                4,
                True,
                "Re: I might need a tax extension",
                "Paid the $3,000. I'll send the rest of my documents in May once everything's in.",
            ),
        ],
    ),
    ClientSpec(
        key="copperfield",
        firm_key="northwind",
        handler_key="sofia",
        name="Copperfield Retail Co",
        email="nina.cho@copperfieldretail.com",
        thread_id="copperfield-nexus-k1",
        pregenerate=True,
        emails=[
            EmailSpec(
                0,
                True,
                "Sales tax nexus in new states?",
                "Sofia, we expanded our online store into five new states last year. I'm worried "
                "about economic nexus and whether we now owe sales tax there.",
            ),
            EmailSpec(
                1,
                False,
                "Re: Sales tax nexus in new states?",
                "Good to get ahead of this. Each state sets an economic nexus threshold, usually "
                "on sales or transaction count. Can you send me your sales by state for the year?",
            ),
            EmailSpec(
                3,
                True,
                "Re: Sales tax nexus in new states?",
                "Here they are: California about $180k, Texas about $90k, and the other three "
                "each under $50k.",
            ),
            EmailSpec(
                4,
                False,
                "Re: Sales tax nexus in new states?",
                "California and Texas both clear their thresholds, so you'll need to register and "
                "collect there. The other three are below threshold for now — we'll monitor them.",
            ),
            EmailSpec(
                5,
                True,
                "Re: Sales tax nexus in new states?",
                "Understood, let's register in California and Texas. Separately, can you handle "
                "the partnership K-1s for me and my co-owner this year?",
            ),
            EmailSpec(
                6,
                False,
                "Re: Sales tax nexus in new states?",
                "Yes — I'll prepare the 1065 and issue both K-1s by mid-March. Can you confirm "
                "the ownership split?",
            ),
            EmailSpec(
                8,
                True,
                "Re: Sales tax nexus in new states?",
                "Thanks. The split is 60% me, 40% my co-owner.",
            ),
            EmailSpec(
                9,
                False,
                "Re: Sales tax nexus in new states?",
                "Recorded the 60/40 split. The California and Texas sales-tax registrations have "
                "been submitted — you're all set on nexus.",
            ),
        ],
    ),
    ClientSpec(
        key="okafor",
        firm_key="northwind",
        handler_key="sofia",
        name="Grant Okafor",
        email="grant.okafor@protonmail.com",
        thread_id="okafor-onboarding-2025",
        pregenerate=False,
        emails=[
            EmailSpec(
                0,
                True,
                "New client — help with my 2025 return",
                "Hello, I was referred to Northwind by a friend. I'd like help preparing my 2025 "
                "personal tax return. What do you need from me to get started?",
            ),
            EmailSpec(
                1,
                False,
                "Re: New client — help with my 2025 return",
                "Welcome, Grant! I've attached our engagement letter and a document checklist. "
                "Please sign the letter and we'll get going.",
            ),
            EmailSpec(
                3,
                True,
                "Re: New client — help with my 2025 return",
                "Signed engagement letter attached. Which documents are the most essential to "
                "start with?",
            ),
            EmailSpec(
                4,
                False,
                "Re: New client — help with my 2025 return",
                "The essentials are your W-2s, any 1099s, your mortgage 1098, and last year's "
                "return for reference. I don't see your prior-year return yet.",
            ),
            EmailSpec(
                6,
                False,
                "Re: New client — help with my 2025 return",
                "Quick follow-up — we're still missing your prior-year return and your W-2. I'll "
                "need both before I can start the return.",
            ),
        ],
    ),
]


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
async def reset(db) -> None:
    """Wipe app tables in FK-safe order so the seed is idempotent."""
    for model in (Email, EmailSummary, Client, Accountant, Firm):
        await db.execute(delete(model))
    await db.commit()


def _build_email(
    spec: EmailSpec, client: Client, handler: Accountant, thread_id: str, position: int
) -> Email:
    outbound = not spec.from_client
    return Email(
        id=uuid.uuid4(),
        firm_id=client.firm_id,
        client_id=client.id,
        accountant_id=handler.id if outbound else None,
        thread_id=thread_id,
        direction=EmailDirection.outbound if outbound else EmailDirection.inbound,
        sender=handler.email if outbound else client.email,
        subject=spec.subject,
        body=spec.body,
        # day drives the date; position guarantees strict in-thread ordering.
        sent_at=BASE + timedelta(days=spec.day, hours=position),
    )


async def seed() -> dict:
    async with SessionLocal() as db:
        await reset(db)

        # --- firms + people ---
        firm_ids: dict[str, uuid.UUID] = {}
        people: dict[str, Accountant] = {}
        pw_hash = hash_password(DEMO_PASSWORD)  # hash once; same demo password for all

        for firm in FIRMS:
            fid = uuid.uuid4()
            firm_ids[firm.key] = fid
            db.add(Firm(id=fid, name=firm.name))
            for p in firm.people:
                acc = Accountant(
                    id=uuid.uuid4(),
                    firm_id=fid,
                    email=p.email,
                    name=p.name,
                    role=p.role,
                    password_hash=pw_hash,
                )
                people[p.key] = acc
                db.add(acc)
        superuser = Accountant(
            id=uuid.uuid4(),
            firm_id=None,
            email=SUPERUSER.email,
            name=SUPERUSER.name,
            role=SUPERUSER.role,
            password_hash=pw_hash,
        )
        people[SUPERUSER.key] = superuser
        db.add(superuser)

        # --- clients ---
        clients: dict[str, Client] = {}
        for spec in CLIENTS:
            c = Client(
                id=uuid.uuid4(),
                firm_id=firm_ids[spec.firm_key],
                name=spec.name,
                email=spec.email,
            )
            clients[spec.key] = c
            db.add(c)

        await db.commit()  # parents committed before emails (FK ordering)

        # --- base emails ---
        for spec in CLIENTS:
            client = clients[spec.key]
            handler = people[spec.handler_key]
            for i, e in enumerate(spec.emails):
                db.add(_build_email(e, client, handler, spec.thread_id, i))
        await db.commit()

        # --- pre-generate summaries through the real service ---
        pregenerated = 0
        for spec in CLIENTS:
            if not spec.pregenerate:
                continue
            client = clients[spec.key]
            admin = next(p for p in FIRMS_BY_KEY[spec.firm_key].people if p.role == Role.firm_admin)
            caller = CurrentUser(
                id=str(people[admin.key].id),
                email=admin.email,
                name=admin.name,
                role=Role.firm_admin.value,
                firm_id=str(client.firm_id),
            )
            await SummaryService(db).refresh_summary(client.id, caller)
            pregenerated += 1

        # --- late emails: arrive AFTER the summary, making that client stale ---
        late = 0
        for spec in CLIENTS:
            if not spec.late_emails:
                continue
            client = clients[spec.key]
            handler = people[spec.handler_key]
            offset = len(spec.emails)
            for i, e in enumerate(spec.late_emails):
                db.add(_build_email(e, client, handler, spec.thread_id, offset + i))
                late += 1
        await db.commit()

        return {
            "firms": len(FIRMS),
            "accountants": len(people),
            "clients": len(CLIENTS),
            "emails": sum(len(c.emails) + len(c.late_emails) for c in CLIENTS),
            "summaries": pregenerated,
            "late_emails": late,
        }


def _print_overview(stats: dict) -> None:
    line = "=" * 68
    print(f"\n{line}\nSeed complete\n{line}")
    print(
        f"  firms={stats['firms']}  accountants={stats['accountants']}  "
        f"clients={stats['clients']}  emails={stats['emails']}  "
        f"summaries={stats['summaries']}"
    )
    print(f"\n  Demo login password for every account:  {DEMO_PASSWORD}\n")
    print("  Accounts")
    print("  --------")
    for firm in FIRMS:
        print(f"  {firm.name}")
        for p in firm.people:
            tag = "  (firm admin)" if p.role == Role.firm_admin else ""
            print(f"    - {p.email}{tag}")
    print("  Ascend network")
    print(f"    - {SUPERUSER.email}  (superuser, cross-firm reports)")
    print("\n  Client states (what each demo path shows)")
    print("  -----------------------------------------")
    for spec in CLIENTS:
        if spec.pregenerate and spec.late_emails:
            state = "summary generated, then a new email arrived -> STALE"
        elif spec.pregenerate:
            state = "summary generated, up to date"
        else:
            state = "no summary yet (needs first refresh)"
        print(f"    - {spec.name}: {state}")
    print(line)


async def _main() -> None:
    stats = await seed()
    _print_overview(stats)


if __name__ == "__main__":
    asyncio.run(_main())
