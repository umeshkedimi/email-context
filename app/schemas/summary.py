"""Schemas for the LLM summarization boundary.

`SummaryPayload` is the structured intelligence the model must return; it is also
exactly what we encrypt at rest and (decrypted) return to the dashboard. Keeping
one schema for all three roles guarantees the shape is validated once and stays
consistent end to end.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Actor(BaseModel):
    """A person or entity involved in the client's discussions."""

    name: str
    role: str = Field(
        description="Their role/relationship in the discussions, "
        "e.g. 'client', 'accountant', 'IRS agent', 'spouse'."
    )


class ActionItem(BaseModel):
    """An open item still needing action."""

    description: str
    owner: str | None = Field(
        default=None, description="Who is responsible, if stated in the emails."
    )


class SummaryPayload(BaseModel):
    """Structured, model-generated state of one client relationship."""

    overview: str = Field(
        description="A 2-4 sentence plain-language summary of where things stand."
    )
    actors: list[Actor] = Field(default_factory=list)
    concluded_discussions: list[str] = Field(
        default_factory=list,
        description="Topics that reached a conclusion/decision, each as one line.",
    )
    open_action_items: list[ActionItem] = Field(default_factory=list)


class EmailForSummary(BaseModel):
    """One email, reduced to what the model needs to reason about."""

    sender: str
    direction: str  # inbound (client->firm) or outbound (firm->client)
    sent_at: datetime
    subject: str | None = None
    body: str


class SummaryContext(BaseModel):
    """The full input handed to a provider to summarize one client."""

    client_name: str
    client_email: str
    emails: list[EmailForSummary]


class SummaryResult(BaseModel):
    """A provider's output: the validated payload plus which model produced it
    (recorded on the summary row for traceability)."""

    payload: SummaryPayload
    model_used: str
