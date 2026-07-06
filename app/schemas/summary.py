"""Schemas for the LLM summarization boundary.

`SummaryPayload` is the structured intelligence the model must return; it is also
exactly what we encrypt at rest and (decrypted) return to the dashboard. Keeping
one schema for all three roles guarantees the shape is validated once and stays
consistent end to end.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class SummaryResponse(BaseModel):
    """What the dashboard receives for one client. `payload` is null until a
    summary has been generated. Staleness is computed live on every read."""

    client_id: str
    client_name: str
    client_email: str

    generated: bool  # has a summary ever been produced for this client?
    payload: SummaryPayload | None = None

    total_emails_count: int
    emails_analyzed_count: int
    new_emails_count: int  # emails not yet reflected in the summary
    is_stale: bool  # new_emails_count > 0 (or never generated)

    status: str | None = None
    model_used: str | None = None
    last_refreshed_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "client_id": "3f9a1b2c-4d5e-6f70-8192-a3b4c5d6e7f8",
                    "client_name": "Hartley Family",
                    "client_email": "hartley.family@example.com",
                    "generated": True,
                    "payload": {
                        "overview": "The Hartleys' 2024 joint return is underway. Filing "
                        "status is settled; we are waiting on their W-2s before the "
                        "return can be drafted.",
                        "actors": [
                            {"name": "Jane Hartley", "role": "client"},
                            {"name": "Diane Sterling", "role": "accountant"},
                        ],
                        "concluded_discussions": [
                            "Filing status confirmed as married filing jointly"
                        ],
                        "open_action_items": [
                            {"description": "Send 2024 W-2 forms", "owner": "Jane Hartley"}
                        ],
                    },
                    "total_emails_count": 9,
                    "emails_analyzed_count": 8,
                    "new_emails_count": 1,
                    "is_stale": True,
                    "status": "ready",
                    "model_used": "gpt-4o-mini",
                    "last_refreshed_at": "2026-07-01T14:30:00Z",
                    "updated_at": "2026-07-01T14:30:00Z",
                }
            ]
        }
    )
