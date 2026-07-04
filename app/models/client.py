import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk


class Client(Base, TimestampMixin):
    """An external entity (taxpayer) serviced by a firm. Scoped to exactly one
    firm — confirmed with the panel. The unique (firm_id, email) constraint lets
    two different firms independently have a client with the same email."""

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("firm_id", "email", name="uq_client_firm_email"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("firms.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)

    firm: Mapped["Firm"] = relationship(back_populates="clients")  # noqa: F821
