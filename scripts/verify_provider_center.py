from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-provider-center-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-provider-center-encryption"
    os.environ["CRON_SECRET"] = "verify-provider-center-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"


class StubProviderHandler(BaseHTTPRequestHandler):
    request_log: list[dict[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        model = payload.get("model", "")
        StubProviderHandler.request_log.append({"path": self.path, "model": model})
        body = {
            "id": "chatcmpl-provider-test",
            "object": "chat.completion",
            "created": 1777777777,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"stub ok for {model}",
                    },
                }
            ],
        }
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def start_stub_provider_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fake_fred_get(url: str, *, params: dict[str, str] | None = None, timeout: int = 20):  # noqa: ARG001
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return

    if "api.stlouisfed.org/fred/series/observations" not in url:
        raise AssertionError(f"Unexpected URL: {url}")
    if not params or params.get("series_id") != "FEDFUNDS":
        raise AssertionError(f"Unexpected FRED params: {params}")
    return FakeResponse()


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_root = Path(temp_dir)
        configure_test_environment(temp_root)

        from research_agent.webapp import create_app

        server, stub_root = start_stub_provider_server()
        try:
            with patch("research_agent.platform_core.requests.get", side_effect=fake_fred_get):
                with TestClient(create_app()) as client:
                    bootstrap = client.get("/api/bootstrap")
                    bootstrap.raise_for_status()
                    bootstrap_payload = bootstrap.json()
                    provider_catalog = bootstrap_payload["provider_catalog"]
                    llm_kinds = {item["kind"] for item in provider_catalog["llm"]}
                    assert {"openai", "deepseek", "gemini", "anthropic", "kimi", "openai_compatible"} <= llm_kinds
                    assert any(item["kind"] == "fred" for item in provider_catalog["data_source"])

                    home = client.get("/")
                    home.raise_for_status()
                    html = home.text
                    assert 'option value="deepseek"' in html
                    assert 'option value="kimi"' in html
                    assert 'id="integration-provider-hint"' in html

                    register_response = client.post(
                        "/api/auth/register",
                        json={
                            "email": "provider-test@example.com",
                            "password": "ProviderPass123",
                            "full_name": "Provider Test",
                        },
                    )
                    register_response.raise_for_status()
                    token = register_response.json()["session_token"]
                    headers = auth_headers(token)

                    llm_payloads = [
                    {
                        "label": "OpenAI Stub",
                        "category": "llm",
                        "kind": "openai",
                        "api_key": "sk-openai-test",
                        "base_url": f"{stub_root}/v1",
                        "model": "gpt-5-mini",
                        "is_default": False,
                    },
                    {
                        "label": "Compatible Stub",
                        "category": "llm",
                        "kind": "openai_compatible",
                        "api_key": "sk-compatible-test",
                        "base_url": f"{stub_root}/v1",
                        "model": "compatible-chat",
                        "is_default": False,
                    },
                    {
                        "label": "Gemini Stub",
                        "category": "llm",
                        "kind": "gemini",
                        "api_key": "sk-gemini-test",
                        "base_url": f"{stub_root}/v1beta/openai/",
                        "model": "gemini-2.5-flash",
                        "is_default": False,
                    },
                    {
                        "label": "Anthropic Stub",
                        "category": "llm",
                        "kind": "anthropic",
                        "api_key": "sk-anthropic-test",
                        "base_url": f"{stub_root}/v1/",
                        "model": "claude-sonnet-4-0",
                        "is_default": False,
                    },
                    {
                        "label": "DeepSeek Stub",
                        "category": "llm",
                        "kind": "deepseek",
                        "api_key": "sk-deepseek-test",
                        "base_url": f"{stub_root}",
                        "model": "deepseek-chat",
                        "is_default": False,
                    },
                    {
                        "label": "Kimi Stub",
                        "category": "llm",
                        "kind": "kimi",
                        "api_key": "sk-kimi-test",
                        "base_url": f"{stub_root}/v1",
                        "model": "kimi-k2.5",
                        "is_default": True,
                    },
                ]

                    verification_items: list[dict[str, object]] = []
                    for payload in llm_payloads:
                        save_response = client.post("/api/integrations", headers=headers, json=payload)
                        save_response.raise_for_status()
                        integration = save_response.json()["integration"]
                        test_response = client.post(f"/api/integrations/{integration['id']}/test", headers=headers)
                        test_response.raise_for_status()
                        tested = test_response.json()
                        assert tested["status"] == "ok"
                        verification_items.append(
                            {
                                "label": integration["label"],
                                "kind": integration["kind"],
                                "provider_name": integration["provider_name"],
                                "docs_url": integration["docs_url"],
                                "resolved_model": tested.get("resolved_model"),
                                "resolved_base_url": tested.get("resolved_base_url"),
                                "preview": tested.get("preview"),
                            }
                        )

                    fred_response = client.post(
                        "/api/integrations",
                        headers=headers,
                        json={
                            "label": "FRED Stub",
                            "category": "data_source",
                            "kind": "fred",
                            "api_key": "fred-api-key-test",
                            "base_url": "",
                            "model": "",
                            "is_default": True,
                        },
                    )
                    fred_response.raise_for_status()
                    fred_integration = fred_response.json()["integration"]
                    fred_test = client.post(f"/api/integrations/{fred_integration['id']}/test", headers=headers)
                    fred_test.raise_for_status()
                    verification_items.append(
                        {
                            "label": fred_integration["label"],
                            "kind": fred_integration["kind"],
                            "provider_name": fred_integration["provider_name"],
                            "docs_url": fred_integration["docs_url"],
                            "preview": fred_test.json().get("preview"),
                        }
                    )

                    list_response = client.get("/api/integrations", headers=headers)
                    list_response.raise_for_status()
                    saved_kinds = {item["kind"] for item in list_response.json()["items"]}
                    assert {"openai", "openai_compatible", "gemini", "anthropic", "deepseek", "kimi", "fred"} <= saved_kinds

                    report_dir = REPO_ROOT / "蒙特卡洛" / "provider_center"
                    report_dir.mkdir(parents=True, exist_ok=True)
                    report = {
                        "bootstrap_supported_llm_kinds": bootstrap_payload["supported_llm_kinds"],
                        "bootstrap_supported_data_kinds": bootstrap_payload["supported_data_kinds"],
                        "verified_integrations": verification_items,
                        "stub_requests": StubProviderHandler.request_log,
                    }
                    (report_dir / "verification_report.json").write_text(
                        json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(json.dumps(report, indent=2, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
