import logging

import structlog
from opentelemetry import trace

from app.core.config import get_settings


def _add_trace_context(logger, method_name, event_dict):
    """Stamp the active trace/span id onto each log line so logs and traces
    cross-reference. No-op when no span is active (e.g. OTel disabled)."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging() -> None:
    """Configure structlog to emit JSON logs with a consistent shape.

    JSON logs are the baseline for observability: they are trivially shippable to
    a log aggregator and each line carries structured fields (request_id, user_id,
    firm_id, latency) rather than free-form text.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_trace_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
