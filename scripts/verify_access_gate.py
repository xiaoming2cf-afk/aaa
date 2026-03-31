from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from verify_data_lab import auth_headers, configure_test_environment  # noqa: E402
from verify_public_monitor import insert_public_briefing  # noqa: E402


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_verification(output_dir: Path | None = None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-access-gate-verify-"))
    configure_test_environment(temp_root)

    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)

        remote_headers = {"host": "economic-research-web.onrender.com"}
        local_headers = {"host": "127.0.0.1"}
        pages = ["/", "/data-lab", "/optimization-lab", "/public-monitor"]
        page_checks: dict[str, Any] = {}
        for route in pages:
            response = client.get(route, headers=remote_headers)
            response.raise_for_status()
            page_checks[route] = {
                "status_code": response.status_code,
                "has_platform_navigation": "Platform Navigation" in response.text,
                "has_access_gate": "data-access-gate" in response.text,
            }
            if output_dir:
                slug = route.strip("/").replace("/", "_") or "home"
                _write_text(output_dir / "pages" / f"{slug}.html", response.text)

        gated_api_routes = [
            "/api/data-lab/catalog",
            "/api/optimization/catalog",
            "/api/public/briefings/latest",
            "/api/openalex/search?q=inflation&max_results=1",
        ]
        remote_api_status: dict[str, int] = {}
        for route in gated_api_routes:
            response = client.get(route, headers=remote_headers)
            remote_api_status[route] = response.status_code
            if response.status_code != 401:
                raise AssertionError(f"Expected remote unauthenticated access to fail for {route}, got {response.status_code}")

        local_api_status: dict[str, int] = {}
        for route in ["/api/data-lab/catalog", "/api/optimization/catalog"]:
            response = client.get(route, headers=local_headers)
            response.raise_for_status()
            local_api_status[route] = response.status_code

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Gate Reviewer", "email": "gate@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        insert_public_briefing()

        authed_remote_status: dict[str, int] = {}
        for route in gated_api_routes:
            response = client.get(route, headers={**remote_headers, **auth_headers(token)})
            authed_remote_status[route] = response.status_code
            if route.endswith("/latest"):
                # latest may still build or return null content, but should become accessible
                if response.status_code != 200:
                    raise AssertionError(f"Authenticated remote access should unlock {route}, got {response.status_code}")
            elif response.status_code != 200:
                raise AssertionError(f"Authenticated remote access should unlock {route}, got {response.status_code}")

        report = {
            "status": "passed",
            "page_checks": page_checks,
            "remote_api_status": remote_api_status,
            "local_api_status": local_api_status,
            "authenticated_remote_api_status": authed_remote_status,
        }
        if output_dir:
            _write_json(output_dir / "verification_report.json", report)
        return report
    finally:
        client.close()


def main() -> None:
    report = run_verification()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
