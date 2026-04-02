from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections import Counter
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

from compare_model_engines import run_comparison  # noqa: E402
from verify_access_gate import run_verification as run_access_gate_verification  # noqa: E402
from verify_data_lab_full import run_verification as run_data_lab_full_verification  # noqa: E402
from verify_optimization_lab import run_verification as run_optimization_verification  # noqa: E402
from research_agent.model_engine_selection import WINNER_FILE, write_model_engine_winners  # noqa: E402


FINAL_OUTPUT_ROOT = REPO_ROOT / "蒙特卡洛"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _status_ok(report: dict[str, Any]) -> bool:
    return str(report.get("status", "")).lower() == "passed"


def _copy_children(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def _merge_model_upgrade_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    status = "passed" if all(_status_ok(report) for report in reports) else "failed"
    counts = Counter()
    models: list[dict[str, Any]] = []
    groups: list[str] = []
    methods: list[str] = []
    for report in reports:
        counts.update(report.get("group_counts", {}))
        models.extend(report.get("models", []))
        groups.extend(report.get("groups", []))
        methods.extend(report.get("methods", []))
    return {
        "status": status,
        "model_count": len(models),
        "group_counts": dict(counts),
        "groups": sorted({group for group in groups if group}),
        "methods": sorted({method for method in methods if method}),
        "models": models,
    }


def _build_notes(report: dict[str, Any]) -> str:
    steps = report["steps"]
    return "\n".join(
        [
            "# Unified Monte Carlo Final Verification",
            "",
            "This directory stores only the final successful unified Monte Carlo run.",
            "",
            "## Execution order",
            "1. Compare baseline vs candidate engines on overlapping models.",
            "2. Pick winners using the quality-first rule: accuracy > completeness > stability > speed.",
            "3. Re-run the full Data Lab baseline suite with winners enabled.",
            "4. Merge successful split model-upgrade chunks.",
            "5. Run strict site-access checks and strict optimization validation.",
            "6. Persist the final results here only after every step passes.",
            "",
            "## Final successful summary",
            f"- Completed at: {report['completed_at']}",
            f"- Compared overlap methods: {steps['comparison']['report']['model_count']}",
            f"- Winner file updated: {steps['comparison']['winner_file_updated']}",
            f"- Core Data Lab status: {steps['data_lab_full']['report']['status']}",
            f"- Core Data Lab model count: {steps['data_lab_full']['report']['model_count']}",
            f"- Upgrade suite status: {steps['model_upgrade']['report']['status']}",
            f"- Upgrade suite model count: {steps['model_upgrade']['report']['model_count']}",
            f"- Site access status: {steps['site_access']['report']['status']}",
            f"- Optimization status: {steps['optimization']['report']['status']}",
            f"- Optimization success count: {steps['optimization']['report']['standard_suite']['success_count']}",
            "",
            "## Review order",
            "1. Open `comparison_report.json` and `verification_report.json` at the root.",
            "2. Review `country_panel/` and `macro_finance_ts/` result bundles.",
            "3. Review `model_anchor/` for the upgrade and anchoring outputs.",
            "4. Review `site_access/verification_report.json`.",
            "5. Review `optimization/verification_report.json`, then inspect `optimization/figures/` and `optimization/tables/`.",
        ]
    )


def _build_readme() -> str:
    return "\n".join(
        [
            "# 蒙特卡洛",
            "",
            "This folder contains only the final successful unified Monte Carlo verification run.",
            "",
            "## Included outputs",
            "- `comparison_report.json`: overlap model baseline-vs-candidate comparison.",
            "- `verification_report.json`: final top-level status summary.",
            "- `notes.md`: review guide for the successful run.",
            "- `country_panel/`: country-level panel Monte Carlo inputs and result bundles.",
            "- `macro_finance_ts/`: macro-finance time-series inputs and result bundles.",
            "- `model_anchor/`: anchoring outputs for method pages and model-upgrade coverage.",
            "- `site_access/`: deployed-host access-control verification.",
            "- `optimization/`: strict multi-algorithm, multi-function, multi-run optimization outputs.",
            "",
            "No failed intermediate run is written here.",
        ]
    )


def run_finalization(
    country_chunk_dir: Path,
    macro_chunk_dir: Path,
) -> dict[str, Any]:
    staging_root = Path(tempfile.mkdtemp(prefix="erp-finalize-mc-"))
    compare_dir = staging_root / "_comparison_tmp"
    winner_backup_exists = WINNER_FILE.exists()
    winner_backup = WINNER_FILE.read_text(encoding="utf-8") if winner_backup_exists else ""
    winner_file_updated = False
    try:
        comparison_report = run_comparison(output_dir=compare_dir)
        winners = comparison_report["winners"]
        write_model_engine_winners(
            winners,
            metadata={
                "generated_at": datetime.now().astimezone().isoformat(),
                "source": "scripts/finalize_unified_monte_carlo.py",
            },
        )
        winner_file_updated = True

        site_access_report = run_access_gate_verification(output_dir=staging_root / "site_access")
        data_lab_full_report = run_data_lab_full_verification(output_dir=staging_root)
        optimization_report = run_optimization_verification(output_dir=staging_root / "optimization")

        country_report = _load_json(country_chunk_dir / "verification_report.json")
        macro_report = _load_json(macro_chunk_dir / "verification_report.json")
        model_upgrade_report = _merge_model_upgrade_reports(country_report, macro_report)

        _copy_children(country_chunk_dir / "country_panel" / "models", staging_root / "country_panel" / "models")
        _copy_children(macro_chunk_dir / "macro_finance_ts" / "models", staging_root / "macro_finance_ts" / "models")
        _copy_children(country_chunk_dir / "model_anchor", staging_root / "model_anchor")
        _copy_children(macro_chunk_dir / "model_anchor", staging_root / "model_anchor")
        _write_json(staging_root / "model_anchor" / "model_upgrade_report.json", model_upgrade_report)

        failed_steps = [
            name
            for name, payload in {
                "comparison": comparison_report,
                "site_access": site_access_report,
                "data_lab_full": data_lab_full_report,
                "model_upgrade": model_upgrade_report,
                "optimization": optimization_report,
            }.items()
            if not _status_ok(payload)
        ]
        if failed_steps:
            raise AssertionError(f"Unified Monte Carlo failed: {', '.join(failed_steps)}")

        final_report = {
            "status": "passed",
            "completed_at": datetime.now().astimezone().isoformat(),
            "steps": {
                "comparison": {
                    "report": {
                        "status": comparison_report["status"],
                        "model_count": len(comparison_report["models"]),
                        "winners": comparison_report["winners"],
                    },
                    "winner_file_updated": winner_file_updated,
                },
                "site_access": {"report": site_access_report},
                "data_lab_full": {"report": data_lab_full_report},
                "model_upgrade": {"report": model_upgrade_report},
                "optimization": {"report": optimization_report},
            },
            "paths": {
                "comparison_report": "comparison_report.json",
                "verification_report": "verification_report.json",
                "country_panel": "country_panel",
                "macro_finance_ts": "macro_finance_ts",
                "model_anchor": "model_anchor",
                "site_access": "site_access",
                "optimization": "optimization",
            },
        }

        _write_json(staging_root / "comparison_report.json", comparison_report)
        _write_json(staging_root / "verification_report.json", final_report)
        _write_text(staging_root / "notes.md", _build_notes(final_report))
        _write_text(staging_root / "README.md", _build_readme())
        shutil.rmtree(compare_dir, ignore_errors=True)

        if FINAL_OUTPUT_ROOT.exists():
            shutil.rmtree(FINAL_OUTPUT_ROOT)
        shutil.move(str(staging_root), str(FINAL_OUTPUT_ROOT))
        return final_report
    except Exception:
        if winner_backup_exists:
            WINNER_FILE.write_text(winner_backup, encoding="utf-8")
        elif WINNER_FILE.exists():
            WINNER_FILE.unlink()
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


def main() -> None:
    country_chunk_dir = REPO_ROOT / "_tmp_model_upgrade_country_out"
    macro_chunk_dir = REPO_ROOT / "_tmp_model_upgrade_macro_out"
    report = run_finalization(country_chunk_dir, macro_chunk_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
