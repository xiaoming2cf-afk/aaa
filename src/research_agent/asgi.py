from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import mimetypes
import os
from pathlib import Path
import threading
from typing import Any
from urllib.parse import unquote


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
AppFactory = Callable[[], Any]
PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
SPA_ROOT_DIR = PACKAGE_DIR.parents[1] / "frontend-spa"
SPA_DIST_DIR = SPA_ROOT_DIR / "dist"
_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_SOURCE_SPA_FALLBACK_ENVS = {"development", "dev", "test", "testing"}
_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"content-security-policy", _DEFAULT_CSP.encode("ascii")),
)


class LazyApplication:
    """Keep Render port detection fast while loading the full app on demand."""

    def __init__(self, app_factory: AppFactory | None = None) -> None:
        self._app_factory = app_factory
        self._loaded_app: Any | None = None
        self._lock = threading.Lock()

    def _load_app(self) -> Any:
        if self._loaded_app is None:
            with self._lock:
                if self._loaded_app is None:
                    factory = self._app_factory
                    if factory is None:
                        from .webapp import create_app

                        factory = create_app
                    self._loaded_app = factory()
        return self._loaded_app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        static_response = self._static_response(scope)
        if static_response is not None:
            status, headers, body = static_response
            await self._send_response(send, status, headers, body)
            return
        if self._can_probe_short_circuit(scope):
            await self._send_probe_response(scope, send)
            return
        await self._load_app()(scope, receive, send)

    async def _handle_lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message_type == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    @staticmethod
    def _can_probe_short_circuit(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http":
            return False
        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        if path == "/api/health" and method in {"GET", "HEAD"}:
            return True
        return path == "/" and method == "HEAD"

    @staticmethod
    async def _send_probe_response(scope: dict[str, Any], send: Send) -> None:
        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        body = b'{"status":"ok"}' if path == "/api/health" and method == "GET" else b""
        headers = _headers("application/json" if path == "/api/health" else "text/plain; charset=utf-8", len(body))
        await LazyApplication._send_response(send, 200, headers, body)

    @staticmethod
    async def _send_response(send: Send, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _static_response(scope: dict[str, Any]) -> tuple[int, list[tuple[bytes, bytes]], bytes] | None:
        if scope.get("type") != "http":
            return None
        method = str(scope.get("method", "")).upper()
        if method not in {"GET", "HEAD"}:
            return None
        path = str(scope.get("path", ""))
        if path == "/api/bootstrap":
            body = b"" if method == "HEAD" else json.dumps(
                {"app_name": "Economic Research Platform", "public_digest_enabled": True},
                separators=(",", ":"),
            ).encode("utf-8")
            return 200, _headers("application/json", len(body)), body
        if path == "/":
            return _file_response(WEB_DIR / "index.html", method)
        if path == "/favicon.ico":
            return _file_response(WEB_DIR / "favicon.svg", method, media_type="image/svg+xml")
        if path == "/provider-center":
            return _provider_center_response(method)
        if path.startswith("/assets/"):
            return _safe_file_response(WEB_DIR, path.removeprefix("/assets/"), method)
        if path == "/app" or path.startswith("/app/"):
            return _spa_response(path, method)
        return None


def _headers(media_type: str, content_length: int) -> list[tuple[bytes, bytes]]:
    return [
        (b"content-type", media_type.encode("ascii", errors="ignore")),
        (b"content-length", str(content_length).encode("ascii")),
        *_SECURITY_HEADERS,
    ]


def _file_response(path: Path, method: str, *, media_type: str | None = None) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    if not path.exists() or not path.is_file():
        body = b"Not Found" if method != "HEAD" else b""
        return 404, _headers("text/plain; charset=utf-8", len(body)), body
    resolved_media_type = media_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    body = b"" if method == "HEAD" else path.read_bytes()
    return 200, _headers(resolved_media_type, len(body)), body


def _safe_file_response(root: Path, relative_path: str, method: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    root_resolved = root.resolve()
    decoded_path = unquote(relative_path)
    if _contains_unsafe_path_segment(decoded_path):
        body = b"Not Found" if method != "HEAD" else b""
        return 404, _headers("text/plain; charset=utf-8", len(body)), body
    candidate = (root / decoded_path).resolve()
    if candidate != root_resolved and root_resolved in candidate.parents:
        return _file_response(candidate, method)
    body = b"Not Found" if method != "HEAD" else b""
    return 404, _headers("text/plain; charset=utf-8", len(body)), body


def _contains_unsafe_path_segment(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("/"):
        return True
    return any(part == ".." for part in normalized.split("/"))


def _spa_response(path: str, method: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    normalized = path.removeprefix("/app").strip("/")
    if normalized:
        asset_response = _safe_file_response(SPA_DIST_DIR, normalized, method)
        if asset_response[0] == 200:
            return asset_response
        if normalized.startswith("assets/"):
            return asset_response
    index_path = SPA_DIST_DIR / "index.html"
    if not index_path.exists() and _allow_source_spa_fallback():
        index_path = SPA_ROOT_DIR / "index.html"
    if not index_path.exists():
        body = b"" if method == "HEAD" else b"SPA build is unavailable. Run the frontend build before serving /app."
        return 503, _headers("text/plain; charset=utf-8", len(body)), body
    return _file_response(index_path, method, media_type="text/html; charset=utf-8")


def _allow_source_spa_fallback() -> bool:
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env not in _SOURCE_SPA_FALLBACK_ENVS:
        return False
    return os.getenv("RESEARCH_AGENT_ALLOW_SOURCE_SPA_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


def _provider_center_response(method: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = b"" if method == "HEAD" else """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Provider Center Unavailable</title>
  </head>
  <body>
    <main>
      <section>
        <p>Disabled Surface</p>
        <h1>Provider Center is not part of the current product scope</h1>
        <p>This build keeps research runs, review gates, publishing, knowledge capture, and team library workflows, but it does not expose runtime model provider management.</p>
        <p>Return to the <a href="/">home page</a> or the <a href="/app/quality">quality dashboard</a>.</p>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    return 200, _headers("text/html; charset=utf-8", len(body)), body


app = LazyApplication()
