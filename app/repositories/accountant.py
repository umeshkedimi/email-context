import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accountant import Accountant


class AccountantRepository:
    """Data access for accountants. The service/API layers call these methods
    instead of writing queries directly, keeping persistence concerns in one place."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> Accountant | None:
        result = await self.db.execute(select(Accountant).where(Accountant.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, accountant_id: uuid.UUID) -> Accountant | None:
        return await self.db.get(Accountant, accountant_id)
