"""Encrypt / decrypt GitHub access tokens at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import AppError


def _fernet() -> Fernet:
    """Derive a stable Fernet key from JWT secret (dev-friendly)."""
    digest = hashlib.sha256(get_settings().jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError("Stored GitHub token is invalid", code="github_token_invalid") from exc
