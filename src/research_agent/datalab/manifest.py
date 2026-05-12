from __future__ import annotations

from pathlib import Path
from typing import Any


_SENSITIVE_KEYS = {"api_key", "token", "cookie", "secret", "password", "database_url", "service_role_key"}


def sanitize_manifest_value(value: Any) -> Any:
    """Return a JSON-safe manifest value without local paths or obvious secrets."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in _SENSITIVE_KEYS):
                continue
            if lowered in {"file_path", "path", "local_path"}:
                text = str(item or "")
                if _looks_like_local_path(text):
                    continue
            sanitized[key_text] = sanitize_manifest_value(item)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_manifest_value(item) for item in value]
    if isinstance(value, Path):
        return ""
    if isinstance(value, str) and _looks_like_local_path(value):
        return ""
    return value


def _looks_like_local_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if "/tmp/" in text.replace("\\", "/") or text.startswith("/tmp"):
        return True
    if text.startswith(("/", "\\")):
        return True
    return len(text) > 2 and text[1:3] in {":\\", ":/"}
