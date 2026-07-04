from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.repositories.accountant import AccountantRepository
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    accountant = await AccountantRepository(db).get_by_email(body.email)
    # Same error whether the email is unknown or the password is wrong — avoids
    # leaking which accounts exist (user-enumeration protection).
    if accountant is None or not verify_password(body.password, accountant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(
        subject=str(accountant.id),
        role=accountant.role.value,
        firm_id=str(accountant.firm_id) if accountant.firm_id else None,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CurrentUser)
async def me(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Return the authenticated principal — useful for verifying a token."""
    return current
