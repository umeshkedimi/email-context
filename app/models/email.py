import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import EmailDirection


class Email(Base, TimestampMixin):
    """A single email in a client conversation. This is the mock inbox that
    stands in for the Microsoft Graph API. firm_id is denormalized so the mock
    provider and tenancy checks never need to join through Client."""

    __tablename__ = "emails"
    # The hot path: fetch all emails for a client in chronological order, and
    # count emails newer than the last summary refresh (staleness check).
    __table_args__ = (Index("ix_emails_client_sent", "client_id", "sent_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("firms.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    accountant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accountants.id"), nullable=True
    )

    thread_id: Mapped[str] = mapped_column(nullable=False, index=True)
    direction: Mapped[EmailDirection] = mapped_column(
        SAEnum(EmailDirection, name="email_direction", native_enum=False, length=10),
        nullable=False,
    )
    sender: Mapped[str] = mapped_column(nullable=False)
    subject: Mapped[str] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
