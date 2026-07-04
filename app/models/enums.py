import enum


class Role(enum.StrEnum):
    """Access-control roles.

    - accountant: reads client context within their own firm
    - firm_admin: accountant privileges + firm-level reporting
    - superuser: cross-firm (Ascend-level) reporting; not bound to a firm
    """

    accountant = "accountant"
    firm_admin = "firm_admin"
    superuser = "superuser"


class EmailDirection(enum.StrEnum):
    inbound = "inbound"  # client -> firm
    outbound = "outbound"  # firm -> client


class SummaryStatus(enum.StrEnum):
    ready = "ready"
    processing = "processing"
    failed = "failed"
