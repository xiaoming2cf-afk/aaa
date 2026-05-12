from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_agent import asgi


def _request(
    path: str,
    *,
    method: str = "GET",
    app: asgi.LazyApplication | None = None,
) -> tuple[int, dict[str, str], bytes]:
    messages: list[dict[str, Any]] = []
    application = app or asgi.LazyApplication(app_factory=lambda: _raise_loaded_app())

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(
        application(
            {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [],
                "query_string": b"",
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body_message = next(message for message in messages if message["type"] == "http.response.body")
    headers = {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in start["headers"]
    }
    return int(start["status"]), headers, body_message.get("body", b"")


def _raise_loaded_app() -> None:
    raise AssertionError("Static ASGI response should not load the FastAPI app.")


def _write_index(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _assert_static_security_headers(headers: dict[str, str]) -> None:
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    csp = headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "img-src 'self' data: blob:" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp


def test_static_short_circuit_routes_include_security_headers(monkeypatch, tmp_path):
    web_dir = tmp_path / "web"
    dist_dir = tmp_path / "frontend-spa" / "dist"
    _write_index(web_dir / "index.html", "<!doctype html><title>Home</title>")
    _write_index(dist_dir / "index.html", "<!doctype html><title>SPA</title>")
    monkeypatch.setattr(asgi, "WEB_DIR", web_dir)
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", dist_dir)
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", tmp_path / "frontend-spa")

    for path in ["/", "/api/bootstrap", "/provider-center", "/app", "/api/health"]:
        status, headers, body = _request(path)
        assert status == 200
        assert body is not None
        _assert_static_security_headers(headers)

    status, headers, body = _request("/api/health", method="HEAD")
    assert status == 200
    assert not body
    _assert_static_security_headers(headers)


def test_production_never_returns_source_spa_fallback(monkeypatch, tmp_path):
    source_root = tmp_path / "frontend-spa"
    dist_dir = source_root / "dist"
    _write_index(source_root / "index.html", '<script type="module" src="/src/main.tsx"></script>')
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", dist_dir)
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", source_root)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")

    status, headers, body = _request("/app")

    assert status == 503
    _assert_static_security_headers(headers)
    assert b"/src/main.tsx" not in body
    assert b"SPA build is unavailable" in body


def test_source_spa_fallback_requires_development_or_test_and_explicit_opt_in(monkeypatch, tmp_path):
    source_root = tmp_path / "frontend-spa"
    dist_dir = source_root / "dist"
    source_body = '<script type="module" src="/src/main.tsx"></script>'
    _write_index(source_root / "index.html", source_body)
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", dist_dir)
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", source_root)

    for env_name in ["development", "dev", "test", "testing"]:
        monkeypatch.setenv("APP_ENV", env_name)
        monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
        status, headers, body = _request("/app")
        assert status == 200
        _assert_static_security_headers(headers)
        assert b"/src/main.tsx" in body

    for env_name in ["production", "staging", "prod", "qa"]:
        monkeypatch.setenv("APP_ENV", env_name)
        monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")
        status, headers, body = _request("/app")
        assert status == 503
        _assert_static_security_headers(headers)
        assert b"/src/main.tsx" not in body

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", raising=False)
    status, headers, body = _request("/app")
    assert status == 503
    _assert_static_security_headers(headers)
    assert b"/src/main.tsx" not in body


def test_production_serves_dist_index_when_available_even_if_source_fallback_is_set(monkeypatch, tmp_path):
    source_root = tmp_path / "frontend-spa"
    dist_dir = source_root / "dist"
    _write_index(source_root / "index.html", '<script type="module" src="/src/main.tsx"></script>')
    _write_index(dist_dir / "index.html", "<!doctype html><title>Built SPA</title>")
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", dist_dir)
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", source_root)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "true")

    status, headers, body = _request("/app")

    assert status == 200
    _assert_static_security_headers(headers)
    assert b"Built SPA" in body
    assert b"/src/main.tsx" not in body


def test_missing_spa_asset_returns_404_without_spa_shell(monkeypatch, tmp_path):
    source_root = tmp_path / "frontend-spa"
    dist_dir = source_root / "dist"
    _write_index(dist_dir / "index.html", "<!doctype html><title>Built SPA</title>")
    monkeypatch.setattr(asgi, "SPA_DIST_DIR", dist_dir)
    monkeypatch.setattr(asgi, "SPA_ROOT_DIR", source_root)

    for path in ["/app/assets/missing.js", "/app/assets/missing.css"]:
        status, headers, body = _request(path)

        assert status == 404
        _assert_static_security_headers(headers)
        assert headers["content-type"].startswith("text/plain")
        assert b"Built SPA" not in body
        assert b"Not Found" in body


def test_missing_public_asset_returns_404(monkeypatch, tmp_path):
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(asgi, "WEB_DIR", web_dir)

    status, headers, body = _request("/assets/missing.css")

    assert status == 404
    _assert_static_security_headers(headers)
    assert headers["content-type"].startswith("text/plain")
    assert b"Not Found" in body
