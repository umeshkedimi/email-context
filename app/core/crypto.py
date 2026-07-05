"""Application-level encryption at rest for sensitive summary payloads.

Uses AES-256-GCM, an AEAD cipher: it provides confidentiality *and* integrity —
decryption fails (raises) if the ciphertext, nonce, or associated data was
tampered with, so a corrupted or swapped row can never be silently trusted.

Design notes (see docs/DESIGN.md):
- A fresh random 96-bit nonce is generated per encryption. GCM's security depends
  on never reusing a (key, nonce) pair, so the nonce is stored alongside the
  ciphertext and never derived deterministically.
- Each ciphertext records the `key_version` that produced it. Decryption looks the
  key up by version in a keyring, so keys can be rotated: a new active key starts
  encrypting new rows while old rows stay decryptable under their recorded version.
- Optional `associated_data` (AAD) is authenticated but not encrypted. Callers bind
  a ciphertext to its logical owner (e.g. the client id) so a valid blob copied
  onto a different row fails integrity checks.

Kept free of web/DB imports so it stays a pure, unit-testable crypto core.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_AES_256_KEY_BYTES = 32
_GCM_NONCE_BYTES = 12  # 96-bit nonce is the GCM-recommended size.


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """The three columns a caller must persist to later recover the plaintext."""

    ciphertext: bytes
    nonce: bytes
    key_version: int


class DecryptionError(Exception):
    """Raised when a payload cannot be authenticated/decrypted (tamper, wrong key,
    or an unknown key version). Never expose the cause to clients."""


class SummaryEncryptor:
    """AES-256-GCM encrypt/decrypt over a versioned keyring."""

    def __init__(self, keyring: dict[int, bytes], active_version: int):
        if active_version not in keyring:
            raise ValueError("active key version is not present in the keyring")
        for version, key in keyring.items():
            if len(key) != _AES_256_KEY_BYTES:
                raise ValueError(
                    f"key for version {version} must be {_AES_256_KEY_BYTES} bytes for AES-256"
                )
        self._keyring = keyring
        self._active_version = active_version

    def encrypt(
        self, plaintext: bytes, *, associated_data: bytes | None = None
    ) -> EncryptedPayload:
        """Encrypt with the active key. A new random nonce is used every call."""
        nonce = os.urandom(_GCM_NONCE_BYTES)
        aead = AESGCM(self._keyring[self._active_version])
        ciphertext = aead.encrypt(nonce, plaintext, associated_data)
        return EncryptedPayload(ciphertext, nonce, self._active_version)

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        key_version: int,
        *,
        associated_data: bytes | None = None,
    ) -> bytes:
        """Recover the plaintext, verifying integrity. Raises DecryptionError on any
        failure (unknown version, wrong key, tampered ciphertext/nonce/AAD)."""
        key = self._keyring.get(key_version)
        if key is None:
            raise DecryptionError(f"no key for version {key_version}")
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, associated_data)
        except Exception as exc:  # cryptography raises InvalidTag; don't leak specifics
            raise DecryptionError("payload failed authentication") from exc


def _load_key(b64_key: str) -> bytes:
    if not b64_key:
        raise ValueError(
            "SUMMARY_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(b64_key, validate=True)
    except Exception as exc:
        raise ValueError("SUMMARY_ENCRYPTION_KEY must be valid base64") from exc
    if len(key) != _AES_256_KEY_BYTES:
        raise ValueError("SUMMARY_ENCRYPTION_KEY must decode to 32 bytes (AES-256)")
    return key


@lru_cache
def get_encryptor() -> SummaryEncryptor:
    """Build the process-wide encryptor from settings (validated on first use, so a
    missing/invalid key fails loudly the moment encryption is needed, not at import).

    To rotate keys, add retired versions to this keyring (e.g. from additional env
    vars) while bumping the active version; old rows stay decryptable.
    """
    settings = get_settings()
    version = settings.summary_encryption_key_version
    keyring = {version: _load_key(settings.summary_encryption_key)}
    return SummaryEncryptor(keyring, active_version=version)
