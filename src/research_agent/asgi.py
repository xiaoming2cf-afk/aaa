from __future__ import annotations

from collections.abc import Awaitable, Callable
import threading
from typing import Any


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
AppFactory = Callable[[], Any]


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
        if self._can_short_circuit(scope):
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
    def _can_short_circuit(scope: dict[str, Any]) -> bool:
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
        headers = [
            (b"content-type", b"application/json" if path == "/api/health" else b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": body})


app = LazyApplication()
