from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from session_auth import same_origin_headers, session_token_from_cookies


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from verify_data_lab import (  # noqa: E402
    assert_redirect_location,
    assert_png_response,
    auth_headers,
    configure_test_environment,
    create_workspace,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _is_nonfinite_fitness(result: dict[str, Any]) -> bool:
    value = result.get("best_fitness")
    try:
        return not math.isfinite(float(value))
    except Exception:
        return True


def _run_tasks(tasks: list[dict[str, Any]], max_workers: int = 12) -> list[dict[str, Any]]:
    from research_agent.optimization_lab import _run_single_optimization_task

    if not tasks:
        return []
    results: list[dict[str, Any]] = []
    worker_count = min(max_workers, len(tasks))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_run_single_optimization_task, task) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (item["optimizer_name"], item["function_name"], item["run_index"]))
    return results


def _download_assets(client: TestClient, token: str, assets: list[dict[str, Any]], output_dir: Path, *, expect_png: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, asset in enumerate(assets, start=1):
        download = client.get(f"/api/assets/{asset['id']}/download", headers=auth_headers(token))
        download.raise_for_status()
        filename = asset.get("filename") or f"asset-{index}"
        if expect_png:
            assert_png_response(download, filename)
            if not filename.lower().endswith(".png"):
                filename = f"{filename}.png"
        (output_dir / filename).write_bytes(download.content)


def run_verification(output_dir: Path | None = None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-optimization-lab-verify-"))
    configure_test_environment(temp_root)

    from research_agent.optimization_lab import MEALPY_DISABLED_OPTIMIZERS
    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)

        remote_headers = {"host": "economic-research-web.onrender.com"}

        anonymous_data_lab = client.get("/data-lab", headers=remote_headers, follow_redirects=False)
        if anonymous_data_lab.status_code not in {302, 303, 307, 308}:
            raise AssertionError(f"/data-lab: expected redirect while anonymous, got {anonymous_data_lab.status_code}")

        register = client.post(
            "/api/auth/register",
            headers=same_origin_headers("http://testserver"),
            json={"full_name": "Optimization Reviewer", "email": "optimizer@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = session_token_from_cookies(client)
        workspace_id = create_workspace(client, token, "Optimization Verification")

        optimization_page = client.get(
            "/data-lab/optimization",
            headers={**remote_headers, **auth_headers(token)},
            follow_redirects=False,
        )
        assert_redirect_location("/data-lab/optimization", optimization_page, "/app/data-lab/optimization")

        catalog_response = client.get("/api/optimization/catalog", headers={**remote_headers, **auth_headers(token)})
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
        summary = catalog["summary"]
        requirements = catalog["suite_requirements"]
        if summary["optimizer_count"] < 200:
            raise AssertionError("Optimization catalog did not expose the full Mealpy optimizer set")
        if summary["function_count"] < 300:
            raise AssertionError("Optimization catalog did not expose the full Opfunu benchmark set")
        if requirements["min_algorithms"] < 3 or requirements["min_functions"] < 3 or requirements["min_runs"] < 3:
            raise AssertionError("Optimization suite requirements regressed below the strict research thresholds")

        available_optimizers = [item["name"] for item in catalog["optimizers"] if item["availability"]["status"] == "available"]
        available_functions = [item["name"] for item in catalog["functions"] if item["availability"]["status"] == "available"]
        baseline_optimizers = catalog["defaults"]["optimizers"] or available_optimizers
        baseline_functions = catalog["defaults"]["functions"] or available_functions
        if len(baseline_optimizers) < 3 or len(baseline_functions) < 3:
            raise AssertionError("Optimization catalog defaults regressed below the minimum standard verification set")
        default_optimizer = baseline_optimizers[0]
        default_function = baseline_functions[0]

        optimizer_health_tasks = [
            {
                "optimizer_name": optimizer_name,
                "function_name": default_function,
                "run_index": 1,
                "seed": 100_000 + index,
                "epoch": 5,
                "pop_size": 12,
                "dimension": 30,
            }
            for index, optimizer_name in enumerate(available_optimizers, start=1)
        ]
        optimizer_health_results = _run_tasks(optimizer_health_tasks, max_workers=12)
        optimizer_failures = [item for item in optimizer_health_results if item["status"] != "ok" or _is_nonfinite_fitness(item)]
        if optimizer_failures:
            raise AssertionError(
                f"{len(optimizer_failures)} available optimizers failed the smoke solve: "
                + "; ".join(f"{item['optimizer_name']} => {item.get('error', 'unknown error')}" for item in optimizer_failures[:10])
            )

        function_health_tasks = [
            {
                "optimizer_name": default_optimizer,
                "function_name": function_name,
                "run_index": 1,
                "seed": 200_000 + index,
                "epoch": 5,
                "pop_size": 16,
                "dimension": 30,
            }
            for index, function_name in enumerate(available_functions, start=1)
        ]
        function_health_results = _run_tasks(function_health_tasks, max_workers=12)
        function_failures = [item for item in function_health_results if item["status"] != "ok" or _is_nonfinite_fitness(item)]
        if function_failures:
            raise AssertionError(
                f"{len(function_failures)} benchmark functions failed the smoke solve: "
                + "; ".join(f"{item['function_name']} => {item.get('error', 'unknown error')}" for item in function_failures[:10])
            )

        small_suite_payload = {
            "suite_label": "Small Suite Should Fail",
            "optimizer_names": baseline_optimizers[:2],
            "function_names": baseline_functions[:2],
            "dimension": 20,
            "epoch": 6,
            "pop_size": 16,
            "runs": 2,
            "workers": 2,
        }
        small_suite_response = client.post(
            f"/api/workspaces/{workspace_id}/optimization/run",
            headers={**remote_headers, **auth_headers(token), "Content-Type": "application/json"},
            json=small_suite_payload,
        )
        if small_suite_response.status_code != 400:
            raise AssertionError(f"Small optimization suite should fail with 400, got {small_suite_response.status_code}")
        small_suite_error = small_suite_response.json().get("detail", "")
        if "at least" not in small_suite_error.lower():
            raise AssertionError(f"Small suite error should explain the strict preconditions, got {small_suite_error!r}")

        standard_suite_payload = {
            "suite_label": "Monte Carlo Optimization Standard Suite",
            "optimizer_names": baseline_optimizers[:3],
            "function_names": baseline_functions[:3],
            "dimension": 30,
            "epoch": 10,
            "pop_size": 20,
            "runs": 3,
            "workers": 3,
            "seed_base": 20260331,
        }
        run_response = client.post(
            f"/api/workspaces/{workspace_id}/optimization/run",
            headers={**remote_headers, **auth_headers(token), "Content-Type": "application/json"},
            json=standard_suite_payload,
        )
        run_response.raise_for_status()
        run_payload = run_response.json()
        record_id = run_payload["record"]["id"]

        result_history = client.get(
            f"/api/workspaces/{workspace_id}/optimization/results",
            headers={**remote_headers, **auth_headers(token)},
        )
        result_history.raise_for_status()
        history_items = result_history.json()["items"]
        if not any(item["id"] == record_id for item in history_items):
            raise AssertionError("Optimization run did not land in workspace history")

        detail_response = client.get(
            f"/api/optimization/results/{record_id}",
            headers={**remote_headers, **auth_headers(token)},
        )
        detail_response.raise_for_status()
        detail_payload = detail_response.json()
        result = detail_payload["result"]
        summary_payload = result.get("summary", {})
        artifacts = result.get("artifacts", {})
        figure_assets = artifacts.get("figures", [])
        table_assets = artifacts.get("tables", [])

        if summary_payload.get("success_count") != 27:
            raise AssertionError(f"Standard suite should complete 27 tasks, got {summary_payload.get('success_count')}")
        if summary_payload.get("failure_count") != 0:
            raise AssertionError("Standard suite reported failed optimization tasks")
        if len(figure_assets) < 6:
            raise AssertionError("Optimization suite did not generate the expected research figures")
        if len(table_assets) < 6:
            raise AssertionError("Optimization suite did not generate the expected research tables")
        if not result.get("ranking_preview"):
            raise AssertionError("Optimization suite did not return a ranking preview")
        if not result.get("friedman_preview"):
            raise AssertionError("Optimization suite did not return a Friedman table preview")
        if not result.get("raw_curve_rows"):
            raise AssertionError("Optimization suite did not preserve raw convergence process data")
        if not result.get("raw_run_rows"):
            raise AssertionError("Optimization suite did not preserve raw per-run process data")

        figure_titles = {figure.get("title", "") for figure in figure_assets}
        expected_figure_hints = ["convergence", "radar", "ranking"]
        if not all(any(hint in title.lower() for title in figure_titles) for hint in expected_figure_hints):
            raise AssertionError(f"Optimization figures are missing expected outputs: {sorted(figure_titles)}")

        table_names = {
            " ".join(
                filter(
                    None,
                    [
                        str(table.get("title", "")).lower(),
                        str(table.get("description", "")).lower(),
                        str(table.get("filename", "")).lower(),
                    ],
                )
            )
            for table in table_assets
        }
        required_table_fragments = ["friedman", "wilcoxon", "sign-test", "ranks", "curves", "runs"]
        if not all(any(fragment in name for name in table_names) for fragment in required_table_fragments):
            raise AssertionError(f"Optimization tables are missing expected exports: {sorted(table_names)}")

        result_page = client.get(
            f"/data-lab/results/optimization/{record_id}",
            headers={**remote_headers, **auth_headers(token)},
            follow_redirects=False,
        )
        assert_redirect_location(
            f"/data-lab/results/optimization/{record_id}",
            result_page,
            f"/app/data-lab/results?type=optimization&id={record_id}",
        )

        if output_dir:
            _write_json(
                output_dir / "pages" / "legacy_optimization_redirects.json",
                {
                    "/data-lab/optimization": optimization_page.headers.get("location"),
                    f"/data-lab/results/optimization/{record_id}": result_page.headers.get("location"),
                },
            )
            _write_json(output_dir / "catalog_summary.json", catalog)
            _write_json(output_dir / "small_suite_error.json", {"detail": small_suite_error})
            _write_json(output_dir / "api_run_response.json", run_payload)
            _write_json(output_dir / "result_detail.json", detail_payload)
            _write_json(
                output_dir / "optimizer_health_sweep.json",
                {
                    "tested_optimizer_count": len(optimizer_health_results),
                    "disabled_optimizer_count": len(MEALPY_DISABLED_OPTIMIZERS),
                    "disabled_optimizers": MEALPY_DISABLED_OPTIMIZERS,
                    "baseline_function": default_function,
                    "results": optimizer_health_results,
                },
            )
            _write_json(
                output_dir / "function_health_sweep.json",
                {
                    "tested_function_count": len(function_health_results),
                    "baseline_optimizer": default_optimizer,
                    "results": function_health_results,
                },
            )
            _download_assets(client, token, figure_assets, output_dir / "figures", expect_png=True)
            _download_assets(client, token, table_assets, output_dir / "tables", expect_png=False)

        report = {
            "status": "passed",
            "workspace_id": workspace_id,
            "catalog_summary": summary,
            "suite_requirements": requirements,
            "disabled_optimizers": MEALPY_DISABLED_OPTIMIZERS,
            "optimizer_health": {
                "tested": len(optimizer_health_results),
                "failed": len(optimizer_failures),
                "default_function": default_function,
            },
            "function_health": {
                "tested": len(function_health_results),
                "failed": len(function_failures),
                "default_optimizer": default_optimizer,
            },
            "small_suite_error": small_suite_error,
            "standard_suite": {
                "record_id": record_id,
                "task_count": summary_payload.get("task_count"),
                "success_count": summary_payload.get("success_count"),
                "failure_count": summary_payload.get("failure_count"),
                "figure_count": len(figure_assets),
                "table_count": len(table_assets),
            },
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
