from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Login credentials. EmailStr validates format before we touch the DB."""

    email: EmailStr
    password: str = Field(min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "diane.sterling@sterlingvance.com", "password": "Demo1234!"}]
        }
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIuLi4ifQ.sig",
                    "token_type": "bearer",
                }
            ]
        }
    )


class CurrentUser(BaseModel):
    """The authenticated principal, resolved from a verified JWT + DB lookup."""

    id: str
    email: EmailStr
    name: str
    role: str
    firm_id: str | None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "b3d1c2e4-5f6a-47b8-9c0d-1e2f3a4b5c6d",
                    "email": "diane.sterling@sterlingvance.com",
                    "name": "Diane Sterling",
                    "role": "firm_admin",
                    "firm_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                }
            ]
        }
    )
