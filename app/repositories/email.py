import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email


class EmailRepository:
    """Data access for emails. Reads use the (client_id, sent_at) index."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_client(self, client_id: uuid.UUID) -> list[Email]:
        """All emails for a client, oldest first — the summarization input order."""
        result = await self.db.execute(
            select(Email).where(Email.client_id == client_id).order_by(Email.sent_at.asc())
        )
        return list(result.scalars().all())

    async def count_for_client(self, client_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Email).where(Email.client_id == client_id)
        )
        return int(result.scalar_one())
