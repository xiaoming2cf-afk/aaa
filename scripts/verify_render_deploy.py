from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import requests

try:
    from scripts.spa_dist_manifest import asset_references_from_text, validate_spa_dist_manifest_payload
except ModuleNotFoundError:  # pragma: no cover - supports `python scripts/<name>.py`
    from spa_dist_manifest import asset_references_from_text, validate_spa_dist_manifest_payload


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
ENGINEERING_GATE_SCHEMA = "engineering-gate.v1"


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
    present = {
        "RENDER_DEPLOY_HOOK": bool(os.getenv("RENDER_DEPLOY_HOOK", "").strip()),
        "RENDER_API_KEY": bool(os.getenv("RENDER_API_KEY", "").strip()),
        "RENDER_SERVICE_ID": bool(os.getenv("RENDER_SERVICE_ID", "").strip()),
    }
    missing_for_api = [name for name in ("RENDER_API_KEY", "RENDER_SERVICE_ID") if not present[name]]
    return {
        "status": "blocked",
        "passed": False,
        "blocked": True,
        "commit_sha": commit_sha,
        "reason": reason,
        "detail": detail or {},
        "credentials": {
            "present": present,
            "missing_for_deploy_hook": [] if present["RENDER_DEPLOY_HOOK"] else ["RENDER_DEPLOY_HOOK"],
            "missing_for_render_api": missing_for_api,
        },
        "required": {
            "deploy_hook": ["RENDER_DEPLOY_HOOK"],
            "render_api": ["RENDER_API_KEY", "RENDER_SERVICE_ID"],
        },
        "remediation": (
            "Configure either RENDER_DEPLOY_HOOK or both RENDER_API_KEY and RENDER_SERVICE_ID as CI secrets. "
            "The verifier blocks deploy promotion when no authenticated Render trigger is available."
        ),
    }


def _load_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, f"{path} is not readable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path} must contain a JSON object."
    return payload, None


def _manifest_path_candidates(*, commit_sha: str, engineering_gate: str, spa_manifest: str) -> list[Path]:
    explicit = [value for value in (spa_manifest, engineering_gate) if value.strip()]
    if explicit:
        return [Path(value).expanduser().resolve() for value in explicit]
    candidates: list[Path] = []
    for name in ("RESEARCH_AGENT_ENGINEERING_GATE_ARTIFACT", "ENGINEERING_GATE_ARTIFACT_PATH"):
        value = os.getenv(name, "").strip()
        if value:
            candidates.append(Path(value).expanduser().resolve())
    if commit_sha:
        candidates.extend(
            [
                REPO_ROOT / "output" / "engineering-gate" / f"engineering-gate.{commit_sha}.json",
                REPO_ROOT / "storage" / "quality" / "gates" / f"engineering-gate.{commit_sha}.json",
                REPO_ROOT / "storage" / "quality" / f"engineering-gate.{commit_sha}.json",
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _resolve_expected_spa_manifest(
    *,
    commit_sha: str,
    engineering_gate: str = "",
    spa_manifest: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    candidates = _manifest_path_candidates(commit_sha=commit_sha, engineering_gate=engineering_gate, spa_manifest=spa_manifest)
    for path in candidates:
        if not path.exists():
            failures.append({"path": str(path), "detail": "path does not exist"})
            continue
        payload, error = _load_json_file(path)
        if error or payload is None:
            failures.append({"path": str(path), "detail": error})
            continue
        if payload.get("artifact_schema") == ENGINEERING_GATE_SCHEMA or "spa_dist" in payload:
            artifact_commit = _clean_commit(str(payload.get("commit_sha") or ""))
            if artifact_commit != commit_sha:
                failures.append(
                    {
                        "path": str(path),
                        "detail": f"engineering gate artifact commit {artifact_commit or '<missing>'} does not match {commit_sha}",
                    }
                )
                continue
            if payload.get("passed") is not True:
                failures.append({"path": str(path), "detail": "engineering gate artifact is not green"})
                continue
            manifest = payload.get("spa_dist")
        else:
            manifest = payload
        manifest_failures = validate_spa_dist_manifest_payload(manifest, commit_sha=commit_sha)
        if manifest_failures:
            failures.append({"path": str(path), "detail": "SPA dist manifest is invalid", "failures": manifest_failures})
            continue
        return manifest, {
            "status": "passed",
            "passed": True,
            "source": str(path),
            "commit_sha": commit_sha,
            "entrypoints": list(manifest.get("entrypoints", [])),
            "asset_count": len(manifest.get("assets", [])),
        }
    return None, {
        "status": "blocked",
        "passed": False,
        "blocked": True,
        "commit_sha": commit_sha,
        "reason": "No valid commit-bound SPA dist manifest was available for deploy verification.",
        "searched": [str(path) for path in candidates],
        "failures": failures,
        "required": [
            "--engineering-gate output/engineering-gate/engineering-gate.<commit>.json",
            "--spa-manifest <spa-dist-manifest.json>",
            "RESEARCH_AGENT_ENGINEERING_GATE_ARTIFACT",
        ],
    }


def _remote_asset_path(base_path: str, asset_path: str) -> str:
    prefix = "/" + str(base_path or "/app/").strip("/")
    return f"{prefix}/{asset_path.lstrip('/')}"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _verify_deployed_spa_assets(
    *,
    base_url: str,
    manifest: dict[str, Any],
    session: requests.Session | None = None,
) -> dict[str, Any]:
    normalized_base_url = base_url.strip().rstrip("/")
    http = session or requests.Session()
    checks: list[dict[str, Any]] = []
    base_path = str(manifest.get("base_path") or "/app/")
    expected_assets = {
        str(entry.get("path")): str(entry.get("sha256"))
        for entry in manifest.get("assets", [])
        if isinstance(entry, dict) and entry.get("path") and entry.get("sha256")
    }
    expected_entrypoints = set(str(path) for path in manifest.get("entrypoints", []))

    for asset_path, expected_hash in sorted(expected_assets.items()):
        remote_path = _remote_asset_path(base_path, asset_path)
        try:
            response = http.get(f"{normalized_base_url}{remote_path}", timeout=30, allow_redirects=False)
            actual_hash = _sha256_bytes(response.content) if response.status_code == 200 else ""
            passed = response.status_code == 200 and actual_hash == expected_hash
            checks.append(
                {
                    "key": "spa_asset_hash_matches_manifest",
                    "path": remote_path,
                    "passed": passed,
                    "status_code": response.status_code,
                    "detail": "sha256 match" if passed else f"expected {expected_hash}, got {actual_hash or response.text[:120]}",
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "key": "spa_asset_hash_matches_manifest",
                    "path": remote_path,
                    "passed": False,
                    "status_code": 0,
                    "detail": str(exc),
                }
            )

    shell_path = "/" + base_path.strip("/")
    try:
        response = http.get(f"{normalized_base_url}{shell_path}", timeout=20, allow_redirects=False)
        location = response.headers.get("location", "")
        if response.status_code == 200:
            actual_entrypoints = asset_references_from_text(response.text)
            passed = "/src/main.tsx" not in response.text and actual_entrypoints == expected_entrypoints
            checks.append(
                {
                    "key": "spa_shell_entrypoints_match_manifest",
                    "path": shell_path,
                    "passed": passed,
                    "status_code": response.status_code,
                    "detail": "entrypoints match"
                    if passed
                    else "SPA shell entrypoints do not match the commit-bound manifest.",
                    "expected_entrypoints": sorted(expected_entrypoints),
                    "actual_entrypoints": sorted(actual_entrypoints),
                }
            )
        else:
            checks.append(
                {
                    "key": "spa_shell_entrypoints_match_manifest",
                    "path": shell_path,
                    "passed": response.status_code in {301, 302, 303, 307, 308} and location == "/",
                    "status_code": response.status_code,
                    "detail": location or response.text[:120],
                    "expected_entrypoints": sorted(expected_entrypoints),
                }
            )
    except Exception as exc:
        checks.append(
            {
                "key": "spa_shell_entrypoints_match_manifest",
                "path": shell_path,
                "passed": False,
                "status_code": 0,
                "detail": str(exc),
                "expected_entrypoints": sorted(expected_entrypoints),
            }
        )

    passed = bool(checks) and all(bool(check.get("passed")) for check in checks)
    return {
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "base_url": normalized_base_url,
        "commit_sha": str(manifest.get("commit_sha") or ""),
        "expected_entrypoints": sorted(expected_entrypoints),
        "checked_asset_count": len(expected_assets),
        "checks": checks,
    }


def _promotion_smoke_guard(
    *,
    base_url: str,
    deep: bool,
    register: bool,
    commit_sha: str,
    manifest_report: dict[str, Any],
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not base_url.strip():
        missing.append("base_url")
    if not (deep or register):
        missing.append("deep_smoke")
    if manifest_report.get("passed") is not True:
        missing.append("spa_dist_manifest")
    if not missing:
        return None
    return _blocking_report(
        "Render deploy promotion requires a deployed base URL, authenticated deep smoke checks, and a commit-bound SPA dist manifest.",
        commit_sha=commit_sha,
        detail={
            "missing": missing,
            "base_url_present": bool(base_url.strip()),
            "deep_smoke_requested": bool(deep or register),
            "spa_manifest": manifest_report,
            "required_flags": ["--base-url", "--deep or --register", "--engineering-gate or --spa-manifest"],
        },
    )


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
    parser.add_argument("--engineering-gate", default="", help="Commit-bound engineering gate artifact containing spa_dist.")
    parser.add_argument("--spa-manifest", default="", help="Optional standalone spa-dist manifest JSON.")
    parser.add_argument("--output", default="", help="Optional JSON report path for CI artifacts.")
    args = parser.parse_args()

    commit_sha = _current_commit(args.commit)
    if not commit_sha:
        report = _blocking_report("Unable to resolve a commit SHA for Render deploy verification.")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.output.strip():
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    expected_manifest, manifest_report = _resolve_expected_spa_manifest(
        commit_sha=commit_sha,
        engineering_gate=args.engineering_gate,
        spa_manifest=args.spa_manifest,
    )
    smoke_guard = _promotion_smoke_guard(
        base_url=args.base_url,
        deep=args.deep,
        register=args.register,
        commit_sha=commit_sha,
        manifest_report=manifest_report,
    )
    if smoke_guard is not None:
        report = {
            "commit_sha": commit_sha,
            "spa_manifest": manifest_report,
            "deploy": {
                "status": "not_triggered",
                "passed": False,
                "blocked": True,
                "commit_sha": commit_sha,
                "reason": "Promotion smoke requirements were not satisfied before triggering Render.",
            },
            "promotion": smoke_guard,
            "status": "blocked",
            "passed": False,
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output.strip():
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        print(rendered)
        return 1

    trigger_report = trigger_render_deploy(commit_sha=commit_sha, clear_cache=args.clear_cache)
    report: dict[str, Any] = {"commit_sha": commit_sha, "spa_manifest": manifest_report, "deploy": trigger_report}
    passed = bool(trigger_report.get("passed"))

    if passed:
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
        if passed and expected_manifest is not None:
            spa_assets_report = _verify_deployed_spa_assets(base_url=args.base_url, manifest=expected_manifest)
            report["spa_assets"] = spa_assets_report
            passed = passed and bool(spa_assets_report.get("passed"))

    report["status"] = "passed" if passed else "blocked"
    report["passed"] = passed
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output.strip():
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
