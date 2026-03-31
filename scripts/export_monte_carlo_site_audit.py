from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "\u8499\u7279\u5361\u6d1b" / "site_audit"
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

SCRIPT_MATRIX = [
    ("verify_access_gate.py", "Remote unauthenticated access gate"),
    ("verify_optimization_lab.py", "Optimization Lab catalog, health sweep, and suite export"),
    ("verify_data_lab.py", "Data Lab processing, models, figures, and result pages"),
    ("verify_provider_center.py", "Provider Center integrations and provider catalog"),
    ("verify_security_and_literature.py", "Paper Library, OpenAlex, PDF import, and knowledge imports"),
    ("verify_public_monitor.py", "Public Daily Monitor moderation and source panel"),
    ("verify_public_sources.py", "Public monitor official-source coverage"),
    ("verify_workbench_and_knowledge.py", "Workbench and Private Knowledge Base"),
    ("verify_case_workspace.py", "Case workspace linking and isolation"),
]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    ensure_dir(OUTPUT_ROOT)
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for script_name, description in SCRIPT_MATRIX:
        command = [str(PYTHON), str(REPO_ROOT / "scripts" / script_name)]
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        slug = script_name.replace(".py", "")
        stdout_path = OUTPUT_ROOT / f"{slug}.stdout.log"
        stderr_path = OUTPUT_ROOT / f"{slug}.stderr.log"
        write_text(stdout_path, completed.stdout)
        write_text(stderr_path, completed.stderr)
        entry = {
            "script": script_name,
            "description": description,
            "returncode": completed.returncode,
            "stdout_log": str(stdout_path.relative_to(OUTPUT_ROOT.parent)),
            "stderr_log": str(stderr_path.relative_to(OUTPUT_ROOT.parent)),
        }
        results.append(entry)
        if completed.returncode != 0:
            failures.append(entry)

    summary = {
        "status": "passed" if not failures else "failed",
        "script_count": len(results),
        "passed_count": len(results) - len(failures),
        "failed_count": len(failures),
        "results": results,
        "failures": failures,
    }
    write_json(OUTPUT_ROOT / "verification_report.json", summary)
    write_text(
        OUTPUT_ROOT / "README.md",
        "\n".join(
            [
                "# Site Audit Export",
                "",
                "This folder records stdout/stderr for every verification script that was executed in the current audit cycle.",
                "",
                "## Files",
                "- `verification_report.json`: top-level pass/fail summary.",
                "- `*.stdout.log`: standard output captured from each verification script.",
                "- `*.stderr.log`: warnings or error output captured from each verification script.",
            ]
        ),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
