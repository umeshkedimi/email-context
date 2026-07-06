# Design Decisions

This document records the **consequential** decisions behind the Email Context &
Summarization System — the ones where a competent engineer could have chosen
differently, with the trade-off we accepted. Implementation details and
framework idioms are deliberately left out; they live in the code and its
comments.

Status legend: ✅ implemented · 🔜 planned (design fixed, code pending).

---

## 1. Product model

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **One summary per client**, covering all emails to date | Summary per email; per-thread summary | The product question is "what's the state of this client relationship?", not "what did this one email say". One rolling summary answers that directly. | Regenerating over the full history costs more tokens than an incremental update. Acceptable at this scale; revisited only if email volume per client grows large. |
| **User-triggered regeneration** (dashboard shows staleness, user clicks refresh) | Auto-regenerate on every inbound email | Auto-regen burns an LLM call on every email even when nobody is looking at that client — wasteful and poor product behavior. The dashboard user decides when a fresh view is worth generating. | The displayed summary can be stale between refreshes. Mitigated by an explicit **staleness indicator** (new-email count since last generation). |
| **`GET` is read-only; only `POST /refresh` calls the LLM** | Generate lazily inside `GET` when stale | Keeps reads cheap, fast, and free of side effects; makes the one expensive, non-idempotent operation explicit and deliberate. | A first-time client has no summary until someone triggers one. Acceptable — reporting/seed flows pre-generate. |

## 2. Data model & multi-tenancy

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **Client belongs to exactly one firm** | Client shared across firms (M:N) | Confirmed with the panel: a client is scoped to one CPA firm. A single owner keeps tenancy, summaries, and access control unambiguous. | If the business later needs shared clients, this needs a join table. Not a current requirement. |
| **Firm-scoped isolation enforced structurally**, cross-firm access returns **404, not 403** | 403 Forbidden on cross-firm access | `firm_id` rides in the JWT and every data query filters on it, so out-of-firm rows are simply not found. Returning 404 (not 403) avoids confirming a resource *exists* to someone outside the firm. | Slightly less "helpful" errors for legitimate edge cases. Correct security posture outweighs it. |
| **`firm_id` denormalized onto emails/summaries** | Always join back through `client` | Lets tenancy filters and firm-level reports run without an extra join on hot paths. | Must keep the denormalized `firm_id` consistent with the client's. Enforced at write time; the client→firm link is immutable. |
| **App-managed UUID primary keys** | Auto-increment integers | Non-guessable, safe to expose in URLs, collision-free across environments, no dependence on DB sequences. | 16 bytes vs 4/8, and random UUIDs are less index-friendly than sequential ids. Negligible at this scale. |

## 3. Authentication & authorization

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **Stateless JWT (HS256)** carrying `sub`, `role`, `firm_id` | Server-side sessions in Redis/DB | No session store to run or share; scales horizontally; authorization reads the role/firm straight from the verified token without a lookup. | A JWT can't be revoked before it expires. **Mitigated** by (a) a short TTL and (b) re-loading the user row from the DB on each request, so a deleted/disabled account can't keep acting on a live token. |
| **`bcrypt` password hashing** | argon2id; SHA-256 + manual salt | Salted (defeats rainbow tables) and adaptive/slow with a tunable work factor (throttles brute force). Battle-tested and ubiquitous. | argon2id is the modern memory-hard winner and a defensible alternative; bcrypt is sufficient and lower-friction here. Plain fast hashes (SHA-256) were rejected outright — too fast to be safe for passwords. |
| **Uniform 401 for unknown-email vs wrong-password** | Distinct "no such user" / "wrong password" messages | Distinct errors let an attacker enumerate which emails are registered. One message closes that channel. | Marginally less convenient for a legitimate user who forgot which email they used. Standard, accepted trade-off. |
| **Role-Based Access Control** — `accountant` / `firm_admin` / `superuser` | Per-user permission flags | Three clear tiers map to the org (accountant → own firm; firm_admin → firm reporting; superuser → cross-firm Ascend reporting). A `require_roles()` dependency enforces it at the route. | Coarser than per-permission grants. Matches the domain; finer granularity isn't needed. |
| **`superuser` is not bound to a firm** (`firm_id` nullable) | Give superuser a sentinel firm | Cross-firm reporting is inherently firm-less; a nullable `firm_id` models that honestly instead of faking membership. | Firm-scoping code must handle the `None` case explicitly. Small, localized. |

## 4. LLM & summarization ✅

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **Provider behind an `LLMProvider` interface** | Call the vendor SDK directly from services | Swappable model/vendor, and a stub implementation lets tests and CI run with no API key or network. | One layer of indirection. Worth it for testability and vendor independence. |
| **OpenAI GPT** as the default model (pluggable) | Gemini; a single hard-wired vendor | The panel left the choice open, so we pick a capable, well-supported model and — more importantly — keep it behind the `LLMProvider` interface so the vendor is a config/implementation swap, not a rewrite. | Vendor lock-in risk if used directly; the interface neutralizes it. Model quality/cost is a tunable, not a fixed commitment. |
| **Structured (schema-validated) output** → actors · concluded discussions · open action items | Free-form text summary | The consumer is a dashboard with defined sections; a validated schema guarantees the shape and lets us store/query parts. | The model must conform to a schema, occasionally needing a retry. Handled by the provider layer. |

## 5. Data protection ✅

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **AES-256-GCM application-level encryption** of summary payloads at rest | Rely only on disk/DB encryption; store plaintext | Summaries contain client-confidential content. App-level AEAD (GCM gives confidentiality **and** integrity) protects the data even if a DB dump leaks, independent of infra config. | Encrypted columns aren't queryable, and key management becomes our responsibility. Non-sensitive tracking fields stay plaintext so they remain queryable. |
| **`key_version` stored with each ciphertext** | Single fixed key | Enables key rotation: new writes use the current key while old rows remain decryptable under their recorded version. | A little extra bookkeeping per row. Standard practice for encryption at rest. |
| **Associated data (AAD) = client id** on every summary ciphertext | Encrypt without AAD | Authentication now also covers *which client* a ciphertext belongs to, so a valid blob copied onto another client's row fails to decrypt. | Callers must pass the same client id on read; a mismatch is treated as corruption. |
| **Redis caches ciphertext + metadata, never plaintext** | Cache the decrypted summary; don't cache at all | Keeps the at-rest encryption boundary intact through the cache — a Redis dump leaks nothing readable — while still saving the DB round-trip. Staleness is always computed live, so a cached payload never hides new email. | A cache hit still pays one decrypt. Negligible, and worth it for the security property. |
| **Reports read metadata only — never decrypt a summary** | Include summary content in reports | The queryable tracking columns (counts, timestamps, status) were deliberately kept out of the encrypted blob; firm/network reports run entirely off them as aggregate SQL. Reporting therefore needs zero access to confidential content, and staleness in a report matches the summary endpoint exactly (same formula). | Reports can show *that* a client is stale, not *what* the summary says. Correct — drill-down is the summary endpoint's job, behind its own decrypt. |

## 6. Engineering & tooling

| Decision | Alternatives considered | Why we chose it | Trade-off accepted |
|---|---|---|---|
| **`uv` + committed `uv.lock`, Python pinned via `.python-version`** | pip + venv; Poetry | Fast, reproducible installs and identical Python across dev and the deploy server (uv provisions the pinned version everywhere), which removed a real 3.14-local vs 3.12-server mismatch. | `uv` is newer than pip/Poetry. Its lockfile and speed are worth it; nothing depends on uv-only behavior. |
| **`pydantic` v2 for all boundaries** — request/response DTOs, settings, LLM output | Hand-rolled validation; dataclasses | One validation layer for HTTP input, environment config, and model output; typed, self-documenting, and fails fast at the edge. | A dependency and its learning curve. Standard in modern FastAPI stacks. |
| **Repository pattern** (api → service → repository) | Query the ORM directly from endpoints | Persistence lives in one place, so business logic and routes are testable without a DB and queries aren't scattered. | More layers/boilerplate for simple reads. Pays off as the surface grows. |
| **Async SQLAlchemy 2.0 + psycopg3** | Sync SQLAlchemy | The app is I/O-bound (DB + LLM calls); async lets a request await the LLM without blocking a worker. | Async is more error-prone (session handling, no lazy loads). Contained by the repository layer. |
| **structlog JSON logs + per-request request-id** | Plain text logging | Structured logs are queryable in aggregation tools, and a request-id ties every line of one request together for debugging. | Slightly noisier locally than plain text. Worth it for real observability. |
| **Alembic migrations committed to git** | Auto-create tables from models on boot | Versioned, reviewable schema changes; the same migration runs in every environment. | Migrations must be written/checked in. Standard discipline. |

---

## Notes for the reviewer

- **Secrets** are never committed. `.env` is git-ignored; real keys are generated on
  the server. `.env.example` documents the required variables.
- **Observability**: every request carries an `x-request-id` (echoed in the
  response header) and emits one structured access-log line with latency.
- This document grows as each block lands; forward-looking rows are marked 🔜
  and reflect a fixed design, not yet-shipped code.
