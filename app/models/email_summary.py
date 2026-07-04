import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import SummaryStatus


class EmailSummary(Base, TimestampMixin):
    """The processed intelligence for one client: actors, concluded discussions,
    and open action items.

    Sensitive at rest, so the structured payload is stored as AES-256-GCM
    ciphertext (`payload_encrypted` + `nonce`), never as plaintext. `key_version`
    records which encryption key produced it, enabling key rotation without a
    big-bang re-encrypt. Queryable/reporting fields (counts, timestamps,
    firm_id, status) stay in plaintext columns.
    """

    __tablename__ = "email_summaries"

    id: Mapped[uuid.UUID] = uuid_pk()
    # One rolling summary per client (confirmed with panel).
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id"), unique=True, nullable=False
    )
    # Denormalized for the admin/superuser reports, which count/group by firm.
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id"), index=True, nullable=False
    )

    # --- Encrypted payload ---
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(nullable=False)

    # --- Tracking (plaintext, queryable) ---
    emails_analyzed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SummaryStatus] = mapped_column(
        SAEnum(SummaryStatus, name="summary_status", native_enum=False, length=20),
        nullable=False,
        default=SummaryStatus.ready,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
