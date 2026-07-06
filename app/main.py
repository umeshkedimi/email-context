import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.logging import configure_logging, get_logger
from app.services.exceptions import (
    ClientNotFound,
    FirmNotFound,
    NoEmailsToSummarize,
    ReportScopeError,
    SummaryGenerationError,
)

configure_logging()
log = get_logger("app.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_logger("app").info("startup")
    yield
    get_logger("app").info("shutdown")


DESCRIPTION = """
Unified per-client email intelligence for CPA firms (**Ascend**). Every email
between a firm's accountants and a client is captured and distilled into one
AI-generated summary — actors, concluded discussions, and open action items.

### Authentication
All `/api/v1` routes except `POST /auth/login` require a **Bearer JWT**. Get one
from `POST /auth/login`, click **Authorize** (top right), and paste the
`access_token`. On the live demo every seeded account's password is `Demo1234!`.

### Roles
- **accountant** — read client context within their own firm
- **firm_admin** — accountant rights + their firm's report
- **superuser** — cross-firm (Ascend-wide) reports; belongs to no firm

Cross-firm access returns **404, never 403** — the API never confirms that a
resource exists to someone outside its firm.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Log in and inspect the authenticated principal."},
    {
        "name": "summaries",
        "description": "Read a client's summary and trigger regeneration — the only "
        "endpoint that calls the LLM.",
    },
    {
        "name": "reports",
        "description": "Firm and network dashboards. Metadata only — reports never "
        "decrypt summary content.",
    },
    {"name": "ops", "description": "Operational endpoints (liveness)."},
]

app = FastAPI(
    title="Email Context & Summarization System",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Umesh Kedimi", "url": "https://github.com/umeshkedimi/email-context"},
    servers=[
        {"url": "https://email-context.umeshkedimi.com", "description": "Live demo"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id, bind it to the logging context, and emit one
    structured access-log line per request with latency."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request_failed", method=request.method, path=request.url.path)
        raise
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(ClientNotFound)
async def _handle_client_not_found(request: Request, exc: ClientNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Client not found"})


@app.exception_handler(NoEmailsToSummarize)
async def _handle_no_emails(request: Request, exc: NoEmailsToSummarize) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"detail": "This client has no emails to summarize"}
    )


@app.exception_handler(SummaryGenerationError)
async def _handle_generation_error(request: Request, exc: SummaryGenerationError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "Summary generation failed"})


@app.exception_handler(FirmNotFound)
async def _handle_firm_not_found(request: Request, exc: FirmNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Firm not found"})


@app.exception_handler(ReportScopeError)
async def _handle_report_scope(request: Request, exc: ReportScopeError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": "A superuser must specify firm_id for a firm report"},
    )


@app.get("/health", tags=["ops"], summary="Liveness probe", operation_id="health_check")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(api_router)

# Serve the thin web client. Mounted LAST so it only catches paths the API
# routes above didn't claim; `/api/v1/...`, `/health`, and `/docs` still resolve
# first. html=True serves index.html at "/". Same origin as the API → no CORS.
WEB_DIR = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
