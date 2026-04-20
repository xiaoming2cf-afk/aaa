from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from research_agent.entities import AuditLogEvent


SAME_ORIGIN_HEADERS = {"Origin": "http://testserver"}


def test_csrf_enforced_for_cookie_session_and_audit_written(client, db_session):
    register = client.post(
        "/api/auth/register",
        headers=SAME_ORIGIN_HEADERS,
        json={
            "email": "audit@example.com",
            "password": "StrongPass!2026",
            "full_name": "Audit User",
        },
    )
    assert register.status_code == 200, register.text
    assert "session_token" not in register.json()
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token

    blocked = client.post(
        "/api/workspaces",
        json={"name": "Blocked Workspace", "description": "should fail without csrf"},
    )
    assert blocked.status_code == 403

    created = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Allowed Workspace", "description": "with csrf"},
    )
    assert created.status_code == 200, created.text

    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 200

    actions = list(db_session.scalars(select(AuditLogEvent.action)))
    assert "auth.register" in actions
    assert "workspace.create" in actions
    assert "auth.logout" in actions


def test_password_reset_clears_lock_and_allows_new_password(client, monkeypatch):
    sent_messages: list[str] = []
    observed_ttls: list[int] = []

    def fake_send_password_reset_email(settings, *, recipient: str, reset_url: str, ttl_minutes: int) -> None:
        sent_messages.append(reset_url)
        observed_ttls.append(ttl_minutes)

    monkeypatch.setattr("research_agent.webapp.send_password_reset_email", fake_send_password_reset_email)

    register = client.post(
        "/api/auth/register",
        headers=SAME_ORIGIN_HEADERS,
        json={
            "email": "locked@example.com",
            "password": "StrongPass!2026",
            "full_name": "Locked User",
        },
    )
    assert register.status_code == 200
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

    for _ in range(5):
        failed = client.post(
            "/api/auth/login",
            headers=SAME_ORIGIN_HEADERS,
            json={"email": "locked@example.com", "password": "WrongPass!2026"},
        )
        assert failed.status_code in {401, 423}
    locked = client.post(
        "/api/auth/login",
        headers=SAME_ORIGIN_HEADERS,
        json={"email": "locked@example.com", "password": "WrongPass!2026"},
    )
    assert locked.status_code == 423

    reset_request = client.post(
        "/api/auth/password-reset/request",
        headers=SAME_ORIGIN_HEADERS,
        json={"email": "locked@example.com"},
    )
    assert reset_request.status_code == 200
    assert sent_messages
    assert observed_ttls == [30]
    reset_url = sent_messages[-1]
    parsed_reset_url = urlparse(reset_url)
    assert "reset_token=" not in parsed_reset_url.query
    token = parse_qs(parsed_reset_url.fragment)["reset_token"][0]

    confirmed = client.post(
        "/api/auth/password-reset/confirm",
        headers=SAME_ORIGIN_HEADERS,
        json={"token": token, "password": "NewStrongPass!2027"},
    )
    assert confirmed.status_code == 200, confirmed.text

    login = client.post(
        "/api/auth/login",
        headers=SAME_ORIGIN_HEADERS,
        json={"email": "locked@example.com", "password": "NewStrongPass!2027"},
    )
    assert login.status_code == 200, login.text
    assert "session_token" not in login.json()


def test_auth_me_clears_stale_session_and_csrf_cookies(client):
    client.cookies.set("erp_session_token", "stale-session-token")
    client.cookies.set("erp_csrf_token", "stale-csrf-token")

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("erp_session_token=" in item for item in set_cookie_headers)
    assert any("erp_csrf_token=" in item for item in set_cookie_headers)


def test_register_is_not_blocked_by_stale_invalid_session_cookie(client):
    client.cookies.set("erp_session_token", "stale-session-token")

    response = client.post(
        "/api/auth/register",
        headers=SAME_ORIGIN_HEADERS,
        json={
            "email": "stale-cookie-register@example.com",
            "password": "StrongPass!2026",
            "full_name": "Stale Cookie Register",
        },
    )

    assert response.status_code == 200, response.text


def test_auth_endpoints_require_same_origin_metadata(client):
    register = client.post(
        "/api/auth/register",
        json={
            "email": "cross-site@example.com",
            "password": "StrongPass!2026",
            "full_name": "Cross Site",
        },
    )
    assert register.status_code == 403

    login = client.post(
        "/api/auth/login",
        json={"email": "cross-site@example.com", "password": "StrongPass!2026"},
    )
    assert login.status_code == 403

    reset_request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "cross-site@example.com"},
    )
    assert reset_request.status_code == 403

    reset_confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "fake-token", "password": "StrongPass!2026"},
    )
    assert reset_confirm.status_code == 403


def test_auth_endpoints_reject_cross_origin_metadata(client):
    evil_headers = {"Origin": "http://evil.example"}

    register = client.post(
        "/api/auth/register",
        headers=evil_headers,
        json={
          "email": "evil-origin@example.com",
          "password": "StrongPass!2026",
          "full_name": "Evil Origin",
        },
    )
    assert register.status_code == 403

    login = client.post(
        "/api/auth/login",
        headers=evil_headers,
        json={"email": "evil-origin@example.com", "password": "StrongPass!2026"},
    )
    assert login.status_code == 403


def test_failed_login_audit_uses_email_digest_not_plain_email(client, db_session):
    register = client.post(
        "/api/auth/register",
        headers=SAME_ORIGIN_HEADERS,
        json={
            "email": "audit-digest@example.com",
            "password": "StrongPass!2026",
            "full_name": "Digest User",
        },
    )
    assert register.status_code == 200
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

    failed = client.post(
        "/api/auth/login",
        headers=SAME_ORIGIN_HEADERS,
        json={"email": "audit-digest@example.com", "password": "WrongPass!2026"},
    )
    assert failed.status_code == 401

    event = db_session.scalar(
        select(AuditLogEvent).where(AuditLogEvent.action == "auth.login.failed").order_by(AuditLogEvent.created_at.desc())
    )
    assert event is not None
    metadata = event.metadata_json or {}
    assert "email" not in metadata
    assert isinstance(metadata.get("email_hmac"), str) and metadata["email_hmac"]
