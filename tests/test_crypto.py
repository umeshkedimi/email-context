"""Unit tests for the AES-256-GCM encryption core (no DB, no app settings)."""

import os

import pytest

from app.core.crypto import DecryptionError, SummaryEncryptor

K1 = b"A" * 32
K2 = b"B" * 32


def _enc(active: int = 1, keyring: dict | None = None) -> SummaryEncryptor:
    return SummaryEncryptor(keyring or {1: K1}, active_version=active)


def test_round_trip_recovers_plaintext():
    enc = _enc()
    plaintext = b"top secret summary"
    payload = enc.encrypt(plaintext)
    assert enc.decrypt(payload.ciphertext, payload.nonce, payload.key_version) == plaintext


def test_nonce_is_random_per_call():
    enc = _enc()
    a = enc.encrypt(b"same plaintext")
    b = enc.encrypt(b"same plaintext")
    # Fresh nonce every call -> identical plaintext yields different ciphertext.
    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext


def test_associated_data_binds_ciphertext():
    enc = _enc()
    payload = enc.encrypt(b"summary", associated_data=b"client-123")
    # Correct AAD decrypts.
    assert (
        enc.decrypt(
            payload.ciphertext, payload.nonce, payload.key_version, associated_data=b"client-123"
        )
        == b"summary"
    )
    # A different client's AAD (a replayed blob) fails authentication.
    with pytest.raises(DecryptionError):
        enc.decrypt(
            payload.ciphertext, payload.nonce, payload.key_version, associated_data=b"client-999"
        )
    # Missing AAD also fails.
    with pytest.raises(DecryptionError):
        enc.decrypt(payload.ciphertext, payload.nonce, payload.key_version)


def test_tampered_ciphertext_is_rejected():
    enc = _enc()
    payload = enc.encrypt(b"summary")
    tampered = bytearray(payload.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(DecryptionError):
        enc.decrypt(bytes(tampered), payload.nonce, payload.key_version)


def test_unknown_key_version_is_rejected():
    enc = _enc()
    payload = enc.encrypt(b"summary")
    with pytest.raises(DecryptionError):
        enc.decrypt(payload.ciphertext, payload.nonce, key_version=99)


def test_key_rotation_old_rows_stay_decryptable():
    # v1 rows written earlier, v2 is now active. Same keyring decrypts both.
    old = _enc(active=1, keyring={1: K1})
    old_row = old.encrypt(b"old summary")

    rotated = SummaryEncryptor({1: K1, 2: K2}, active_version=2)
    new_row = rotated.encrypt(b"new summary")

    assert new_row.key_version == 2  # new writes use the active key
    assert rotated.decrypt(old_row.ciphertext, old_row.nonce, old_row.key_version) == b"old summary"
    assert rotated.decrypt(new_row.ciphertext, new_row.nonce, new_row.key_version) == b"new summary"


def test_wrong_key_for_version_is_rejected():
    payload = _enc(active=1, keyring={1: K1}).encrypt(b"summary")
    wrong = SummaryEncryptor({1: K2}, active_version=1)  # same version, different key
    with pytest.raises(DecryptionError):
        wrong.decrypt(payload.ciphertext, payload.nonce, payload.key_version)


@pytest.mark.parametrize("bad_len", [16, 24, 31, 33])
def test_rejects_non_256_bit_keys(bad_len):
    with pytest.raises(ValueError):
        SummaryEncryptor({1: os.urandom(bad_len)}, active_version=1)


def test_active_version_must_be_in_keyring():
    with pytest.raises(ValueError):
        SummaryEncryptor({1: K1}, active_version=2)
