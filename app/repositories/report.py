import uuid
from collections.abc import Sequence

from sqlalchemy import Row, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.email import Email
from app.models.email_summary import EmailSummary
from app.models.firm import Firm


class ReportRepository:
    """Read-only aggregate queries for the firm and network reports.

    Everything here reads only plaintext metadata columns (counts, timestamps,
    firm_id) — never the encrypted summary payload. Reporting therefore needs no
    access to confidential content. All work is pushed into the database as
    grouped queries (no per-client N+1 round-trips).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _email_counts_subquery(self):
        """emails-per-client, computed once and joined by both reports."""
        return (
            select(Email.client_id, func.count().label("cnt")).group_by(Email.client_id).subquery()
        )

    async def firm_client_rows(self, firm_id: uuid.UUID) -> Sequence[Row]:
        """One row per client in the firm: name, email, total emails, and the
        summary's analyzed-count / last-refresh (NULL when no summary exists).
        Staleness is derived by the caller so it stays identical to the
        summary endpoint's formula."""
        email_counts = self._email_counts_subquery()
        stmt = (
            select(
                Client.id.label("client_id"),
                Client.name.label("client_name"),
                Client.email.label("client_email"),
                func.coalesce(email_counts.c.cnt, 0).label("total_emails"),
                EmailSummary.emails_analyzed_count,
                EmailSummary.last_refreshed_at,
                EmailSummary.id.label("summary_id"),
            )
            .select_from(Client)
            .outerjoin(EmailSummary, EmailSummary.client_id == Client.id)
            .outerjoin(email_counts, email_counts.c.client_id == Client.id)
            .where(Client.firm_id == firm_id)
            .order_by(Client.name)
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def network_firm_rows(self) -> Sequence[Row]:
        """One aggregate row per firm across the whole network: client count,
        clients with a summary, total emails, and stale-client count."""
        email_counts = self._email_counts_subquery()
        # A client is stale if it has no summary, or has more emails than were
        # analyzed. The first branch guards the empty-firm LEFT JOIN row
        # (Client.id NULL) so a client-less firm reports 0 stale, not 1.
        stale = case(
            (Client.id.is_(None), 0),
            (EmailSummary.id.is_(None), 1),
            (func.coalesce(email_counts.c.cnt, 0) > EmailSummary.emails_analyzed_count, 1),
            else_=0,
        )
        stmt = (
            select(
                Firm.id.label("firm_id"),
                Firm.name.label("firm_name"),
                func.count(func.distinct(Client.id)).label("total_clients"),
                func.count(func.distinct(EmailSummary.client_id)).label("clients_with_summary"),
                func.coalesce(func.sum(func.coalesce(email_counts.c.cnt, 0)), 0).label(
                    "total_emails"
                ),
                func.coalesce(func.sum(stale), 0).label("clients_stale"),
            )
            .select_from(Firm)
            .outerjoin(Client, Client.firm_id == Firm.id)
            .outerjoin(EmailSummary, EmailSummary.client_id == Client.id)
            .outerjoin(email_counts, email_counts.c.client_id == Client.id)
            .group_by(Firm.id, Firm.name)
            .order_by(Firm.name)
        )
        result = await self.db.execute(stmt)
        return result.all()
