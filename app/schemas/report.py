"""Schemas for the firm and network reports.

Reports expose only metadata (counts, staleness, timestamps) — never the
encrypted summary content — so they are safe for firm admins and the Ascend
superuser to read without decrypting anything.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


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
