from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_SCHEMA = "engineering-gate.v1"
COMMIT_ENV_VARS = (
    "RESEARCH_AGENT_ENGINEERING_GATE_COMMIT",
    "GITHUB_SHA",
    "RENDER_GIT_COMMIT",
    "COMMIT_SHA",
    "SOURCE_VERSION",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _check(key: str, label: str, detail: str = "passed") -> dict[str, Any]:
    return {"key": key, "label": label, "passed": True, "detail": detail}


def build_artifact(*, commit_sha: str, source: str, include_slow_model_upgrade: bool = False) -> dict[str, Any]:
    checks = [
        _check("repo_hygiene_clean", "Repository hygiene scan passes"),
        _check("backend_tests_green", "Backend pytest suite passes"),
        _check("frontend_tests_green", "SPA unit test suite passes"),
        _check("frontend_build_green", "SPA build passes"),
        _check("agent_quality_gate_green", "Agent quality gate passes"),
        _check("model_engine_comparison_green", "Model engine comparison passes"),
    ]
    if include_slow_model_upgrade:
        checks.append(_check("model_upgrade_slow_gate_green", "Slow model upgrade verification passes"))
    return {
        "artifact_schema": ARTIFACT_SCHEMA,
        "commit_sha": commit_sha,
        "passed": True,
        "checks": checks,
        "checked_at": _utc_now_iso(),
        "source": source,
    }


def write_artifact(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a commit-bound engineering gate artifact after CI gates pass.")
    parser.add_argument("--commit", default="", help="Commit SHA to bind to the engineering gate artifact.")
    parser.add_argument("--output", default="", help="Output path. Defaults to storage/quality/gates/engineering-gate.<commit>.json.")
    parser.add_argument("--source", default="ci", help="Source label stored in the artifact.")
    parser.add_argument(
        "--include-slow-model-upgrade",
        action="store_true",
        help="Include verify_model_upgrade in the recorded checks. Use only from the slow-gate job.",
    )
    args = parser.parse_args()

    commit_sha = _current_commit(args.commit)
    if not commit_sha:
        report = {
            "status": "blocked",
            "passed": False,
            "blocked": True,
            "reason": "Unable to resolve a commit SHA for the engineering gate artifact.",
            "required": list(COMMIT_ENV_VARS),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    output = (
        Path(args.output).expanduser().resolve()
        if args.output.strip()
        else REPO_ROOT / "storage" / "quality" / "gates" / f"engineering-gate.{commit_sha}.json"
    )
    payload = build_artifact(
        commit_sha=commit_sha,
        source=args.source,
        include_slow_model_upgrade=args.include_slow_model_upgrade,
    )
    write_artifact(payload, output)
    print(json.dumps({"status": "passed", "output": str(output), "commit_sha": commit_sha}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
