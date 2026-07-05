import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_summary import EmailSummary
from app.models.enums import SummaryStatus


class EmailSummaryRepository:
    """Data access for the one-per-client summary row."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_client(self, client_id: uuid.UUID) -> EmailSummary | None:
        result = await self.db.execute(
            select(EmailSummary).where(EmailSummary.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        client_id: uuid.UUID,
        firm_id: uuid.UUID,
        payload_encrypted: bytes,
        nonce: bytes,
        key_version: int,
        emails_analyzed_count: int,
        last_refreshed_at: datetime,
        model_used: str,
        status: SummaryStatus = SummaryStatus.ready,
    ) -> EmailSummary:
        """Create the client's summary row, or update it in place if it exists.
        The caller owns the transaction (commit happens in the service)."""
        summary = await self.get_by_client(client_id)
        if summary is None:
            summary = EmailSummary(client_id=client_id, firm_id=firm_id)
            self.db.add(summary)
        summary.payload_encrypted = payload_encrypted
        summary.nonce = nonce
        summary.key_version = key_version
        summary.emails_analyzed_count = emails_analyzed_count
        summary.last_refreshed_at = last_refreshed_at
        summary.model_used = model_used
        summary.status = status
        return summary
