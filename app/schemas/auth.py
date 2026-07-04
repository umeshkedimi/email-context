from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login credentials. EmailStr validates format before we touch the DB."""

    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    """The authenticated principal, resolved from a verified JWT + DB lookup."""

    id: str
    email: EmailStr
    name: str
    role: str
    firm_id: str | None
