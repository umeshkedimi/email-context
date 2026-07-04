import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.repositories.accountant import AccountantRepository
from app.schemas.auth import CurrentUser

# Extracts "Authorization: Bearer <token>" and drives the Swagger "Authorize" button.
bearer_scheme = HTTPBearer(auto_error=True)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve the authenticated accountant from a verified JWT.

    We still load the row from the DB (rather than trusting claims blindly) so a
    deleted/disabled user can't keep acting on a still-valid token.
    """
    try:
        payload = decode_access_token(credentials.credentials)
        accountant_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED from None

    accountant = await AccountantRepository(db).get_by_id(accountant_id)
    if accountant is None:
        raise _UNAUTHORIZED

    return CurrentUser(
        id=str(accountant.id),
        email=accountant.email,
        name=accountant.name,
        role=accountant.role.value,
        firm_id=str(accountant.firm_id) if accountant.firm_id else None,
    )


def require_roles(
    *roles: str,
) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Dependency factory: allow only the given roles, else 403."""

    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource",
            )
        return user

    return checker
