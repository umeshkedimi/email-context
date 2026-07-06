"""Reusable OpenAPI `responses` fragments.

Each route documents its *real* failure modes, not just the 200. Keeping the
fragments here means the error contract stays consistent across endpoints and
every documented status maps to the same `ErrorResponse` shape the handlers emit.
Merge them per route, e.g. `responses={**UNAUTHORIZED, **CLIENT_NOT_FOUND}`.
"""

from typing import Any

from app.schemas.errors import ErrorResponse


def _error(status: int, description: str, example_detail: str) -> dict[int, dict[str, Any]]:
    return {
        status: {
            "model": ErrorResponse,
            "description": description,
            "content": {"application/json": {"example": {"detail": example_detail}}},
        }
    }


UNAUTHORIZED = _error(
    401, "Missing, malformed, or expired bearer token.", "Invalid or expired token"
)
FORBIDDEN = _error(
    403,
    "Authenticated, but your role may not access this resource.",
    "Insufficient permissions for this resource",
)
BAD_LOGIN = _error(
    401,
    "Unknown email or wrong password — the same response for both, to prevent account enumeration.",
    "Incorrect email or password",
)
CLIENT_NOT_FOUND = _error(
    404,
    "No such client in your firm. Cross-firm access is deliberately "
    "indistinguishable from a missing client.",
    "Client not found",
)
NO_EMAILS = _error(
    400,
    "The client has no emails, so there is nothing to summarize.",
    "This client has no emails to summarize",
)
GENERATION_FAILED = _error(
    502,
    "The LLM provider failed to generate a summary; any previous summary is left intact.",
    "Summary generation failed",
)
FIRM_NOT_FOUND = _error(404, "No firm with that id.", "Firm not found")
REPORT_SCOPE = _error(
    400,
    "A superuser belongs to no firm and must pass `?firm_id=` to scope a firm report.",
    "A superuser must specify firm_id for a firm report",
)
