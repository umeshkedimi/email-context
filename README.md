# Email Context & Summarization System

Backend for **Ascend**, a network of CPA firms. Multiple accountants email the
same client to gather tax-return information but can't see each other's threads,
leading to redundant questions. This system captures all email discussions
between a firm's accountants and a client and produces a single, AI-generated
**source of truth** per client: who's involved, what's been concluded, and what
action items are still open.

> Take-home case study — Backend Engineer @ Ascend. Built with Python/FastAPI,
> PostgreSQL, Redis, and Gemini.

## Status

🚧 Under active development — see commit history for incremental progress.

- [x] Scaffold, tooling, `/health`, structured logging
- [ ] Schema + migrations
- [ ] Auth (JWT) + firm-scoped access control
- [ ] LLM summarization + encryption at rest
- [ ] Summary endpoints, caching, refresh
- [ ] Admin / superuser reports
- [ ] Seed data + tests

## Quick start

### Option A — Docker (reviewers)

```bash
cp .env.example .env   # fill in GEMINI_API_KEY and SUMMARY_ENCRYPTION_KEY
docker compose up --build
# API on http://localhost:8000  •  docs on http://localhost:8000/docs
```

### Option B — native (Postgres + Redis already installed)

Uses [uv](https://docs.astral.sh/uv/) for dependency management. `uv sync` reads
the pinned `.python-version`, provisions Python 3.12, and installs the exact
versions from `uv.lock`.

```bash
uv sync                # creates .venv (Python 3.12) from the lockfile
cp .env.example .env   # fill in secrets (see below)
make migrate && make seed
make run               # http://localhost:8000/docs
```

Generate the two required secrets:

```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "import base64,os; print('SUMMARY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

Grab a free `GEMINI_API_KEY` at https://aistudio.google.com. To run without a
key (tests/demo), set `LLM_STUB_MODE=true`.

## Architecture

Full design notes land here as the build progresses (schema, layered
architecture, security, caching, scalability, and AI-tool usage).
