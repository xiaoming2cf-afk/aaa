from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from research_agent import asgi
from research_agent.asgi import LazyApplication

STATIC_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data: blob:; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


def assert_static_security_headers(response) -> None:
    for header, expected in STATIC_SECURITY_HEADERS.items():
        assert response.headers[header] == expected


def test_source_spa_fallback_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", raising=False)
    assert asgi._allow_source_spa_fallback() is False

    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
    assert asgi._allow_source_spa_fallback() is False

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", raising=False)
    assert asgi._allow_source_spa_fallback() is False

    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
    assert asgi._allow_source_spa_fallback() is True

    monkeypatch.setenv("APP_ENV", "production")
    assert asgi._allow_source_spa_fallback() is False


def test_lazy_asgi_short_circuits_render_probe_paths_without_loading_full_app(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")

    def fail_factory():
        raise AssertionError("full application should not load for Render probe paths")

    with TestClient(LazyApplication(fail_factory)) as client:
        root_head = client.head("/")
        assert root_head.status_code == 200
        assert not root_head.content
        assert_static_security_headers(root_head)

        root_get = client.get("/")
        assert root_get.status_code == 200
        assert "Economic Research Platform" in root_get.text
        assert_static_security_headers(root_get)

        asset_get = client.get("/assets/styles.css")
        assert asset_get.status_code == 200
        assert asset_get.headers["content-type"].startswith("text/css")
        assert_static_security_headers(asset_get)

        bootstrap_get = client.get("/api/bootstrap")
        assert bootstrap_get.status_code == 200
        assert bootstrap_get.json()["app_name"] == "Economic Research Platform"
        assert_static_security_headers(bootstrap_get)

        provider_center = client.get("/provider-center")
        assert provider_center.status_code == 200
        assert "not part of the current product scope" in provider_center.text.lower()
        assert_static_security_headers(provider_center)

        spa_get = client.get("/app")
        assert spa_get.status_code == 200
        assert "<!doctype html>" in spa_get.text.lower()
        assert_static_security_headers(spa_get)

        health_get = client.get("/api/health")
        assert health_get.status_code == 200
        assert health_get.json() == {"status": "ok"}
        assert_static_security_headers(health_get)

        health_head = client.head("/api/health")
        assert health_head.status_code == 200
        assert not health_head.content
        assert_static_security_headers(health_head)


def test_production_spa_fallback_does_not_serve_source_index(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", tmp_path / "dist")
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", tmp_path / "frontend-spa")

    def fail_factory():
        raise AssertionError("full application should not load for SPA fallback failure")

    with TestClient(LazyApplication(fail_factory)) as client:
        response = client.get("/app")

    assert response.status_code == 503
    assert "/src/main.tsx" not in response.text
    assert_static_security_headers(response)


def test_lazy_asgi_loads_full_app_once_for_non_probe_paths():
    load_count = 0

    def app_factory():
        nonlocal load_count
        load_count += 1
        app = FastAPI()

        @app.get("/ready")
        def ready() -> dict[str, str]:
            return {"status": "ready"}

        return app

    with TestClient(LazyApplication(app_factory)) as client:
        first = client.get("/ready")
        assert first.status_code == 200
        assert first.json() == {"status": "ready"}

        second = client.get("/ready")
        assert second.status_code == 200
        assert load_count == 1


def test_auth_me_returns_401_without_session(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET", "test-secret-with-sufficient-length-1234567890")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("RESEARCH_AGENT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'asgi-auth.db').as_posix()}")

    from research_agent.webapp import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/auth/me")

    assert response.status_code == 401
