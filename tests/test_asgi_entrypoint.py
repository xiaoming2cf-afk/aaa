from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from research_agent import asgi
from research_agent.asgi import LazyApplication


def test_source_spa_fallback_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", raising=False)
    assert asgi._allow_source_spa_fallback() is False

    monkeypatch.setenv("APP_ENV", "development")
    assert asgi._allow_source_spa_fallback() is False

    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
    assert asgi._allow_source_spa_fallback() is True


def test_lazy_asgi_short_circuits_render_probe_paths_without_loading_full_app():
    def fail_factory():
        raise AssertionError("full application should not load for Render probe paths")

    with TestClient(LazyApplication(fail_factory)) as client:
        root_head = client.head("/")
        assert root_head.status_code == 200
        assert not root_head.content

        root_get = client.get("/")
        assert root_get.status_code == 200
        assert "Economic Research Platform" in root_get.text

        asset_get = client.get("/assets/styles.css")
        assert asset_get.status_code == 200
        assert asset_get.headers["content-type"].startswith("text/css")

        bootstrap_get = client.get("/api/bootstrap")
        assert bootstrap_get.status_code == 200
        assert bootstrap_get.json()["app_name"] == "Economic Research Platform"

        provider_center = client.get("/provider-center")
        assert provider_center.status_code == 200
        assert "not part of the current product scope" in provider_center.text.lower()

        spa_get = client.get("/app")
        assert spa_get.status_code == 200
        assert "<!doctype html>" in spa_get.text.lower()

        health_get = client.get("/api/health")
        assert health_get.status_code == 200
        assert health_get.json() == {"status": "ok"}

        health_head = client.head("/api/health")
        assert health_head.status_code == 200
        assert not health_head.content


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
