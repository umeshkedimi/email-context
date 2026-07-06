from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Uniform error body for every handled failure. FastAPI's exception handlers
    and `HTTPException` both emit `{"detail": "..."}`, so this one shape documents
    all of them."""

    detail: str = Field(
        description="Human-readable explanation of what went wrong.",
        examples=["Client not found"],
    )
