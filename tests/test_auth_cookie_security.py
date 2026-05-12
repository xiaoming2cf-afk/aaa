from __future__ import annotations

from fastapi.testclient import TestClient


def _reset_app_caches() -> None:
    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


def _cookie_headers(response) -> list[str]:
    get_list = getattr(response.headers, "get_list", None)
    if callable(get_list):
        return list(get_list("set-cookie"))
    value = response.headers.get("set-cookie", "")
    return [part.strip() for part in value.split(", ") if part.strip()]


def test_auth_cookies_have_safe_defaults(client):
    response = client.post(
        "/api/auth/register",
        headers={"Origin": "http://testserver"},
        json={"email": "cookie@example.com", "password": "StrongPass!2026", "full_name": "Cookie User"},
    )
    assert response.status_code == 200, response.text
    cookies = "\n".join(_cookie_headers(response)).lower()

    session_line = next(line.lower() for line in _cookie_headers(response) if line.startswith("erp_session_token="))
    csrf_line = next(line.lower() for line in _cookie_headers(response) if line.startswith("erp_csrf_token="))
    assert "httponly" in session_line
    assert "samesite=lax" in session_line
    assert "samesite=lax" in csrf_line
    assert "httponly" not in csrf_line
    assert "erp_session_token" in cookies
    assert "erp_csrf_token" in cookies


def test_auth_cookies_are_secure_for_https_public_base_url(monkeypatch, app_env):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://testserver")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://testserver")
    _reset_app_caches()
    from research_agent.webapp import create_app

    client = TestClient(create_app(), base_url="https://testserver")
    response = client.post(
        "/api/auth/register",
        headers={"Origin": "https://testserver"},
        json={"email": "secure-cookie@example.com", "password": "StrongPass!2026", "full_name": "Secure Cookie"},
    )
    assert response.status_code == 200, response.text
    for line in _cookie_headers(response):
        lowered = line.lower()
        if lowered.startswith(("erp_session_token=", "erp_csrf_token=")):
            assert "secure" in lowered
            assert "samesite=lax" in lowered
    _reset_app_caches()


def test_cookie_session_write_requests_require_valid_csrf_token(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    valid_csrf = auth_headers["csrf"]

    missing = client.post(
        "/api/workspaces",
        json={"name": "Missing CSRF", "description": "should fail"},
    )
    assert missing.status_code == 403

    wrong = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": "wrong-token"},
        json={"name": "Wrong CSRF", "description": "should fail"},
    )
    assert wrong.status_code == 403

    cross_site = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": valid_csrf, "Origin": "https://evil.example"},
        data={"description": "cross-site upload"},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert cross_site.status_code == 403


def test_auth_post_requires_same_origin_metadata(client):
    missing_origin = client.post(
        "/api/auth/register",
        json={"email": "missing-origin@example.com", "password": "StrongPass!2026", "full_name": "Missing Origin"},
    )
    assert missing_origin.status_code == 403

    cross_site = client.post(
        "/api/auth/register",
        headers={"Origin": "https://evil.example"},
        json={"email": "cross-site@example.com", "password": "StrongPass!2026", "full_name": "Cross Site"},
    )
    assert cross_site.status_code == 403
