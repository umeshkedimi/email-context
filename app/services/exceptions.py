"""Domain-level service errors.

Services raise these instead of HTTP exceptions so they stay free of web-framework
concerns; the API layer maps them to status codes (see app/main.py handlers).
"""


class ServiceError(Exception):
    """Base for service-layer errors."""


class ClientNotFound(ServiceError):
    """Client does not exist, or is outside the caller's firm (we don't distinguish
    the two to the caller — both surface as 404)."""


class NoEmailsToSummarize(ServiceError):
    """Refresh requested for a client with no emails to summarize."""


class SummaryGenerationError(ServiceError):
    """The LLM provider failed to produce a summary."""
