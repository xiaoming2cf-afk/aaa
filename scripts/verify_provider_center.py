from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from session_auth import auth_headers, same_origin_headers, session_token_from_cookies


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
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        configure_test_environment(Path(temp_dir))

        from research_agent.webapp import create_app

        with TestClient(create_app()) as client:
            register_response = client.post(
                "/api/auth/register",
                headers=same_origin_headers("http://testserver"),
                json={
                    "email": "provider-test@example.com",
                    "password": "ProviderPass123!",
                    "full_name": "Provider Test",
                },
            )
            register_response.raise_for_status()
            token = session_token_from_cookies(client)
            headers = auth_headers(token)

            provider_center_page = client.get("/provider-center", headers=headers)
            provider_center_page.raise_for_status()
            html = provider_center_page.text.lower()
            assert "provider center is not part of the current product scope" in html

            providers = client.get("/api/providers", headers=headers)
            providers.raise_for_status()
            payload = providers.json()
            assert payload["available"] is False

            blocked = client.post(
                "/api/integrations",
                headers=headers,
                json={
                    "label": "Blocked Runtime",
                    "category": "llm",
                    "kind": "ollama",
                    "api_key": "",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "qwen2.5:7b-instruct",
                    "is_default": True,
                    "config": {},
                },
            )
            assert blocked.status_code == 400
            print(
                {
                    "provider_center": "disabled",
                    "providers_api": payload,
                    "blocked_runtime_status": blocked.status_code,
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
