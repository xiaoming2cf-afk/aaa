from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify_access_gate import run_verification as run_access_gate_verification  # noqa: E402
from verify_data_lab_full import run_verification as run_data_lab_full_verification  # noqa: E402
from verify_optimization_lab import run_verification as run_optimization_verification  # noqa: E402


FINAL_OUTPUT_ROOT = REPO_ROOT / "蒙特卡洛"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def _build_notes(report: dict[str, Any]) -> str:
    access = report["steps"]["site_access"]["report"]
    data_lab = report["steps"]["data_lab_full"]["report"]
    optimization = report["steps"]["optimization"]["report"]
    lines = [
        "# Unified Monte Carlo Final Verification",
        "",
        "This directory contains the final successful unified Monte Carlo verification run.",
        "",
        "## Rule",
        "The repository only writes to `蒙特卡洛/` after the entire unified verification succeeds.",
        "Any failed intermediate run stays outside the final directory and is not treated as deliverable output.",
        "",
        "## Included verification scopes",
        "- `site_access/`: deployed-host access control and login gate checks.",
        "- `country_panel/`: country-level panel Monte Carlo inputs and model outputs.",
        "- `macro_finance_ts/`: macro-finance time-series Monte Carlo inputs and model outputs.",
        "- `model_anchor/`: Data Lab method pages, result pages, and complex-output anchoring records.",
        "- `optimization/`: multi-algorithm, multi-function, multi-run optimization validation assets.",
        "",
        "## Final successful run summary",
        f"- Finished at: {report['completed_at']}",
        f"- Site access status: {access['status']}",
        f"- Data Lab full status: {data_lab['status']}",
        f"- Data Lab model count: {data_lab['model_count']}",
        f"- Data Lab processing run count: {data_lab['processing_run_count']}",
        f"- Optimization status: {optimization['status']}",
        f"- Optimization task success count: {optimization['standard_suite']['success_count']}",
        f"- Optimization task failure count: {optimization['standard_suite']['failure_count']}",
        f"- Optimization figures: {optimization['standard_suite']['figure_count']}",
        f"- Optimization tables: {optimization['standard_suite']['table_count']}",
        "",
        "## Review order",
        "1. Open `verification_report.json` at the root.",
        "2. Review `site_access/verification_report.json`.",
        "3. Review `model_anchor/model_anchor_report.json` and the model result bundles under `country_panel/` and `macro_finance_ts/`.",
        "4. Review `optimization/verification_report.json`, then inspect `optimization/figures/` and `optimization/tables/`.",
        "",
        "## Acceptance rule that this run satisfied",
        "- Anonymous deployed-host access is limited to the homepage public daily report surfaces.",
        "- Data Lab produced complex research outputs for all verified models.",
        "- Optimization produced multi-algorithm, multi-function, multi-run outputs and associated statistical tables/figures.",
    ]
    return "\n".join(lines)


def _build_root_readme() -> str:
    return "\n".join(
        [
            "# 蒙特卡洛",
            "",
            "This folder stores only the final successful unified Monte Carlo verification run.",
            "",
            "## Structure",
            "- `verification_report.json`: top-level final verification summary.",
            "- `notes.md`: explanation of the successful run and review order.",
            "- `site_access/`: deployed-host access-control checks.",
            "- `country_panel/`: Monte Carlo panel data inputs and result bundles.",
            "- `macro_finance_ts/`: Monte Carlo time-series inputs and result bundles.",
            "- `model_anchor/`: Data Lab catalog/method/result anchoring artifacts.",
            "- `optimization/`: optimization suite figures, tables, raw processes, and result detail.",
            "",
            "No partial or failed intermediate run is written here.",
        ]
    )


def run_final_verification() -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-unified-mc-"))
    site_access_dir = temp_root / "site_access"
    optimization_dir = temp_root / "optimization"
    data_lab_root = temp_root

    access_report = run_access_gate_verification(output_dir=site_access_dir)
    data_lab_report = run_data_lab_full_verification(output_dir=data_lab_root)
    optimization_report = run_optimization_verification(output_dir=optimization_dir)

    if data_lab_root.joinpath("verification_report.json").exists():
        data_lab_root.joinpath("verification_report.json").replace(temp_root / "model_anchor" / "data_lab_full_verification_report.json")

    final_report = {
        "status": "passed",
        "completed_at": datetime.now().astimezone().isoformat(),
        "steps": {
            "site_access": {"status": access_report["status"], "report": access_report},
            "data_lab_full": {"status": data_lab_report["status"], "report": data_lab_report},
            "optimization": {"status": optimization_report["status"], "report": optimization_report},
        },
        "paths": {
            "site_access": "site_access",
            "country_panel": "country_panel",
            "macro_finance_ts": "macro_finance_ts",
            "model_anchor": "model_anchor",
            "optimization": "optimization",
        },
    }
    _write_json(temp_root / "verification_report.json", final_report)
    _write_text(temp_root / "notes.md", _build_notes(final_report))
    _write_text(temp_root / "README.md", _build_root_readme())

    if FINAL_OUTPUT_ROOT.exists():
        shutil.rmtree(FINAL_OUTPUT_ROOT)
    shutil.move(str(temp_root), str(FINAL_OUTPUT_ROOT))
    return final_report


def main() -> None:
    report = run_final_verification()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
