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


def _assert_redirect_home(response, route: str) -> dict[str, Any]:
    if response.status_code not in {302, 303, 307, 308}:
        raise AssertionError(f"{route}: expected redirect to home, got {response.status_code}")
    location = response.headers.get("location", "")
    if location != "/":
        raise AssertionError(f"{route}: expected redirect target '/', got {location!r}")
    return {"status_code": response.status_code, "location": location}


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
        insert_public_briefing()

        home = client.get("/", headers=remote_headers)
        home.raise_for_status()
        if "Platform Navigation" not in home.text:
            raise AssertionError("Home page lost the platform navigation surface")
        if "Daily" not in home.text and "Public Daily Monitor" not in home.text:
            raise AssertionError("Home page no longer exposes the public daily-report surface")

        public_api_routes = [
            "/api/public/briefings/latest",
            "/api/public/briefings",
            "/api/public/summary?days=7",
        ]
        public_api_status: dict[str, int] = {}
        for route in public_api_routes:
            response = client.get(route, headers=remote_headers)
            public_api_status[route] = response.status_code
            if response.status_code != 200:
                raise AssertionError(f"{route}: expected public access, got {response.status_code}")

        private_pages = [
            "/data-lab",
            "/public-monitor",
            "/summaries/weekly",
            "/summaries/monthly",
            "/data-lab/models/econometrics_baseline/ols",
            "/data-lab/learn/models/econometrics_baseline/ols",
        ]
        page_redirects: dict[str, Any] = {}
        for route in private_pages:
            response = client.get(route, headers=remote_headers, follow_redirects=False)
            page_redirects[route] = _assert_redirect_home(response, route)

        legacy_opt_response = client.get("/optimization-lab", headers=remote_headers, follow_redirects=False)
        if legacy_opt_response.status_code not in {302, 303, 307, 308}:
            raise AssertionError(
                f"/optimization-lab: expected redirect into Data Lab anchor, got {legacy_opt_response.status_code}"
            )
        if legacy_opt_response.headers.get("location") != "/data-lab#optimization-module":
            raise AssertionError(
                f"/optimization-lab: unexpected location {legacy_opt_response.headers.get('location')!r}"
            )

        private_api_routes = [
            "/api/data-lab/catalog",
            "/api/optimization/catalog",
            "/api/openalex/search?q=inflation&max_results=1",
            "/api/auth/me",
        ]
        private_api_status: dict[str, int] = {}
        for route in private_api_routes:
            response = client.get(route, headers=remote_headers)
            private_api_status[route] = response.status_code
            if response.status_code != 401:
                raise AssertionError(f"{route}: expected 401 for anonymous remote access, got {response.status_code}")

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Gate Reviewer", "email": "gate@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]

        authenticated_pages: dict[str, int] = {}
        for route in private_pages:
            response = client.get(route, headers={**remote_headers, **auth_headers(token)})
            authenticated_pages[route] = response.status_code
            if response.status_code != 200:
                raise AssertionError(f"{route}: expected authenticated access, got {response.status_code}")

        authenticated_private_api_status: dict[str, int] = {}
        for route in private_api_routes:
            response = client.get(route, headers={**remote_headers, **auth_headers(token)})
            authenticated_private_api_status[route] = response.status_code
            if response.status_code != 200:
                raise AssertionError(f"{route}: expected authenticated API access, got {response.status_code}")

        me_response = client.get("/api/auth/me", headers={**remote_headers, **auth_headers(token)})
        me_response.raise_for_status()
        me_payload = me_response.json()
        if me_payload.get("user", {}).get("email") != "gate@example.com":
            raise AssertionError("Authenticated /api/auth/me returned the wrong user")

        report = {
            "status": "passed",
            "home_status": home.status_code,
            "public_api_status": public_api_status,
            "private_page_redirects": page_redirects,
            "legacy_optimization_redirect": {
                "status_code": legacy_opt_response.status_code,
                "location": legacy_opt_response.headers.get("location", ""),
            },
            "private_api_status": private_api_status,
            "authenticated_pages": authenticated_pages,
            "authenticated_private_api_status": authenticated_private_api_status,
        }
        if output_dir:
            _write_text(output_dir / "pages" / "home.html", home.text)
            _write_json(output_dir / "verification_report.json", report)
        return report
    finally:
        client.close()


def main() -> None:
    report = run_verification()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
