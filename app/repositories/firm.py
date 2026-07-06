import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.firm import Firm


class FirmRepository:
    """Data access for firms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, firm_id: uuid.UUID) -> Firm | None:
        return await self.db.get(Firm, firm_id)
