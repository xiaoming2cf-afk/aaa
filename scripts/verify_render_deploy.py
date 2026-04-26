from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

COMMIT_ENV_VARS = (
    "RESEARCH_AGENT_ENGINEERING_GATE_COMMIT",
    "GITHUB_SHA",
    "RENDER_GIT_COMMIT",
    "COMMIT_SHA",
    "SOURCE_VERSION",
)
RENDER_API_URL = "https://api.render.com/v1"


def _clean_commit(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "", str(value or "").strip())


def _current_commit(explicit: str = "") -> str:
    if explicit.strip():
        return _clean_commit(explicit)
    for name in COMMIT_ENV_VARS:
        value = _clean_commit(os.getenv(name, ""))
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except Exception:
        return ""
    return _clean_commit(result.stdout) if result.returncode == 0 else ""


def _blocking_report(reason: str, *, commit_sha: str = "", detail: Any | None = None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "passed": False,
        "blocked": True,
        "commit_sha": commit_sha,
        "reason": reason,
        "detail": detail or {},
        "required": {
            "deploy_hook": ["RENDER_DEPLOY_HOOK"],
            "render_api": ["RENDER_API_KEY", "RENDER_SERVICE_ID"],
        },
    }


def _append_ref(url: str, commit_sha: str) -> str:
    if not commit_sha:
        return url
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("ref", commit_sha)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _trigger_deploy_hook(deploy_hook: str, *, commit_sha: str) -> dict[str, Any]:
    url = _append_ref(deploy_hook, commit_sha)
    try:
        response = requests.post(url, timeout=30)
    except Exception as exc:
        return _blocking_report("Render deploy hook request failed.", commit_sha=commit_sha, detail=str(exc))
    if response.status_code < 200 or response.status_code >= 300:
        return _blocking_report(
            "Render deploy hook did not start a deploy.",
            commit_sha=commit_sha,
            detail={"status_code": response.status_code, "body": response.text[:500]},
        )
    return {
        "status": "triggered",
        "passed": True,
        "blocked": False,
        "method": "deploy_hook",
        "commit_sha": commit_sha,
        "render_status_code": response.status_code,
    }


def _trigger_render_api(api_key: str, service_id: str, *, commit_sha: str, clear_cache: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"clearCache": "clear" if clear_cache else "do_not_clear"}
    if commit_sha:
        body["commitId"] = commit_sha
    try:
        response = requests.post(
            f"{RENDER_API_URL}/services/{service_id}/deploys",
            timeout=30,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=body,
        )
    except Exception as exc:
        return _blocking_report("Render API deploy request failed.", commit_sha=commit_sha, detail=str(exc))
    if response.status_code < 200 or response.status_code >= 300:
        return _blocking_report(
            "Render API did not start a deploy.",
            commit_sha=commit_sha,
            detail={"status_code": response.status_code, "body": response.text[:500]},
        )
    try:
        payload = response.json()
    except Exception:
        payload = {"body": response.text[:500]}
    return {
        "status": "triggered",
        "passed": True,
        "blocked": False,
        "method": "render_api",
        "commit_sha": commit_sha,
        "render_status_code": response.status_code,
        "render_response": payload,
    }


def trigger_render_deploy(*, commit_sha: str, clear_cache: bool = False) -> dict[str, Any]:
    deploy_hook = os.getenv("RENDER_DEPLOY_HOOK", "").strip()
    api_key = os.getenv("RENDER_API_KEY", "").strip()
    service_id = os.getenv("RENDER_SERVICE_ID", "").strip()

    if deploy_hook:
        return _trigger_deploy_hook(deploy_hook, commit_sha=commit_sha)
    if api_key and service_id:
        return _trigger_render_api(api_key, service_id, commit_sha=commit_sha, clear_cache=clear_cache)
    return _blocking_report(
        "No Render deploy trigger is configured. Set RENDER_DEPLOY_HOOK or RENDER_API_KEY plus RENDER_SERVICE_ID.",
        commit_sha=commit_sha,
    )


def _run_smoke(base_url: str, *, deep: bool, register: bool, auth_email: str, auth_password: str) -> dict[str, Any]:
    from research_agent.cli import _run_deploy_smoke

    return _run_deploy_smoke(
        base_url=base_url,
        deep=deep or register,
        register=register,
        auth_email=auth_email,
        auth_password=auth_password,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger and optionally smoke-test a Render deploy.")
    parser.add_argument("--commit", default="", help="Commit SHA to deploy. Defaults to CI or git commit.")
    parser.add_argument("--base-url", default="", help="Optional deployed base URL for smoke-deploy after triggering.")
    parser.add_argument("--clear-cache", action="store_true", help="Request a clear-cache deploy when using the Render API.")
    parser.add_argument("--deep", action="store_true", help="Run authenticated deep smoke checks after triggering.")
    parser.add_argument("--register", action="store_true", help="Register a throwaway account for deep smoke checks.")
    parser.add_argument("--auth-email", default="", help="Email for deep smoke login.")
    parser.add_argument("--auth-password", default="", help="Password for deep smoke login.")
    args = parser.parse_args()

    commit_sha = _current_commit(args.commit)
    if not commit_sha:
        report = _blocking_report("Unable to resolve a commit SHA for Render deploy verification.")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    trigger_report = trigger_render_deploy(commit_sha=commit_sha, clear_cache=args.clear_cache)
    report: dict[str, Any] = {"deploy": trigger_report}
    passed = bool(trigger_report.get("passed"))

    if passed and args.base_url.strip():
        try:
            smoke_report = _run_smoke(
                args.base_url,
                deep=args.deep,
                register=args.register,
                auth_email=args.auth_email,
                auth_password=args.auth_password,
            )
        except Exception as exc:
            smoke_report = _blocking_report("Deploy smoke check failed to execute.", commit_sha=commit_sha, detail=str(exc))
        report["smoke"] = smoke_report
        passed = passed and bool(smoke_report.get("passed"))

    report["status"] = "passed" if passed else "blocked"
    report["passed"] = passed
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
