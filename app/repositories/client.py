import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client


class ClientRepository:
    """Data access for clients."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, client_id: uuid.UUID) -> Client | None:
        return await self.db.get(Client, client_id)
