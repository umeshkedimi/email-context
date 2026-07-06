"""Unit tests for password hashing and JWT issue/verify."""

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


def test_hash_is_salted():
    # Same password hashed twice -> different hashes (random salt).
    assert hash_password("pw") != hash_password("pw")


def test_verify_tolerates_malformed_hash():
    # A garbage hash in the DB must fail login, never raise.
    assert verify_password("pw", "not-a-bcrypt-hash") is False


def test_token_carries_claims():
    token = create_access_token(subject="user-1", role="firm_admin", firm_id="firm-1")
    claims = decode_access_token(token)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "firm_admin"
    assert claims["firm_id"] == "firm-1"


def test_superuser_token_allows_null_firm():
    token = create_access_token(subject="root", role="superuser", firm_id=None)
    assert decode_access_token(token)["firm_id"] is None


def test_tampered_token_is_rejected():
    token = create_access_token(subject="u", role="accountant", firm_id="f")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "x")


def test_token_signed_with_other_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "u", "role": "superuser", "firm_id": None}, "attacker-secret", algorithm="HS256"
    )
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(forged)
