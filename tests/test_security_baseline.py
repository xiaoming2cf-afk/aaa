from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import requests
from fastapi.testclient import TestClient

from research_agent.config import Settings
from research_agent.entities import PublicEconomicBriefing
from research_agent.notifications import send_password_reset_email
from research_agent.request_meta import request_ip
from research_agent.platform_research import serialize_public_briefing
from research_agent.platform_core import validate_email
from research_agent.webapp import ModelRunRequest


def test_health_and_bootstrap_are_minimized(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert set(payload.keys()) == {"app_name", "public_digest_enabled"}

    providers = client.get("/api/providers")
    assert providers.status_code == 401


def test_root_sets_security_headers_without_unsafe_inline(client):
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_docs_are_available_in_test_with_docs_specific_csp(client):
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    docs_csp = docs.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in docs_csp
    assert "unsafe-inline" in docs_csp

    redoc = client.get("/redoc")
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()
    redoc_csp = redoc.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in redoc_csp
    assert "unsafe-inline" in redoc_csp


def test_internal_job_endpoint_is_excluded_from_openapi_schema(client):
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/internal/run-due-jobs" not in paths


def test_public_briefing_serializer_omits_internal_fields():
    briefing = PublicEconomicBriefing(
        slug="macro-open",
        title="Macro Open",
        briefing_date="2026-04-15",
        timezone_name="UTC",
        summary_markdown="Summary",
        query_text="internal query",
        template_version="v1",
        headline_count=3,
        items_json=[{"title": "Headline"}],
        raw_json={"internal": True},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = serialize_public_briefing(briefing, public_base_url="http://testserver")
    assert "id" not in payload
    assert "query_text" not in payload
    assert "template_version" not in payload
    assert "created_at" not in payload
    assert payload["share_url"].startswith("http://testserver")


def test_docs_and_openapi_are_disabled_in_production(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "prod-secret-with-sufficient-length-1234567890")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'prod-platform.db').as_posix()}")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("STORAGE_DIR", str((tmp_path / "storage").resolve()))
    monkeypatch.setenv("RESEARCH_AGENT_REPORTS_DIR", str((tmp_path / "reports").resolve()))

    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory
    from research_agent.webapp import create_app

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


def test_password_reset_email_uses_ssl_transport(monkeypatch):
    calls: list[tuple[str, str, int, int]] = []

    class DummySMTPSSL:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls.append(("ssl-init", host, port, timeout))

        def __enter__(self):
            calls.append(("ssl-enter", "", 0, 0))
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            calls.append(("ssl-exit", "", 0, 0))

        def login(self, username: str, password: str) -> None:
            calls.append(("login", username, 0, 0))

        def send_message(self, message) -> None:
            calls.append(("send", str(message["To"]), 0, 0))

    def blocked_plain(*args, **kwargs):
        raise AssertionError("SMTP() should not be used for ssl mode")

    monkeypatch.setattr("research_agent.notifications.smtplib.SMTP_SSL", DummySMTPSSL)
    monkeypatch.setattr("research_agent.notifications.smtplib.SMTP", blocked_plain)

    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="noreply@example.com",
        smtp_security="ssl",
    )

    send_password_reset_email(
        settings,
        recipient="user@example.com",
        reset_url="https://example.com/reset?token=abc",
        ttl_minutes=15,
    )

    assert ("ssl-init", "smtp.example.com", 465, 20) in calls
    assert ("login", "mailer", 0, 0) in calls
    assert ("send", "user@example.com", 0, 0) in calls


def test_password_reset_email_uses_starttls_only_when_configured(monkeypatch):
    calls: list[tuple[str, str, int, int]] = []

    class DummySMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls.append(("plain-init", host, port, timeout))

        def __enter__(self):
            calls.append(("plain-enter", "", 0, 0))
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            calls.append(("plain-exit", "", 0, 0))

        def starttls(self) -> None:
            calls.append(("starttls", "", 0, 0))

        def login(self, username: str, password: str) -> None:
            calls.append(("login", username, 0, 0))

        def send_message(self, message) -> None:
            calls.append(("send", str(message["To"]), 0, 0))

    def blocked_ssl(*args, **kwargs):
        raise AssertionError("SMTP_SSL() should not be used for starttls mode")

    monkeypatch.setattr("research_agent.notifications.smtplib.SMTP", DummySMTP)
    monkeypatch.setattr("research_agent.notifications.smtplib.SMTP_SSL", blocked_ssl)

    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="noreply@example.com",
        smtp_security="starttls",
    )

    send_password_reset_email(
        settings,
        recipient="user@example.com",
        reset_url="https://example.com/reset?token=abc",
        ttl_minutes=15,
    )

    assert ("plain-init", "smtp.example.com", 587, 20) in calls
    assert ("starttls", "", 0, 0) in calls
    assert ("login", "mailer", 0, 0) in calls
    assert ("send", "user@example.com", 0, 0) in calls


def test_email_validation_rejects_common_invalid_formats():
    invalid_values = [
        "",
        " plain@example.com",
        "plain@example.com ",
        "plain example@example.com",
        "@example.com",
        "user@",
        "user@example",
        "user@example.",
        "user..dots@example.com",
    ]

    for value in invalid_values:
        try:
            validate_email(value)
        except ValueError:
            continue
        raise AssertionError(f"{value!r} should be rejected")

    assert validate_email("valid.user+tag@example-domain.com") == "valid.user+tag@example-domain.com"


def test_frontend_escapes_single_quotes_and_uses_replace_redirect():
    app_js = Path("D:/智能体/src/research_agent/web/app.js").read_text(encoding="utf-8")
    assert ".replaceAll(\"'\", \"&#39;\")" in app_js
    assert 'window.location.replace("/workspace")' in app_js
    assert 'window.location.assign("/workspace")' not in app_js
    assert 'dom.sessionSignoutButton?.addEventListener("click", wrap(handleSignOut));' in app_js
    assert 'window.location.hash.replace(/^#/, "")' in app_js


def test_workspace_form_uses_autofill_resistant_attributes():
    workspace_html = Path("D:/智能体/src/research_agent/web/workspace.html").read_text(encoding="utf-8")
    assert 'id="workspace-form"' in workspace_html
    assert 'autocomplete="off"' in workspace_html
    assert 'data-lpignore="true"' in workspace_html
    assert 'data-1p-ignore="true"' in workspace_html


def test_deployment_samples_match_security_baseline():
    env_example = Path("D:/智能体/.env.example").read_text(encoding="utf-8")
    render_yaml = Path("D:/智能体/render.yaml").read_text(encoding="utf-8")
    readme = Path("D:/智能体/README.md").read_text(encoding="utf-8")

    assert "APP_SECRET=" in env_example
    assert "APP_SECRET=development-secret-change-me" not in env_example
    assert "SMTP_SECURITY=ssl" in env_example
    assert "PASSWORD_RESET_TTL_MINUTES=30" in env_example
    assert "SESSION_TTL_HOURS=72" in env_example
    assert "TRUSTED_PROXY_IPS=" in env_example
    assert "value: 72" in render_yaml
    assert "SMTP_SECURITY" in render_yaml
    assert "PASSWORD_RESET_TTL_MINUTES" in render_yaml
    assert "SESSION_TTL_HOURS=72" in readme


def test_request_ip_ignores_xff_without_trusted_proxy():
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.8"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    settings = Settings(app_env="test", app_secret="test-secret-with-sufficient-length-1234567890")
    assert request_ip(request, settings) == "127.0.0.1"


def test_request_ip_uses_xff_when_direct_peer_is_trusted():
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.8, 127.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        trusted_proxy_ips="127.0.0.1",
    )
    assert request_ip(request, settings) == "203.0.113.8"


def test_model_run_request_ignores_unknown_fields_and_rejects_oversized_variant_spec():
    payload = ModelRunRequest(
        asset_id="asset-1",
        model_family="econometrics_baseline",
        model_type="ols",
        dependent="y",
        independents=["x1"],
        unexpected_field="ignored",
    )
    assert "unexpected_field" not in payload.model_dump()

    try:
        ModelRunRequest(
            asset_id="asset-2",
            variant_spec={f"key_{index}": "x" * 400 for index in range(80)},
        )
    except ValueError:
        return
    raise AssertionError("Oversized variant_spec should be rejected")


def test_init_database_upgrades_legacy_user_schema(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "legacy-platform.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                full_name TEXT,
                password_hash TEXT,
                is_active INTEGER,
                created_at TEXT
            )
            """
        )
        conn.commit()

    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET", "test-secret-with-sufficient-length-1234567890")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("STORAGE_DIR", str((tmp_path / "storage").resolve()))
    monkeypatch.setenv("RESEARCH_AGENT_REPORTS_DIR", str((tmp_path / "reports").resolve()))

    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory, init_database

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

    init_database()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}

    assert "locked_until" in columns


def test_literature_import_blocks_private_network_pdf_sources(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    requested_urls: list[str] = []

    def blocked_get(self, url, *args, **kwargs):
        requested_urls.append(url)
        raise AssertionError("Unsafe literature URLs should be rejected before any outbound request.")

    monkeypatch.setattr("research_agent.platform_research.requests.Session.get", blocked_get)

    imported = client.post(
        f"/api/workspaces/{workspace_id}/literature/import",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "works": [
                {
                    "id": "https://openalex.org/W1234567890",
                    "display_name": "Unsafe OA Link Example",
                    "publication_year": 2026,
                    "authorships": [{"author": {"display_name": "Test Author"}}],
                    "primary_location": {
                        "landing_page_url": "http://127.0.0.1:9000/private-paper",
                        "pdf_url": "http://127.0.0.1:9000/private-paper.pdf",
                        "source": {"display_name": "Unsafe Localhost Source"},
                    },
                }
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    item = imported.json()["items"][0]
    assert item["can_import_pdf"] is False
    assert item["pdf_import_status"] == "blocked"
    assert item["pdf_url"] == ""
    assert item["landing_page_url"] == ""

    response = client.post(
        f"/api/workspaces/{workspace_id}/literature/{item['id']}/import-pdf",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 400
    assert "unsafe" in response.json()["detail"].lower() or "network location" in response.json()["detail"].lower()
    assert requested_urls == []


def test_public_feed_fetch_blocks_private_network_redirect(monkeypatch):
    requested_urls: list[str] = []

    class DummyResponse:
        def __init__(self, *, url: str, status_code: int, headers: dict[str, str] | None = None, body: bytes = b""):
            self.url = url
            self.status_code = status_code
            self.headers = headers or {}
            self._body = body
            self.encoding = "utf-8"
            self.apparent_encoding = "utf-8"

        def iter_content(self, chunk_size: int = 1024 * 1024):
            if self._body:
                yield self._body

        @property
        def content(self) -> bytes:
            return self._body

        @property
        def text(self) -> str:
            return self._body.decode("utf-8", errors="ignore")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error")

        def close(self) -> None:
            return None

    def fake_get(self, url, *args, **kwargs):
        requested_urls.append(url)
        if len(requested_urls) == 1:
            return DummyResponse(
                url=url,
                status_code=302,
                headers={"Location": "http://127.0.0.1:9000/private-feed.xml"},
            )
        raise AssertionError("Unsafe redirect target should be rejected before any follow-up request.")

    monkeypatch.setattr("research_agent.platform_research.requests.Session.get", fake_get)

    from research_agent.config import get_settings
    from research_agent.platform_research import fetch_rss_hotspots

    payload = fetch_rss_hotspots(
        get_settings(),
        now=datetime(2026, 4, 17, tzinfo=timezone.utc),
        feeds=[
            {
                "name": "Example Feed",
                "url": "https://example.com/feed.xml",
                "domain": "example.com",
                "source_country": "US",
                "language": "English",
                "source_type": "media",
                "region_focus": "Global",
                "credibility": "test",
                "note": "redirect safety test",
            }
        ],
    )
    assert payload["feeds"][0]["status"] == "error"
    assert "private network" in payload["feeds"][0]["message"].lower()
    assert requested_urls == ["https://example.com/feed.xml"]
