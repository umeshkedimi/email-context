import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import (
    CLIENT_NOT_FOUND,
    GENERATION_FAILED,
    NO_EMAILS,
    UNAUTHORIZED,
)
from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.summary import SummaryResponse
from app.services.summary_service import SummaryService

router = APIRouter(prefix="/clients", tags=["summaries"])


@router.get(
    "/{client_id}/summary",
    response_model=SummaryResponse,
    summary="Read a client's summary (+ live staleness)",
    responses={**UNAUTHORIZED, **CLIENT_NOT_FOUND},
)
async def get_summary(
    client_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    """Read the client's current summary. Read-only: never calls the LLM. Returns
    staleness (`new_emails_count`, `is_stale`) computed live against the inbox."""
    return await SummaryService(db).get_summary(client_id, user)


@router.post(
    "/{client_id}/summary/refresh",
    response_model=SummaryResponse,
    summary="Regenerate a client's summary (the only LLM call)",
    responses={**UNAUTHORIZED, **CLIENT_NOT_FOUND, **NO_EMAILS, **GENERATION_FAILED},
)
async def refresh_summary(
    client_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    """Regenerate the summary over the client's full email history. This is the
    only endpoint that invokes the LLM."""
    return await SummaryService(db).refresh_summary(client_id, user)
