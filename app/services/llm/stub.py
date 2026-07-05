"""Deterministic, no-network provider.

Selected when LLM_STUB_MODE is on or no API key is configured, so tests, CI, and
demos run without a key or spend. Output is derived from the input (not random),
so tests can assert on it.
"""

from app.schemas.summary import (
    ActionItem,
    Actor,
    SummaryContext,
    SummaryPayload,
    SummaryResult,
)
from app.services.llm.base import LLMProvider

MODEL_NAME = "stub"


class StubProvider(LLMProvider):
    async def summarize(self, context: SummaryContext) -> SummaryResult:
        # Distinct senders become actors, in first-seen order (deterministic).
        seen: dict[str, None] = {}
        for e in context.emails:
            seen.setdefault(e.sender, None)
        actors = [Actor(name=s, role="participant") for s in seen]

        subjects = [e.subject for e in context.emails if e.subject]
        # Heuristic stand-in: the latest inbound email is treated as an open item.
        last_inbound = next((e for e in reversed(context.emails) if e.direction == "inbound"), None)
        open_items = (
            [
                ActionItem(
                    description=f"Respond to: {last_inbound.subject or '(no subject)'}",
                    owner=context.client_name,
                )
            ]
            if last_inbound
            else []
        )

        payload = SummaryPayload(
            overview=(
                f"[STUB] {len(context.emails)} emails with {context.client_name} "
                f"involving {len(actors)} participant(s)."
            ),
            actors=actors,
            concluded_discussions=list(dict.fromkeys(subjects)),
            open_action_items=open_items,
        )
        return SummaryResult(payload=payload, model_used=MODEL_NAME)
