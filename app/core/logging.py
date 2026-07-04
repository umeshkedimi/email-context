import logging

import structlog

from app.core.config import get_settings


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
