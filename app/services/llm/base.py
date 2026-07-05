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


def _render_email(e: EmailForSummary) -> str:
    subject = e.subject or "(no subject)"
    return (
        f"[{e.sent_at:%Y-%m-%d %H:%M} | {e.direction} | from: {e.sender}]\n"
        f"Subject: {subject}\n{e.body.strip()}"
    )


def build_prompt(context: SummaryContext) -> tuple[str, str]:
    """Return (system, user) messages for a chat-style provider."""
    header = (
        f"Client: {context.client_name} <{context.client_email}>\n"
        f"Emails ({len(context.emails)}), oldest first:\n"
    )
    body = "\n\n---\n\n".join(_render_email(e) for e in context.emails)
    return _SYSTEM_PROMPT, header + "\n" + body


class LLMProvider(ABC):
    """Summarizes one client's email history into a structured payload."""

    @abstractmethod
    async def summarize(self, context: SummaryContext) -> SummaryResult:
        """Return a validated summary, or raise on unrecoverable provider failure."""
        raise NotImplementedError
