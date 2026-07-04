"""Import every model so its table is registered on Base.metadata for Alembic."""

from app.models.accountant import Accountant
from app.models.client import Client
from app.models.email import Email
from app.models.email_summary import EmailSummary
from app.models.enums import EmailDirection, Role, SummaryStatus
from app.models.firm import Firm

__all__ = [
    "Accountant",
    "Client",
    "Email",
    "EmailSummary",
    "EmailDirection",
    "Role",
    "SummaryStatus",
    "Firm",
]
