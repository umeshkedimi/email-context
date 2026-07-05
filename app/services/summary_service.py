"""Summary orchestration: read (cached, read-only) and refresh (the only LLM call).

Firm-scoping is enforced here: a client outside the caller's firm is indistinguishable
from a missing one (both raise ClientNotFound -> 404). The cache only ever holds the
*ciphertext* + metadata, so plaintext never leaves the process except in the response.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete, cache_get_json, cache_set_json
from app.core.config import get_settings
from app.core.crypto import get_encryptor
from app.models.client import Client
from app.models.enums import SummaryStatus
from app.repositories.client import ClientRepository
from app.repositories.email import EmailRepository
from app.repositories.email_summary import EmailSummaryRepository
from app.schemas.auth import CurrentUser
from app.schemas.summary import (
    EmailForSummary,
    SummaryContext,
    SummaryPayload,
    SummaryResponse,
)
from app.services.exceptions import ClientNotFound, NoEmailsToSummarize, SummaryGenerationError
from app.services.llm.factory import get_llm_provider

log = structlog.get_logger("app.summary")

_SUPERUSER = "superuser"


def _cache_key(client_id: uuid.UUID) -> str:
    return f"summary:{client_id}"


class SummaryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.clients = ClientRepository(db)
        self.emails = EmailRepository(db)
        self.summaries = EmailSummaryRepository(db)
        self.encryptor = get_encryptor()
        self.settings = get_settings()

    # --- helpers ---

    async def _load_client(self, client_id: uuid.UUID, user: CurrentUser) -> Client:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            raise ClientNotFound
        # Superuser is firm-less and may read any firm; everyone else is confined.
        if user.role != _SUPERUSER and str(client.firm_id) != user.firm_id:
            raise ClientNotFound  # 404, not 403 — don't reveal the row exists
        return client

    @staticmethod
    def _aad(client_id: uuid.UUID) -> bytes:
        """Bind a ciphertext to its client so a blob can't be replayed on another row."""
        return str(client_id).encode()

    # --- read (no LLM) ---

    async def get_summary(self, client_id: uuid.UUID, user: CurrentUser) -> SummaryResponse:
        client = await self._load_client(client_id, user)
        total = await self.emails.count_for_client(client_id)

        blob = await cache_get_json(_cache_key(client_id))
        if blob is None:
            blob = await self._read_model_from_db(client)
            await cache_set_json(
                _cache_key(client_id), blob, self.settings.summary_cache_ttl_seconds
            )
        return self._build_response(client_id, blob, total)

    async def _read_model_from_db(self, client: Client) -> dict:
        """A JSON-serializable, plaintext-free snapshot of the summary row for caching."""
        base = {"client_name": client.name, "client_email": client.email}
        summary = await self.summaries.get_by_client(client.id)
        if summary is None:
            return {**base, "generated": False, "emails_analyzed_count": 0}
        return {
            **base,
            "generated": True,
            "ciphertext_b64": base64.b64encode(summary.payload_encrypted).decode(),
            "nonce_b64": base64.b64encode(summary.nonce).decode(),
            "key_version": summary.key_version,
            "emails_analyzed_count": summary.emails_analyzed_count,
            "status": summary.status.value,
            "model_used": summary.model_used,
            "last_refreshed_at": (
                summary.last_refreshed_at.isoformat() if summary.last_refreshed_at else None
            ),
            "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
        }

    def _build_response(
        self, client_id: uuid.UUID, blob: dict, total_emails: int
    ) -> SummaryResponse:
        analyzed = blob.get("emails_analyzed_count", 0)
        new = max(total_emails - analyzed, 0)
        generated = blob.get("generated", False)

        payload: SummaryPayload | None = None
        if generated:
            plaintext = self.encryptor.decrypt(
                base64.b64decode(blob["ciphertext_b64"]),
                base64.b64decode(blob["nonce_b64"]),
                blob["key_version"],
                associated_data=self._aad(client_id),
            )
            payload = SummaryPayload.model_validate_json(plaintext)

        return SummaryResponse(
            client_id=str(client_id),
            client_name=blob["client_name"],
            client_email=blob["client_email"],
            generated=generated,
            payload=payload,
            total_emails_count=total_emails,
            emails_analyzed_count=analyzed,
            new_emails_count=new,
            is_stale=(not generated) or new > 0,
            status=blob.get("status"),
            model_used=blob.get("model_used"),
            last_refreshed_at=blob.get("last_refreshed_at"),
            updated_at=blob.get("updated_at"),
        )

    # --- refresh (the only LLM trigger) ---

    async def refresh_summary(self, client_id: uuid.UUID, user: CurrentUser) -> SummaryResponse:
        client = await self._load_client(client_id, user)
        emails = await self.emails.list_for_client(client_id)
        if not emails:
            raise NoEmailsToSummarize

        context = SummaryContext(
            client_name=client.name,
            client_email=client.email,
            emails=[
                EmailForSummary(
                    sender=e.sender,
                    direction=e.direction.value,
                    sent_at=e.sent_at,
                    subject=e.subject,
                    body=e.body,
                )
                for e in emails
            ],
        )

        provider = get_llm_provider()
        try:
            result = await provider.summarize(context)
        except Exception as exc:
            log.exception("summary_generation_failed", client_id=str(client_id))
            # Leave any existing good summary untouched.
            raise SummaryGenerationError from exc

        enc = self.encryptor.encrypt(
            result.payload.model_dump_json().encode(),
            associated_data=self._aad(client_id),
        )
        now = datetime.now(UTC)
        await self.summaries.upsert(
            client_id=client_id,
            firm_id=client.firm_id,
            payload_encrypted=enc.ciphertext,
            nonce=enc.nonce,
            key_version=enc.key_version,
            emails_analyzed_count=len(emails),
            last_refreshed_at=now,
            model_used=result.model_used,
            status=SummaryStatus.ready,
        )
        await self.db.commit()
        await cache_delete(_cache_key(client_id))

        log.info(
            "summary_refreshed",
            client_id=str(client_id),
            emails=len(emails),
            model=result.model_used,
        )
        return SummaryResponse(
            client_id=str(client_id),
            client_name=client.name,
            client_email=client.email,
            generated=True,
            payload=result.payload,
            total_emails_count=len(emails),
            emails_analyzed_count=len(emails),
            new_emails_count=0,
            is_stale=False,
            status=SummaryStatus.ready.value,
            model_used=result.model_used,
            last_refreshed_at=now,
            updated_at=now,
        )
