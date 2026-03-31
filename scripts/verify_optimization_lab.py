from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from verify_data_lab import (  # noqa: E402
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


def _run_tasks(tasks: list[dict[str, Any]], max_workers: int = 12) -> list[dict[str, Any]]:
    from research_agent.optimization_lab import _run_single_optimization_task

    results: list[dict[str, Any]] = []
    if not tasks:
        return results
    worker_count = min(max_workers, len(tasks))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_run_single_optimization_task, task) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (item["optimizer_name"], item["function_name"], item["run_index"]))
    return results


def run_verification(output_dir: Path | None = None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-optimization-lab-verify-"))
    configure_test_environment(temp_root)

    from research_agent.optimization_lab import (
        DEFAULT_FUNCTIONS,
        DEFAULT_OPTIMIZERS,
        MEALPY_DISABLED_OPTIMIZERS,
        get_optimization_catalog,
    )
    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)

        public_host_headers = {"host": "economic-research-web.onrender.com"}
        page_checks: dict[str, Any] = {}
        for route, slug in [
            ("/optimization-lab", "optimization_lab"),
            ("/data-lab", "data_lab"),
            ("/public-monitor", "public_monitor"),
            ("/", "home"),
        ]:
            response = client.get(route, headers=public_host_headers)
            response.raise_for_status()
            html = response.text
            page_checks[route] = {
                "status_code": response.status_code,
                "has_platform_navigation": "Platform Navigation" in html,
                "has_access_gate": "data-access-gate" in html,
            }
            if output_dir:
                _write_text(output_dir / "pages" / f"{slug}.html", html)

        remote_gate_status: dict[str, int] = {}
        for route in [
            "/api/data-lab/catalog",
            "/api/optimization/catalog",
            "/api/public/briefings/latest",
            "/api/openalex/search?q=macro&max_results=1",
        ]:
            response = client.get(route, headers=public_host_headers)
            remote_gate_status[route] = response.status_code
            if response.status_code != 401:
                raise AssertionError(f"Remote gate should reject {route}, got {response.status_code}")

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Optimization Reviewer", "email": "optimizer@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Optimization Verification")

        catalog_response = client.get("/api/optimization/catalog")
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
        if catalog["summary"]["optimizer_count"] < 200:
            raise AssertionError("Optimization catalog did not expose the full Mealpy optimizer set")
        if catalog["summary"]["function_count"] < 300:
            raise AssertionError("Optimization catalog did not expose the full Opfunu benchmark set")
        if not catalog["defaults"]["optimizers"] or not catalog["defaults"]["functions"]:
            raise AssertionError("Optimization catalog defaults are incomplete")
        if output_dir:
            _write_json(output_dir / "catalog_summary.json", catalog)

        available_optimizers = [item["name"] for item in catalog["optimizers"] if item["availability"]["status"] == "available"]
        available_functions = [item["name"] for item in catalog["functions"] if item["availability"]["status"] == "available"]

        optimizer_health_tasks = [
            {
                "optimizer_name": optimizer_name,
                "function_name": DEFAULT_FUNCTIONS[0],
                "run_index": 1,
                "seed": 100_000 + index,
                "epoch": 5,
                "pop_size": 12,
                "dimension": 30,
            }
            for index, optimizer_name in enumerate(available_optimizers, start=1)
        ]
        optimizer_health_results = _run_tasks(optimizer_health_tasks, max_workers=12)
        optimizer_failures = [item for item in optimizer_health_results if item["status"] != "ok"]
        if optimizer_failures:
            raise AssertionError(
                f"{len(optimizer_failures)} available optimizers still fail the smoke solve: "
                + "; ".join(f"{item['optimizer_name']} => {item.get('error', 'unknown error')}" for item in optimizer_failures[:10])
            )

        function_health_tasks = [
            {
                "optimizer_name": DEFAULT_OPTIMIZERS[0],
                "function_name": function_name,
                "run_index": 1,
                "seed": 200_000 + index,
                "epoch": 5,
                "pop_size": 20,
                "dimension": 30,
            }
            for index, function_name in enumerate(available_functions, start=1)
        ]
        function_health_results = _run_tasks(function_health_tasks, max_workers=12)
        function_failures = [item for item in function_health_results if item["status"] != "ok"]
        if function_failures:
            raise AssertionError(
                f"{len(function_failures)} available benchmark functions still fail the smoke solve: "
                + "; ".join(f"{item['function_name']} => {item.get('error', 'unknown error')}" for item in function_failures[:10])
            )

        if output_dir:
            _write_json(
                output_dir / "optimizer_health_sweep.json",
                {
                    "tested_optimizer_count": len(optimizer_health_results),
                    "disabled_optimizer_count": len(MEALPY_DISABLED_OPTIMIZERS),
                    "disabled_optimizers": MEALPY_DISABLED_OPTIMIZERS,
                    "results": optimizer_health_results,
                },
            )
            _write_json(
                output_dir / "function_health_sweep.json",
                {
                    "tested_function_count": len(function_health_results),
                    "results": function_health_results,
                },
            )

        suite_payload = {
            "suite_label": "Monte Carlo Optimization Suite",
            "optimizer_names": DEFAULT_OPTIMIZERS,
            "function_names": DEFAULT_FUNCTIONS,
            "dimension": 30,
            "epoch": 8,
            "pop_size": 20,
            "runs": 2,
            "workers": 4,
        }
        run_response = client.post(
            f"/api/workspaces/{workspace_id}/optimization/run",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json=suite_payload,
        )
        run_response.raise_for_status()
        run_payload = run_response.json()
        record_id = run_payload["record"]["id"]
        detail_response = client.get(f"/api/optimization/results/{record_id}", headers=auth_headers(token))
        detail_response.raise_for_status()
        detail_payload = detail_response.json()

        result = detail_payload["result"]
        artifacts = result.get("artifacts", {})
        figure_assets = artifacts.get("figures", [])
        table_assets = artifacts.get("tables", [])
        if len(figure_assets) < 3:
            raise AssertionError("Optimization suite did not generate the expected figure exports")
        if len(table_assets) < 6:
            raise AssertionError("Optimization suite did not generate the expected table exports")
        if not result.get("ranking_preview"):
            raise AssertionError("Optimization result is missing the ranking preview")
        if not result.get("summary", {}).get("friedman"):
            raise AssertionError("Optimization result is missing the Friedman summary")

        if output_dir:
            _write_json(output_dir / "api_run_response.json", run_payload)
            _write_json(output_dir / "result_detail.json", detail_payload)

        for index, asset in enumerate(figure_assets, start=1):
            download = client.get(f"/api/assets/{asset['id']}/download", headers=auth_headers(token))
            assert_png_response(download, f"optimization figure {index}")
            if output_dir:
                filename = asset.get("filename") or f"figure-{index}.png"
                (output_dir / "figures").mkdir(parents=True, exist_ok=True)
                (output_dir / "figures" / filename).write_bytes(download.content)

        for index, asset in enumerate(table_assets, start=1):
            download = client.get(f"/api/assets/{asset['id']}/download", headers=auth_headers(token))
            download.raise_for_status()
            if output_dir:
                filename = asset.get("filename") or f"table-{index}.csv"
                (output_dir / "tables").mkdir(parents=True, exist_ok=True)
                (output_dir / "tables" / filename).write_bytes(download.content)

        result_page = client.get(f"/optimization-lab/results/{record_id}")
        result_page.raise_for_status()
        if output_dir:
            _write_text(output_dir / "pages" / "optimization_result.html", result_page.text)

        report = {
            "status": "passed",
            "workspace_id": workspace_id,
            "catalog_summary": catalog["summary"],
            "disabled_optimizers": MEALPY_DISABLED_OPTIMIZERS,
            "page_checks": page_checks,
            "remote_gate_status": remote_gate_status,
            "optimizer_health": {
                "tested": len(optimizer_health_results),
                "passed": len(optimizer_health_results) - len(optimizer_failures),
                "failed": len(optimizer_failures),
                "default_function": DEFAULT_FUNCTIONS[0],
            },
            "function_health": {
                "tested": len(function_health_results),
                "passed": len(function_health_results) - len(function_failures),
                "failed": len(function_failures),
                "default_optimizer": DEFAULT_OPTIMIZERS[0],
            },
            "suite_run": {
                "record_id": record_id,
                "suite_label": result.get("suite_label"),
                "summary": result.get("summary", {}),
                "figure_count": len(figure_assets),
                "table_count": len(table_assets),
                "ranking_preview_head": result.get("ranking_preview", [])[:5],
                "failure_rows": result.get("failures", [])[:10],
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
