"""Password hashing (bcrypt) and JWT issue/verify.

Kept free of any web-framework or DB imports so it stays a pure, unit-testable
security core.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt (salt is generated and embedded in the hash)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # Malformed hash in the DB — treat as a failed login, never raise to caller.
        return False


def create_access_token(*, subject: str, role: str, firm_id: str | None) -> str:
    """Issue a signed JWT carrying the claims authorization needs (id, role, firm)
    so protected endpoints don't need a DB round-trip just to authorize."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "firm_id": firm_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises jwt.PyJWTError on any invalid/expired token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
