from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "test-platform.db"
    storage_dir = (tmp_path / "storage").resolve()
    quality_dir = storage_dir / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    (quality_dir / "engineering-gate.json").write_text(
        json.dumps(
            {
                "passed": True,
                "checks": [
                    {"key": "repo_hygiene_clean", "label": "Repository hygiene is clean", "passed": True, "detail": "clean"},
                    {
                        "key": "production_import_scan_clean",
                        "label": "Production paths avoid runtime model dependencies",
                        "passed": True,
                        "detail": "clean",
                    },
                    {"key": "backend_tests_green", "label": "Backend pytest suite passes", "passed": True, "detail": "ok"},
                    {"key": "frontend_build_green", "label": "SPA build passes", "passed": True, "detail": "ok"},
                    {
                        "key": "runtime_narrative_clean",
                        "label": "Runtime provider narrative is removed from product docs and UI",
                        "passed": True,
                        "detail": "clean",
                    },
                ],
                "checked_at": "2026-01-01T00:00:00+00:00",
                "source": "snapshot",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET", "test-secret-with-sufficient-length-1234567890")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("RESEARCH_AGENT_REPORTS_DIR", str((tmp_path / "reports").resolve()))
    monkeypatch.setenv("SMTP_HOST", "smtp.test.local")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "30")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://testserver")
    return db_path


@pytest.fixture()
def app(app_env: Path):
    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory
    from research_agent.webapp import create_app

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
    application = create_app()
    yield application
    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db_session():
    from research_agent.db import session_scope

    with session_scope() as session:
        yield session


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        headers={"Origin": "http://testserver"},
        json={
            "email": "tester@example.com",
            "password": "StrongPass!2026",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 200, response.text
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token
    workspace = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Primary Workspace", "description": "Test workspace"},
    )
    assert workspace.status_code == 200, workspace.text
    return {
        "csrf": csrf_token,
        "workspace_id": workspace.json()["workspace"]["id"],
    }
