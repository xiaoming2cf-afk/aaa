from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from .config import Settings


PASSWORD_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_value: str) -> bool:
    try:
        iterations_text, salt_hex, digest_hex = stored_value.split("$", 2)
        iterations = int(iterations_text)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            iterations,
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_fernet(settings: Settings) -> Fernet:
    return Fernet(settings.get_encryption_key())


def encrypt_secret(settings: Settings, secret_value: str) -> str:
    return get_fernet(settings).encrypt(secret_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(settings: Settings, encrypted_value: str) -> str:
    return get_fernet(settings).decrypt(encrypted_value.encode("utf-8")).decode("utf-8")


def build_session_expiry(settings: Settings) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
