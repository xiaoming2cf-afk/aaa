from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
OUTPUT_ROOT = REPO_ROOT / "\u8499\u7279\u5361\u6d1b"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify_access_gate import run_verification as run_access_gate_verification  # noqa: E402
from verify_optimization_lab import run_verification as run_optimization_verification  # noqa: E402


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def build_anchor_report(optimization_report: dict, gate_report: dict) -> dict[str, object]:
    return {
        "suite_name": "optimization_lab_anchor",
        "objective": "Verify the standalone Optimization Lab, anchor every available optimizer and Opfunu benchmark to a real local run, and confirm the remote access gate only leaves Platform Navigation open before login.",
        "workflow": [
            "Fetch the Optimization Lab catalog through the API and confirm the full Mealpy and Opfunu inventories are exposed.",
            "Run a smoke solve for every available Mealpy optimizer on Ackley01.",
            "Run a smoke solve for every available Opfunu benchmark using a stable PSO baseline.",
            "Run one private suite through the public API to confirm result records, figures, and CSV assets are exported end to end.",
            "Check remote unauthenticated access against key APIs and standalone pages, then confirm authenticated access unlocks the same routes.",
        ],
        "stability_fixes": [
            "mealpy.human_based.GSKA.OriginalGSKA now enforces a minimum population size of 20.",
            "mealpy.human_based.GSKA.DevGSKA now enforces a minimum population size of 20.",
            "mealpy.physics_based.ESO.OriginalESO now applies a runtime safeguard that clips the percentile threshold used inside the ionized-region selection step.",
            "mealpy.bio_based.BCO.OriginalBCO remains visible in the catalog but is explicitly marked unavailable because the upstream implementation references undefined attributes during evolve().",
        ],
        "verification_summary": {
            "optimizer_health": optimization_report.get("optimizer_health", {}),
            "function_health": optimization_report.get("function_health", {}),
            "remote_gate": gate_report.get("remote_api_status", {}),
        },
        "manual_review_focus": [
            "Open figures/ to confirm average convergence, radar, ranking, and per-function curve PNGs were exported.",
            "Open tables/ to review score, rank, Wilcoxon, sign-test, curve, and raw-run CSV files.",
            "Check result_detail.json to confirm the Friedman summary and ranking preview match the exported tables.",
            "Check access_gate/verification_report.json to confirm remote unauthenticated requests are rejected with 401 while the same routes unlock after login.",
        ],
    }


def main() -> None:
    optimization_dir = OUTPUT_ROOT / "optimization_lab"
    access_gate_dir = OUTPUT_ROOT / "access_gate"
    shutil.rmtree(optimization_dir, ignore_errors=True)
    shutil.rmtree(access_gate_dir, ignore_errors=True)

    optimization_report = run_optimization_verification(output_dir=optimization_dir)
    access_gate_report = run_access_gate_verification(output_dir=access_gate_dir)
    anchor_report = build_anchor_report(optimization_report, access_gate_report)

    write_json(optimization_dir / "optimization_anchor_report.json", anchor_report)
    write_text(
        optimization_dir / "\u4f18\u5316\u6a21\u5757\u6838\u67e5\u4e0e\u951a\u5b9a\u8bf4\u660e.md",
        "\n".join(
            [
                "# Optimization Lab Verification Notes",
                "",
                "This note explains how the Optimization Lab and the remote unauthenticated access gate were verified in the current run.",
                "",
                "## Verification path",
                "1. Pull the Mealpy and Opfunu catalogs through the API and confirm the counts and defaults.",
                "2. Run one smoke solve for every optimizer that is marked available in the catalog.",
                "3. Run one smoke solve for every benchmark function that is marked available in the catalog.",
                "4. Launch a real private optimization suite through the API and confirm figures, CSV tables, raw run data, and the result detail page.",
                "5. Re-run the remote access gate checks to confirm unauthenticated public-host requests are blocked while authenticated requests succeed.",
                "",
                "## Fixes applied in this cycle",
                "- `OriginalGSKA` / `DevGSKA`: the platform now enforces a minimum `pop_size = 20` because the upstream implementation is unstable with very small populations.",
                "- `OriginalESO`: the platform now clips the percentile threshold used inside the ionized-region selection step.",
                "- `OriginalBCO`: still shown in the catalog, but explicitly marked unavailable because the upstream Mealpy implementation references undefined attributes during `evolve()`.",
                "",
                "## Current conclusion",
                f"- Verified available optimizers: {optimization_report['optimizer_health']['tested']}",
                f"- Verified available benchmark functions: {optimization_report['function_health']['tested']}",
                f"- Remote access-gate status: {access_gate_report['status']}",
                "- Exported assets are stored in `figures/` and `tables/` for manual inspection.",
                "",
                "## Manual review order",
                "1. Start with `verification_report.json`.",
                "2. Review `optimizer_health_sweep.json` and `function_health_sweep.json`.",
                "3. Open `result_detail.json`, then inspect `figures/` and `tables/`.",
                "4. Finish with `../access_gate/verification_report.json`.",
            ]
        ),
    )
    write_text(
        optimization_dir / "README.md",
        "\n".join(
            [
                "# Optimization Lab Monte Carlo Export",
                "",
                "This folder stores the reproducible verification output for the standalone Optimization Lab.",
                "",
                "## Files",
                "- `verification_report.json`: top-level verification result for the optimization module.",
                "- `optimization_anchor_report.json`: the anchoring logic, fixes, and manual review checklist.",
                "- `catalog_summary.json`: full optimizer/function catalog snapshot from the API.",
                "- `optimizer_health_sweep.json`: one smoke solve for every available Mealpy optimizer.",
                "- `function_health_sweep.json`: one smoke solve for every available Opfunu benchmark.",
                "- `api_run_response.json`: the private suite run response returned by the API.",
                "- `result_detail.json`: the stored optimization result detail.",
                "- `figures/`: exported PNG figures from the suite run.",
                "- `tables/`: exported CSV tables from the suite run.",
                "",
                "## Related folder",
                "- `../access_gate/`: verification output for remote unauthenticated access restrictions.",
            ]
        ),
    )
    print(json.dumps({"optimization_lab": str(optimization_dir), "access_gate": str(access_gate_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
