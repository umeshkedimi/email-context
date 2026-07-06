import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import FIRM_NOT_FOUND, FORBIDDEN, REPORT_SCOPE, UNAUTHORIZED
from app.core.deps import require_roles
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.report import FirmReport, NetworkReport
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

# Role guards are dependency factories; build them once at import (B008) rather
# than calling require_roles(...) inline in each route's argument defaults.
_require_firm_reader = require_roles("firm_admin", "superuser")
_require_superuser = require_roles("superuser")


@router.get(
    "/firm",
    response_model=FirmReport,
    summary="Firm dashboard (client roster + staleness)",
    operation_id="read_firm_report",
    responses={**UNAUTHORIZED, **FORBIDDEN, **REPORT_SCOPE, **FIRM_NOT_FOUND},
)
async def firm_report(
    firm_id: uuid.UUID | None = Query(
        default=None,
        description="Which firm to report on. Required for superusers (who belong "
        "to no firm); ignored for firm admins, who always see their own firm.",
    ),
    user: CurrentUser = Depends(_require_firm_reader),
    db: AsyncSession = Depends(get_db),
) -> FirmReport:
    """Per-firm dashboard: client roster with summary status and staleness.
    A firm admin sees their own firm; a superuser names any firm."""
    return await ReportService(db).firm_report(user, firm_id)


@router.get(
    "/network",
    response_model=NetworkReport,
    summary="Network rollup across all firms",
    operation_id="read_network_report",
    responses={**UNAUTHORIZED, **FORBIDDEN},
)
async def network_report(
    user: CurrentUser = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
) -> NetworkReport:
    """Ascend-wide rollup across every firm. Superuser only."""
    return await ReportService(db).network_report(user)
