from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


def auth_headers(token: str, *, csrf_token: str = "", content_type: str = "") -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def same_origin_headers(base_url: str) -> dict[str, str]:
    parsed = urlsplit(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
    return {"Origin": origin}


def session_token_from_cookies(holder: Any) -> str:
    cookies = getattr(holder, "cookies", holder)
    token = cookies.get("erp_session_token") if cookies is not None else ""
    if not token:
        raise RuntimeError("Missing erp_session_token cookie after authentication.")
    return token


def csrf_token_from_cookies(holder: Any) -> str:
    cookies = getattr(holder, "cookies", holder)
    token = cookies.get("erp_csrf_token") if cookies is not None else ""
    if not token:
        raise RuntimeError("Missing erp_csrf_token cookie after authentication.")
    return token
