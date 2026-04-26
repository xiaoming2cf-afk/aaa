from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ENGINEERING_GATE_SCHEMA = "engineering-gate.v1"


def _clean_commit(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "", str(value or "").strip())


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, f"{path} is not readable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path} must contain a JSON object."
    return payload, None


def _expected_artifact_name(prefix: str, commit_sha: str) -> str:
    return f"{prefix}.{commit_sha}.json"


def _check_engineering_gate(path: Path, *, commit_sha: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    payload, error = _load_json(path)
    if error or payload is None:
        return [{"key": "engineering_gate_json_readable", "passed": False, "detail": error}]

    artifact_commit = _clean_commit(str(payload.get("commit_sha") or ""))
    filename = path.name
    if payload.get("artifact_schema") != ENGINEERING_GATE_SCHEMA:
        failures.append(
            {
                "key": "engineering_gate_schema",
                "passed": False,
                "detail": f"Expected {ENGINEERING_GATE_SCHEMA}, found {payload.get('artifact_schema')!r}.",
            }
        )
    if artifact_commit != commit_sha:
        failures.append(
            {
                "key": "engineering_gate_commit_match",
                "passed": False,
                "detail": f"Artifact commit {artifact_commit or '<missing>'} does not match expected {commit_sha}.",
            }
        )
    expected_filename = _expected_artifact_name("engineering-gate", commit_sha)
    if filename != expected_filename:
        failures.append(
            {
                "key": "engineering_gate_filename_commit_match",
                "passed": False,
                "detail": f"Artifact filename {filename!r} must equal {expected_filename!r}.",
            }
        )
    if payload.get("passed") is not True:
        failed_checks = [check for check in payload.get("checks", []) if isinstance(check, dict) and not check.get("passed")]
        failures.append(
            {
                "key": "engineering_gate_passed",
                "passed": False,
                "detail": "Engineering gate artifact is not green.",
                "failed_checks": failed_checks,
            }
        )
    return failures


def _check_render_deploy(path: Path, *, commit_sha: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    payload, error = _load_json(path)
    if error or payload is None:
        return [{"key": "render_deploy_json_readable", "passed": False, "detail": error}]

    report_commit = _clean_commit(str(payload.get("commit_sha") or payload.get("deploy", {}).get("commit_sha") or ""))
    if report_commit != commit_sha:
        failures.append(
            {
                "key": "render_deploy_commit_match",
                "passed": False,
                "detail": f"Render deploy report commit {report_commit or '<missing>'} does not match expected {commit_sha}.",
            }
        )
    expected_filename = _expected_artifact_name("render-deploy", commit_sha)
    if path.name != expected_filename:
        failures.append(
            {
                "key": "render_deploy_filename_commit_match",
                "passed": False,
                "detail": f"Render deploy report filename {path.name!r} must equal {expected_filename!r}.",
            }
        )
    deploy_payload = payload.get("deploy") if isinstance(payload.get("deploy"), dict) else {}
    smoke_payload = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    deploy_failed = deploy_payload.get("passed") is not True
    smoke_failed = smoke_payload.get("passed") is not True
    if payload.get("passed") is not True or deploy_failed or smoke_failed:
        failures.append(
            {
                "key": "render_deploy_passed",
                "passed": False,
                "detail": payload.get("reason") or deploy_payload.get("reason") or "Render deploy report is not green.",
                "deploy": deploy_payload,
                "smoke": smoke_payload,
            }
        )
    return failures


def verify_artifacts(*, commit_sha: str, engineering_gate: Path, render_deploy: Path | None = None) -> dict[str, Any]:
    expected_commit = _clean_commit(commit_sha)
    failures: list[dict[str, Any]] = []
    if not expected_commit:
        failures.append({"key": "expected_commit_present", "passed": False, "detail": "Expected commit SHA is empty."})
    if not engineering_gate.exists():
        failures.append(
            {
                "key": "engineering_gate_artifact_present",
                "passed": False,
                "detail": f"{engineering_gate} does not exist.",
            }
        )
    elif expected_commit:
        failures.extend(_check_engineering_gate(engineering_gate, commit_sha=expected_commit))

    if render_deploy is not None:
        if not render_deploy.exists():
            failures.append(
                {
                    "key": "render_deploy_report_present",
                    "passed": False,
                    "detail": f"{render_deploy} does not exist.",
                }
            )
        elif expected_commit:
            failures.extend(_check_render_deploy(render_deploy, commit_sha=expected_commit))

    return {
        "status": "passed" if not failures else "blocked",
        "passed": not failures,
        "commit_sha": expected_commit,
        "engineering_gate": str(engineering_gate),
        "render_deploy": str(render_deploy) if render_deploy is not None else "",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deploy artifacts are green and bound to the same commit.")
    parser.add_argument("--commit", required=True, help="Expected commit SHA.")
    parser.add_argument("--engineering-gate", required=True, help="Path to engineering-gate.<commit>.json.")
    parser.add_argument("--render-deploy", default="", help="Optional path to render-deploy.<commit>.json.")
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = verify_artifacts(
        commit_sha=args.commit,
        engineering_gate=Path(args.engineering_gate).expanduser().resolve(),
        render_deploy=Path(args.render_deploy).expanduser().resolve() if args.render_deploy.strip() else None,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output.strip():
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
