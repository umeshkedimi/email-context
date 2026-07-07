"""The provider-agnostic contract every LLM backend implements.

Services depend only on this ABC, never on a vendor SDK, so the model/vendor is a
swap of one implementation — the reason the whole LLM layer is pluggable.
"""

from abc import ABC, abstractmethod

from app.schemas.summary import EmailForSummary, SummaryContext, SummaryResult

_SYSTEM_PROMPT = (
    "You are an assistant for a CPA firm. You are given the full email history "
    "between the firm's accountants and one client. Produce a single, faithful "
    "summary of the client relationship. Extract:\n"
    "- actors: every distinct person/entity involved and their role;\n"
    "- concluded_discussions: topics that reached a decision or conclusion;\n"
    "- open_action_items: things still needing action, with an owner if stated.\n"
    "Only use information present in the emails. Do not invent facts, amounts, or "
    "commitments. If something is ambiguous, prefer leaving it out over guessing."
)

# Used when a prior summary is carried forward (incremental refresh): the model
# updates the running summary from only the new emails, instead of re-reading the
# whole history. This keeps each call bounded as the thread grows.
_INCREMENTAL_SYSTEM_PROMPT = (
    "You are an assistant for a CPA firm maintaining a running summary of one "
    "client relationship. You are given the PREVIOUS summary (as JSON) and only "
    "the NEW emails received since it was produced. Return an UPDATED summary "
    "that:\n"
    "- integrates the new emails into the prior state;\n"
    "- keeps still-valid actors, concluded discussions, and open action items;\n"
    "- moves an open action item into concluded_discussions when the new emails "
    "show it was resolved;\n"
    "- adds newly-raised action items and any newly-involved actors.\n"
    "Use only the previous summary and the new emails. Do not invent facts, "
    "amounts, or commitments. If something is ambiguous, prefer leaving it out."
)


def _render_email(e: EmailForSummary) -> str:
    subject = e.subject or "(no subject)"
    return (
        f"[{e.sent_at:%Y-%m-%d %H:%M} | {e.direction} | from: {e.sender}]\n"
        f"Subject: {subject}\n{e.body.strip()}"
    )


def build_prompt(context: SummaryContext) -> tuple[str, str]:
    """Return (system, user) messages for a chat-style provider.

    Two shapes: a full pass over the whole history, or — when `prior_summary` is
    set — an incremental update from the prior state plus only the new emails.
    """
    body = "\n\n---\n\n".join(_render_email(e) for e in context.emails)

    if context.prior_summary is not None:
        header = (
            f"Client: {context.client_name} <{context.client_email}>\n\n"
            "=== PREVIOUS SUMMARY (JSON) ===\n"
            f"{context.prior_summary.model_dump_json(indent=2)}\n\n"
            f"=== NEW EMAILS ({len(context.emails)}), oldest first ===\n"
        )
        return _INCREMENTAL_SYSTEM_PROMPT, header + body

    header = (
        f"Client: {context.client_name} <{context.client_email}>\n"
        f"Emails ({len(context.emails)}), oldest first:\n"
    )
    return _SYSTEM_PROMPT, header + "\n" + body


class LLMProvider(ABC):
    """Summarizes one client's email history into a structured payload."""

    @abstractmethod
    async def summarize(self, context: SummaryContext) -> SummaryResult:
        """Return a validated summary, or raise on unrecoverable provider failure."""
        raise NotImplementedError
