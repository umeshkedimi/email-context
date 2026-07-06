"""Schemas for the firm and network reports.

Reports expose only metadata (counts, staleness, timestamps) — never the
encrypted summary content — so they are safe for firm admins and the Ascend
superuser to read without decrypting anything.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class ClientReportRow(BaseModel):
    """One client's status line in a firm report."""

    client_id: uuid.UUID
    client_name: str
    client_email: EmailStr
    total_emails: int
    emails_analyzed_count: int
    new_emails_count: int  # emails not yet reflected in the summary
    has_summary: bool
    is_stale: bool  # no summary yet, or new_emails_count > 0
    last_refreshed_at: datetime | None = None


class FirmReport(BaseModel):
    """A single firm's dashboard: headline counts plus per-client detail."""

    firm_id: uuid.UUID
    firm_name: str
    total_clients: int
    clients_with_summary: int
    clients_stale: int
    total_emails: int
    clients: list[ClientReportRow]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "firm_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "firm_name": "Sterling & Vance CPAs",
                    "total_clients": 4,
                    "clients_with_summary": 3,
                    "clients_stale": 1,
                    "total_emails": 34,
                    "clients": [
                        {
                            "client_id": "3f9a1b2c-4d5e-6f70-8192-a3b4c5d6e7f8",
                            "client_name": "Hartley Family",
                            "client_email": "hartley.family@example.com",
                            "total_emails": 9,
                            "emails_analyzed_count": 8,
                            "new_emails_count": 1,
                            "has_summary": True,
                            "is_stale": True,
                            "last_refreshed_at": "2026-07-01T14:30:00Z",
                        }
                    ],
                }
            ]
        }
    )


class FirmReportRow(BaseModel):
    """A single firm's aggregate line in the network report."""

    firm_id: uuid.UUID
    firm_name: str
    total_clients: int
    clients_with_summary: int
    clients_stale: int
    total_emails: int


class NetworkReport(BaseModel):
    """Ascend-wide rollup for the superuser: network totals plus a per-firm
    breakdown. No per-client detail — that is the firm report's job."""

    total_firms: int
    total_clients: int
    clients_with_summary: int
    clients_stale: int
    total_emails: int
    firms: list[FirmReportRow]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total_firms": 2,
                    "total_clients": 6,
                    "clients_with_summary": 4,
                    "clients_stale": 3,
                    "total_emails": 40,
                    "firms": [
                        {
                            "firm_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            "firm_name": "Sterling & Vance CPAs",
                            "total_clients": 4,
                            "clients_with_summary": 3,
                            "clients_stale": 1,
                            "total_emails": 34,
                        }
                    ],
                }
            ]
        }
    )
