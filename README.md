# Email Context & Summarization System

![CI](https://github.com/umeshkedimi/email-context/actions/workflows/ci.yml/badge.svg)

**Live demo:** [email-context.umeshkedimi.com](https://email-context.umeshkedimi.com) —
seeded, over HTTPS. Sign in as `diane.sterling@sterlingvance.com` (firm admin) or
`platform@ascendcpa.com` (Ascend superuser); every demo password is `Demo1234!`.

Backend for **Ascend**, a network of CPA firms. Several accountants email the same
client to gather tax-return information but can't see each other's threads — so the
client gets asked the same things twice and context is lost. This service captures
every email between a firm's accountants and a client and produces a single,
AI-generated **source of truth** per client:

- **Actors** — who is involved in the discussions (client, spouse, IRS agent, …)
- **Concluded discussions** — topics that reached a decision
- **Open action items** — what still needs doing, and who owns it

One rolling summary per client, regenerated **on demand** with a live
staleness indicator so nobody wastes an LLM call — or trusts an out-of-date view.

> Take-home case study — Backend Engineer @ Ascend. Python / FastAPI, PostgreSQL,
> Redis, and a pluggable LLM (OpenAI by default). The backend is the focus; a thin
> web UI (see [Web UI](#web-ui)) and a live deployment round it out.

---

## Contents

- [Architecture](#architecture)
- [Key design decisions](#key-design-decisions)
- [Quick start](#quick-start)
- [Demo walkthrough](#demo-walkthrough)
- [API](#api)
- [Roles & access control](#roles--access-control)
- [Web UI](#web-ui)
- [Testing & CI](#testing--ci)
- [Security](#security)
- [AI in this system](#ai-in-this-system)
- [Deployment](#deployment)
- [Project layout](#project-layout)
- [License](#license)

---

## Architecture

Clean, layered separation — routes stay thin, business rules live in services,
persistence is isolated in repositories:

```
HTTP ─▶ api/ (FastAPI routers)         validation, auth dependency, HTTP mapping
          │
          ▼
        services/                      business rules: tenancy, staleness,
          │                            encryption, LLM orchestration
          ├──▶ repositories/           all SQL lives here (async SQLAlchemy 2.0)
          ├──▶ core/crypto             AES-256-GCM encrypt/decrypt at rest
          ├──▶ core/cache              Redis (ciphertext only, best-effort)
          └──▶ services/llm            LLMProvider interface (OpenAI | stub)
```

**Stack:** Python 3.12 · FastAPI · async SQLAlchemy 2.0 + psycopg3 · PostgreSQL 16 ·
Redis 7 · Alembic · pydantic v2 · structlog · `uv` for packaging.

**Data model:** `firms` ─┬─ `accountants` (users) · ─┬─ `clients` ─┬─ `emails`
(the mock inbox) and └─ `email_summaries` (one per client, encrypted payload +
plaintext tracking columns). `firm_id` is denormalized onto emails/summaries so
tenancy filters and firm reports never need an extra join.

## Key design decisions

The full trade-off table (decision · alternatives · why · trade-off accepted)
is in **[docs/DESIGN.md](docs/DESIGN.md)** — the highest-signal read. Headlines:

- **User-triggered regeneration.** `GET` is read-only and never calls the LLM;
  `POST …/refresh` is the *only* trigger. Staleness (`new_emails_count`) is
  computed live on every read, so the dashboard never hides new mail or burns
  tokens on clients nobody is looking at.
- **Firm-scoped multi-tenancy, enforced in the service layer.** `firm_id` rides
  in the JWT; cross-firm access returns **404, not 403**, so we never confirm a
  resource exists to an outsider.
- **Encryption at rest for summary content.** Payloads are AES-256-GCM (AEAD)
  ciphertext with a versioned keyring (rotation) and **AAD bound to the client
  id** (a blob can't be replayed onto another client). Only non-sensitive
  tracking columns stay queryable in plaintext.
- **The cache holds ciphertext only.** A Redis dump leaks nothing readable; the
  at-rest encryption boundary survives into the cache.
- **The LLM is behind an interface.** Vendor is a config swap, and a deterministic
  stub lets tests, CI, and keyless demos run with no network.

## Quick start

### Option A — Docker (reviewers, zero setup)

```bash
cp .env.example .env     # set SUMMARY_ENCRYPTION_KEY (and JWT_SECRET); LLM key optional
docker compose up --build
# migrates, seeds the demo data, and serves:
#   API   http://localhost:8000
#   Docs  http://localhost:8000/docs
```

### Option B — native (uv)

Uses [uv](https://docs.astral.sh/uv/). `uv sync` reads the pinned
`.python-version`, provisions Python 3.12, and installs the exact `uv.lock`
versions. Requires Postgres + Redis reachable at the URLs in `.env`.

```bash
uv sync
cp .env.example .env
make migrate && make seed      # apply schema, load the demo world
make run                       # http://localhost:8000/docs
```

Generate the required secrets:

```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "import base64,os; print('SUMMARY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

Set `LLM_API_KEY` for real summaries, or leave it empty / `LLM_STUB_MODE=true`
to run keyless with the deterministic stub.

## Demo walkthrough

`make seed` loads two firms, six clients, and ~40 realistic tax-season emails,
and pre-generates a few summaries — deliberately leaving clients in **different
states** so every path is visible. Every demo account's password is `Demo1234!`.

| Client | State |
|---|---|
| Brightwave Design LLC, Elena Vasquez, Copperfield Retail Co | summary generated, up to date |
| **Hartley Family** | summary generated, then a new email arrived → **stale** |
| Ridgeline Contractors Inc, Grant Okafor | no summary yet |

Walk the whole product in five calls (needs `jq`):

```bash
BASE=http://localhost:8000/api/v1

# 1. Log in as a firm admin
TOKEN=$(curl -s $BASE/auth/login -H 'content-type: application/json' \
  -d '{"email":"diane.sterling@sterlingvance.com","password":"Demo1234!"}' | jq -r .access_token)

# 2. Firm dashboard: every client with summary status + staleness
curl -s $BASE/reports/firm -H "Authorization: Bearer $TOKEN" | jq

# 3. Read the stale client's summary (note is_stale / new_emails_count)
CID=$(curl -s $BASE/reports/firm -H "Authorization: Bearer $TOKEN" \
  | jq -r '.clients[] | select(.client_name=="Hartley Family").client_id')
curl -s $BASE/clients/$CID/summary -H "Authorization: Bearer $TOKEN" \
  | jq '{generated,is_stale,new_emails_count}'

# 4. Regenerate (the only LLM call) — staleness clears
curl -s -X POST $BASE/clients/$CID/summary/refresh -H "Authorization: Bearer $TOKEN" \
  | jq '{is_stale,new_emails_count,payload}'

# 5. Superuser: network-wide rollup across all firms
STOKEN=$(curl -s $BASE/auth/login -H 'content-type: application/json' \
  -d '{"email":"platform@ascendcpa.com","password":"Demo1234!"}' | jq -r .access_token)
curl -s $BASE/reports/network -H "Authorization: Bearer $STOKEN" | jq
```

Cross-firm isolation to try: log in as `alan.brooks@northwindtax.com` (a different
firm) and request `$CID` above — you get a `404`, not a `403`.

## API

Interactive docs at `/docs`. All `/api/v1` routes except login require a
`Bearer` token.

| Method & path | Role | Purpose |
|---|---|---|
| `POST /api/v1/auth/login` | public | Exchange email + password for a JWT |
| `GET /api/v1/auth/me` | any | The authenticated principal |
| `GET /api/v1/clients/{id}/summary` | own firm (superuser: any) | Read summary + live staleness. **No LLM call.** |
| `POST /api/v1/clients/{id}/summary/refresh` | own firm (superuser: any) | Regenerate — the only LLM trigger |
| `GET /api/v1/reports/firm` | firm_admin (own) · superuser (`?firm_id=`) | Per-firm dashboard + per-client rows |
| `GET /api/v1/reports/network` | superuser | Ascend-wide rollup across firms |
| `GET /health` | public | Liveness |

## Roles & access control

| Role | Scope |
|---|---|
| `accountant` | Read client context within their own firm |
| `firm_admin` | Accountant rights + their firm's report |
| `superuser` | Cross-firm (Ascend) reports; not bound to any firm (`firm_id` is null) |

Enforced two ways: a `require_roles(...)` dependency gates routes (→ 403), and the
service layer scopes every query to the caller's firm (cross-firm → 404).

## Web UI

A thin browser client ships in [`app/web/`](app/web/), served **same-origin** by
FastAPI (`StaticFiles`) — no separate frontend build, no CORS. It is a pure
consumer of the JSON API above: it holds the JWT, attaches it as a bearer token,
and renders what the API returns. Four screens cover the product — login, the firm
dashboard (client roster + staleness), a client summary with a **Regenerate**
button (the only LLM trigger), and the superuser network rollup — with role-aware
navigation.

Vanilla HTML/CSS/JS, no framework: the point is to showcase the backend, and the
UI proves the API is complete enough that a client is just another consumer. All
server- and model-originated text is HTML-escaped before render. The JWT is kept
in `localStorage` — a conscious trade-off for a thin demo (an httpOnly cookie +
CSRF is the production path); see [docs/DESIGN.md](docs/DESIGN.md) §7.

## Testing & CI

```bash
make test                                   # in-memory SQLite, stub LLM, no services
TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest   # same suite, real Postgres
```

The suite (42 tests) is hermetic by default — dialect-neutral models let it run
against in-memory SQLite with the stub LLM and no Redis, so it needs zero
services. The **same** tests run against Postgres by setting `TEST_DATABASE_URL`,
which exercises the aggregate report SQL on the real engine. Coverage: the crypto
core (AEAD round-trip, AAD replay rejection, key rotation, tamper detection),
password/JWT, login enumeration protection, deleted-user token rejection,
firm-scoped 404s, the GET/refresh flow and live staleness, and report role-gating
and rollups.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push/PR:
ruff lint + format check + the SQLite suite (hermetic job), and the full suite
again against Postgres + Redis service containers (fidelity job).

## Security

- **Secrets are never committed.** `.env` is git-ignored; `.env.example` documents
  every variable. Keys are generated per environment.
- **Encryption at rest** for summary content (see design decisions above).
- **Passwords** are bcrypt-hashed (salted, adaptive work factor).
- **Login** returns one uniform error for unknown-email and wrong-password, so an
  attacker can't enumerate registered emails.
- **JWTs** are short-lived and the user row is re-loaded on every request, so a
  disabled/deleted account can't keep acting on a live token.
- Every response carries an `x-request-id` for traceability.

## AI in this system

The summarizer is the AI surface, and it's built to be trustworthy and swappable:

- **Provider interface.** `LLMProvider` (`app/services/llm/`) abstracts the vendor.
  `OpenAIProvider` is the default; `StubProvider` is deterministic and keyless for
  tests/CI/demos. Switching vendor is a config + one-class change, not a rewrite.
- **Structured output.** The model must return a schema-validated payload (actors,
  concluded discussions, open action items) — the dashboard's exact shape.
- **Anti-hallucination.** The system prompt constrains the model to facts present
  in the emails only; it must not invent people, decisions, or action items.
- **Resilience.** Transient provider errors are retried (tenacity); a failed
  refresh leaves the last good summary intact.

## Deployment

Runs on a small Linux host (a DigitalOcean droplet for this project), live at
[email-context.umeshkedimi.com](https://email-context.umeshkedimi.com).

```bash
# on the host: pull, install, migrate
git pull && uv sync --frozen && uv run alembic upgrade head
```

The production shape:

- **`systemd` service** ([`deploy/email-context.service`](deploy/email-context.service))
  runs uvicorn bound to `127.0.0.1:8000`, applies migrations on start
  (`ExecStartPre`), and restarts on failure. Seeding is intentionally *not* a boot
  step — it's a one-off, destructive reset. Logs stream to `journalctl -u
  email-context`.
- **nginx** reverse-proxies the domain to the localhost app, so uvicorn never
  listens publicly.
- **Let's Encrypt TLS** via certbot terminates HTTPS at nginx and redirects HTTP,
  with automatic renewal.

Postgres and Redis run alongside on the host. For a zero-setup local run, the
Docker Compose stack ([`docker-compose.yml`](docker-compose.yml)) brings up the
app, Postgres, and Redis together.

## Project layout

```
app/
  api/v1/        routers: auth, summaries, reports
  services/      summary_service, report_service, llm/ (provider interface)
  repositories/  data access (one per aggregate)
  models/        SQLAlchemy ORM + enums
  schemas/       pydantic DTOs
  core/          config, security (JWT/bcrypt), crypto, cache, deps, logging
  web/           thin browser client (static HTML/CSS/JS), served same-origin
alembic/         migrations
scripts/seed.py  idempotent demo dataset
tests/           hermetic pytest suite
docs/DESIGN.md   trade-off decision record
deploy/          systemd unit
```

## License

Released under the [MIT License](LICENSE).
