import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import Role


class Accountant(Base, TimestampMixin):
    """A user. Accountants and firm admins belong to a firm; superusers do not
    (firm_id is NULL) because they operate across the whole Ascend network."""

    __tablename__ = "accountants"

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("firms.id"), index=True, nullable=True
    )
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role", native_enum=False, length=20), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    firm: Mapped["Firm | None"] = relationship(back_populates="accountants")  # noqa: F821
