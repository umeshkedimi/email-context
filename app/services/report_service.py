import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.repositories.firm import FirmRepository
from app.repositories.report import ReportRepository
from app.schemas.auth import CurrentUser
from app.schemas.report import (
    ClientReportRow,
    FirmReport,
    FirmReportRow,
    NetworkReport,
)
from app.services.exceptions import FirmNotFound, ReportScopeError


def _staleness(
    total_emails: int, emails_analyzed: int | None, has_summary: bool
) -> tuple[int, bool]:
    """The single source of truth for staleness, identical to the summary
    endpoint: a client is stale if it has no summary yet, or has emails that
    the summary hasn't analyzed. Returns (new_emails_count, is_stale)."""
    analyzed = emails_analyzed or 0
    new_emails = max(total_emails - analyzed, 0)
    is_stale = (not has_summary) or new_emails > 0
    return new_emails, is_stale


class ReportService:
    """Firm-level and network-level reporting. Reads metadata only; never
    decrypts a summary payload."""

    def __init__(self, db: AsyncSession):
        self.reports = ReportRepository(db)
        self.firms = FirmRepository(db)

    async def firm_report(self, user: CurrentUser, firm_id: uuid.UUID | None) -> FirmReport:
        target = self._resolve_firm_scope(user, firm_id)

        firm = await self.firms.get_by_id(target)
        if firm is None:
            raise FirmNotFound

        rows = await self.reports.firm_client_rows(target)
        clients: list[ClientReportRow] = []
        for r in rows:
            has_summary = r.summary_id is not None
            new_emails, is_stale = _staleness(r.total_emails, r.emails_analyzed_count, has_summary)
            clients.append(
                ClientReportRow(
                    client_id=r.client_id,
                    client_name=r.client_name,
                    client_email=r.client_email,
                    total_emails=r.total_emails,
                    emails_analyzed_count=r.emails_analyzed_count or 0,
                    new_emails_count=new_emails,
                    has_summary=has_summary,
                    is_stale=is_stale,
                    last_refreshed_at=r.last_refreshed_at,
                )
            )

        return FirmReport(
            firm_id=firm.id,
            firm_name=firm.name,
            total_clients=len(clients),
            clients_with_summary=sum(1 for c in clients if c.has_summary),
            clients_stale=sum(1 for c in clients if c.is_stale),
            total_emails=sum(c.total_emails for c in clients),
            clients=clients,
        )

    async def network_report(self, user: CurrentUser) -> NetworkReport:
        rows = await self.reports.network_firm_rows()
        firms = [
            FirmReportRow(
                firm_id=r.firm_id,
                firm_name=r.firm_name,
                total_clients=r.total_clients,
                clients_with_summary=r.clients_with_summary,
                clients_stale=r.clients_stale,
                total_emails=r.total_emails,
            )
            for r in rows
        ]
        return NetworkReport(
            total_firms=len(firms),
            total_clients=sum(f.total_clients for f in firms),
            clients_with_summary=sum(f.clients_with_summary for f in firms),
            clients_stale=sum(f.clients_stale for f in firms),
            total_emails=sum(f.total_emails for f in firms),
            firms=firms,
        )

    def _resolve_firm_scope(self, user: CurrentUser, firm_id: uuid.UUID | None) -> uuid.UUID:
        """Decide which firm a firm report targets.

        - superuser: belongs to no firm, so must name one explicitly.
        - firm_admin: always their own firm; asking for a different one is
          indistinguishable from that firm not existing (404), matching the
          non-disclosure posture used for clients.
        """
        if user.role == Role.superuser:
            if firm_id is None:
                raise ReportScopeError
            return firm_id

        if user.firm_id is None:
            raise FirmNotFound
        own_firm = uuid.UUID(user.firm_id)
        if firm_id is not None and firm_id != own_firm:
            raise FirmNotFound
        return own_firm
