from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import SplitResult, urlsplit, urlunsplit

from cryptography.fernet import Fernet

from .config import Settings


PASSWORD_ITERATIONS = 390_000
_DEV_APP_ENVS = {"development", "dev", "test", "testing"}
_LOCAL_HOSTS = {"localhost", "testserver"}
_WEAK_PASSWORDS = {
    "password",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "aaaaaaaaaaaa",
    "letmein123",
}


class RateLimitError(Exception):
    pass


class AccountLockedError(Exception):
    pass


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


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(24)


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


def build_password_reset_expiry(*, ttl_minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=max(1, int(ttl_minutes)))


def validate_password_strength(password: str, *, email: str = "") -> str:
    value = str(password or "")
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must include a lowercase letter.")
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must include an uppercase letter.")
    if not re.search(r"\d", value):
        raise ValueError("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", value):
        raise ValueError("Password must include a special character.")
    lowered = value.lower()
    if lowered in _WEAK_PASSWORDS:
        raise ValueError("Password is too common.")
    if re.fullmatch(r"(.)\1{11,}", value):
        raise ValueError("Password must not repeat the same character.")
    local_part = str(email or "").split("@", 1)[0].strip().lower()
    if len(local_part) >= 4 and local_part in lowered:
        raise ValueError("Password must not contain the email name.")
    if re.search(r"(1234|abcd|qwer|password)", lowered):
        raise ValueError("Password is too predictable.")
    return value


def _is_relaxed_app_env(settings: Settings) -> bool:
    return settings.app_env.strip().lower() in _DEV_APP_ENVS


def _format_netloc(hostname: str, port: int | None) -> str:
    host = hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is None:
        return host
    return f"{host}:{port}"


def _normalized_split_url(raw_url: str, *, field_name: str) -> SplitResult:
    if not raw_url.strip():
        raise ValueError(f"{field_name} is required.")
    parsed = urlsplit(raw_url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if scheme not in {"http", "https"}:
        raise ValueError(f"{field_name} must use http or https.")
    if not parsed.netloc or not hostname:
        raise ValueError(f"{field_name} must include a valid host.")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include credentials.")
    return SplitResult(
        scheme=scheme,
        netloc=_format_netloc(hostname, parsed.port),
        path=parsed.path or "",
        query=parsed.query or "",
        fragment=parsed.fragment or "",
    )


def _host_is_local_name(hostname: str) -> bool:
    return hostname in _LOCAL_HOSTS or hostname.endswith(".localhost")


def _host_is_non_public_ip(hostname: str) -> bool:
    try:
        return not ipaddress.ip_address(hostname).is_global
    except ValueError:
        return False


def validate_optional_source_url(url: str, *, field_name: str = "Source URL") -> str:
    raw_value = (url or "").strip()
    if not raw_value:
        return ""
    parsed = _normalized_split_url(raw_value, field_name=field_name)
    return urlunsplit(parsed)


def validate_external_fetch_url(url: str, *, field_name: str = "External URL") -> str:
    raw_value = (url or "").strip()
    if not raw_value:
        return ""
    parsed = _normalized_split_url(raw_value, field_name=field_name)
    hostname = parsed.hostname or ""
    if _host_is_local_name(hostname) or _host_is_non_public_ip(hostname):
        raise ValueError(f"{field_name} must not target localhost or private network addresses.")
    return urlunsplit(parsed)


def validate_provider_base_url(settings: Settings, url: str) -> str:
    raw_value = (url or "").strip()
    if not raw_value:
        return ""
    parsed = _normalized_split_url(raw_value, field_name="Provider base URL")
    hostname = parsed.hostname or ""
    if parsed.query or parsed.fragment:
        raise ValueError("Provider base URL must not include query parameters or fragments.")
    if _is_relaxed_app_env(settings):
        return urlunsplit(parsed)
    if parsed.scheme != "https":
        raise ValueError("Provider base URL must use HTTPS outside development or test.")
    if _host_is_local_name(hostname) or _host_is_non_public_ip(hostname):
        raise ValueError("Provider base URL must not target localhost or private network addresses.")
    return urlunsplit(parsed)
