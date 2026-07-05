import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.logging import configure_logging, get_logger
from app.services.exceptions import (
    ClientNotFound,
    NoEmailsToSummarize,
    SummaryGenerationError,
)

configure_logging()
log = get_logger("app.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_logger("app").info("startup")
    yield
    get_logger("app").info("shutdown")


app = FastAPI(
    title="Email Context & Summarization System",
    description="Unified per-client email intelligence for CPA firms.",
    version="0.1.0",
    lifespan=lifespan,
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


@app.get("/health", tags=["ops"])
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(api_router)
