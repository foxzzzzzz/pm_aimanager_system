from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PHONE_CONTEXT = b"project-manager:phone:v1"


class PhoneCipher:
    def __init__(self, encoded_key: str | None):
        if not encoded_key:
            raise ValueError("PHONE_ENCRYPTION_KEY is required")
        try:
            key = base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))
        except ValueError as exc:
            raise ValueError("PHONE_ENCRYPTION_KEY must be base64url encoded") from exc
        if len(key) != 32:
            raise ValueError("PHONE_ENCRYPTION_KEY must decode to 32 bytes")
        self._aes = AESGCM(key)

    def encrypt(self, phone: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, phone.encode("utf-8"), PHONE_CONTEXT)
        value = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
        return f"v1:{value}"

    def decrypt(self, envelope: str) -> str:
        version, separator, value = envelope.partition(":")
        if separator != ":" or version != "v1":
            raise ValueError("unsupported phone encryption envelope")
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return self._aes.decrypt(raw[:12], raw[12:], PHONE_CONTEXT).decode("utf-8")
