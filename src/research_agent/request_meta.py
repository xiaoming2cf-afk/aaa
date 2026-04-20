from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import Request

from .config import Settings


def _normalize_ip(value: str) -> str:
    return str(value or "").strip().strip("[]")


def _is_trusted_proxy(peer_host: str, settings: Settings) -> bool:
    candidate = _normalize_ip(peer_host)
    if not candidate:
        return False
    try:
        peer_ip = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate in settings.trusted_proxy_ip_list
    for raw_entry in settings.trusted_proxy_ip_list:
        try:
            if peer_ip in ipaddress.ip_network(raw_entry, strict=False):
                return True
        except ValueError:
            if candidate == _normalize_ip(raw_entry):
                return True
    return False


def request_ip(request: Request | None, settings: Settings) -> str:
    if not request:
        return ""
    direct_peer = str(request.client.host if request.client else "").strip()
    if not direct_peer:
        return ""
    if not _is_trusted_proxy(direct_peer, settings):
        return direct_peer
    forwarded = str(request.headers.get("x-forwarded-for", "")).strip()
    if not forwarded:
        return direct_peer
    for raw_part in forwarded.split(","):
        candidate = _normalize_ip(raw_part)
        if candidate:
            return candidate
    return direct_peer


def _normalized_origin(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    parsed = urlsplit(raw_value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def allowed_request_origins(request: Request, settings: Settings) -> set[str]:
    origins = {_normalized_origin(str(request.base_url))}
    origins.update(
        origin
        for origin in (_normalized_origin(item) for item in settings.allowed_origin_list)
        if origin
    )
    return origins


def validate_same_origin_request(request: Request, settings: Settings, *, require_header: bool) -> None:
    supplied = str(request.headers.get("origin") or request.headers.get("referer") or "").strip()
    if not supplied:
        if require_header:
            raise PermissionError("Missing same-origin request metadata.")
        return
    normalized = _normalized_origin(supplied)
    if not normalized or normalized not in allowed_request_origins(request, settings):
        raise PermissionError("Cross-site request blocked.")
