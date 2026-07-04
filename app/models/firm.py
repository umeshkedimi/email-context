import uuid

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk


class Firm(Base, TimestampMixin):
    """A CPA firm within the Ascend network. The tenancy boundary: accountants,
    clients, and summaries all belong to exactly one firm."""

    __tablename__ = "firms"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(nullable=False)

    accountants: Mapped[list["Accountant"]] = relationship(back_populates="firm")  # noqa: F821
    clients: Mapped[list["Client"]] = relationship(back_populates="firm")  # noqa: F821
