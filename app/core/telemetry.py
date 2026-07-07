"""OpenTelemetry tracing setup (opt-in).

Traces are the second pillar of observability alongside the structured logs: they
turn one request into a timed tree of spans (HTTP -> DB -> cache -> LLM), so
latency can be attributed to the exact sub-operation rather than guessed at from
flat log lines. Spans are exported over OTLP, which is vendor-neutral — the same
code ships to Jaeger, Tempo, Datadog, or Honeycomb by only changing the endpoint.

Everything here is a no-op unless OTEL_ENABLED is set, so the app has no hard
runtime dependency on a running collector (local dev, tests, and CI are
unaffected). The manual span helper (`get_tracer`) always works: without an SDK
provider the OpenTelemetry API returns a no-op span, so instrumented call sites
stay valid whether tracing is on or off.
"""

from __future__ import annotations

import structlog

from app.core.config import get_settings

log = structlog.get_logger("app.telemetry")

_configured = False


def setup_telemetry(app) -> None:
    """Wire up the tracer provider and auto-instrumentation. Idempotent + opt-in."""
    global _configured
    s = get_settings()
    if not s.otel_enabled or _configured:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create(
        {"service.name": s.otel_service_name, "deployment.environment": s.env}
    )
    provider = TracerProvider(resource=resource)

    if s.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{s.otel_exporter_otlp_endpoint}/v1/traces")
            )
        )
    if s.otel_console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Auto-instrument the framework, ORM, and cache. FastAPI gives a span per
    # request; SQLAlchemy a span per query; Redis a span per cache op — so the
    # DB/cache portions of a request appear without hand-written spans.
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from app.db.session import engine

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    RedisInstrumentor().instrument()

    _configured = True
    log.info(
        "otel_enabled",
        service=s.otel_service_name,
        otlp=bool(s.otel_exporter_otlp_endpoint),
        console=s.otel_console_export,
    )


def get_tracer(name: str = "app"):
    """A tracer for hand-written spans. No-op until a provider is configured."""
    from opentelemetry import trace

    return trace.get_tracer(name)
