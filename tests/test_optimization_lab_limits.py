from __future__ import annotations

import json
import math
from typing import Any

from research_agent.optimization_lab import (
    MAX_ESTIMATED_EVALUATIONS,
    MAX_PARALLEL_TASKS,
    MEALPY_DISABLED_OPTIMIZERS,
    MIN_STANDARD_ALGORITHMS,
    MIN_STANDARD_FUNCTIONS,
    MIN_STANDARD_RUNS,
)


def _catalog(client, csrf_token: str) -> dict[str, Any]:
    response = client.get("/api/optimization/catalog", headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200, response.text
    return response.json()


def _available_names(catalog: dict[str, Any], key: str) -> list[str]:
    return [
        item["name"]
        for item in catalog[key]
        if (item.get("availability") or {}).get("status") == "available"
    ]


def _standard_payload(catalog: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    optimizers = _available_names(catalog, "optimizers")[:MIN_STANDARD_ALGORITHMS]
    functions = _available_names(catalog, "functions")[:MIN_STANDARD_FUNCTIONS]
    assert len(optimizers) == MIN_STANDARD_ALGORITHMS
    assert len(functions) == MIN_STANDARD_FUNCTIONS
    payload = {
        "suite_label": "Targeted Optimization Suite",
        "optimizer_names": optimizers,
        "function_names": functions,
        "dimension": 5,
        "epoch": 4,
        "pop_size": 8,
        "runs": MIN_STANDARD_RUNS,
        "workers": 1,
        "seed_base": 20260511,
    }
    payload.update(overrides)
    return payload


def _run_suite(client, workspace_id: str, csrf_token: str, payload: dict[str, Any]):
    return client.post(
        f"/api/workspaces/{workspace_id}/optimization/run",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )


def _run_suite_raw_json(client, workspace_id: str, csrf_token: str, payload: dict[str, Any]):
    return client.post(
        f"/api/workspaces/{workspace_id}/optimization/run",
        headers={"X-CSRF-Token": csrf_token, "Content-Type": "application/json"},
        content=json.dumps(payload, allow_nan=True),
    )


def _assert_rejected(response, *expected_fragments: str) -> str:
    assert response.status_code in {400, 422}, response.text
    detail = response.json().get("detail", response.text)
    detail_text = str(detail).lower()
    for fragment in expected_fragments:
        assert fragment.lower() in detail_text
    return detail_text


def _assert_finite_tree(value: Any) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        assert math.isfinite(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _assert_finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite_tree(item)


def test_optimization_suite_minimums_and_resource_caps_fail_before_launch(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    base = _standard_payload(catalog)

    too_small = {
        **base,
        "optimizer_names": base["optimizer_names"][: MIN_STANDARD_ALGORITHMS - 1],
        "function_names": base["function_names"][: MIN_STANDARD_FUNCTIONS - 1],
        "runs": MIN_STANDARD_RUNS - 1,
    }
    _assert_rejected(_run_suite(client, workspace_id, csrf_token, too_small), "at least")

    optimizer_count_for_task_cap = (MAX_PARALLEL_TASKS // (MIN_STANDARD_FUNCTIONS * MIN_STANDARD_RUNS)) + 1
    too_many_tasks = {
        **base,
        "optimizer_names": _available_names(catalog, "optimizers")[:optimizer_count_for_task_cap],
        "function_names": base["function_names"],
        "runs": MIN_STANDARD_RUNS,
    }
    assert len(too_many_tasks["optimizer_names"]) == optimizer_count_for_task_cap
    _assert_rejected(_run_suite(client, workspace_id, csrf_token, too_many_tasks), "tasks")

    eval_cap_pop_size = (MAX_ESTIMATED_EVALUATIONS // (MIN_STANDARD_ALGORITHMS * MIN_STANDARD_FUNCTIONS * MIN_STANDARD_RUNS * 1000)) + 1
    too_many_evaluations = {
        **base,
        "epoch": 1000,
        "pop_size": eval_cap_pop_size,
    }
    _assert_rejected(_run_suite(client, workspace_id, csrf_token, too_many_evaluations), "evaluations")


def test_optimization_numeric_inputs_reject_nonfinite_and_out_of_bounds(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    base = _standard_payload(catalog)

    for field_name, value, expected in [
        ("dimension", 0, "dimension"),
        ("dimension", 101, "dimension"),
        ("epoch", 0, "epoch"),
        ("epoch", 1001, "epoch"),
        ("pop_size", 1, "pop_size"),
        ("pop_size", 501, "pop_size"),
        ("runs", 0, "runs"),
        ("runs", 51, "runs"),
        ("workers", -1, "workers"),
        ("workers", 17, "workers"),
        ("dimension", float("nan"), "finite"),
        ("epoch", float("inf"), "finite"),
        ("pop_size", 3.5, "integer"),
    ]:
        payload = {**base, field_name: value}
        runner = _run_suite_raw_json if isinstance(value, float) and not math.isfinite(value) else _run_suite
        _assert_rejected(runner(client, workspace_id, csrf_token, payload), expected)


def test_optimization_unknown_and_disabled_catalog_items_are_not_silent(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    base = _standard_payload(catalog)

    unknown_optimizer = {
        **base,
        "optimizer_names": [*base["optimizer_names"][:-1], "mealpy.missing.Nope"],
    }
    _assert_rejected(_run_suite(client, workspace_id, csrf_token, unknown_optimizer), "unknown", "algorithms")

    unknown_function = {
        **base,
        "function_names": [*base["function_names"][:-1], "MissingBenchmarkFunction"],
    }
    _assert_rejected(_run_suite(client, workspace_id, csrf_token, unknown_function), "unknown", "benchmark")

    disabled_name = next(iter(MEALPY_DISABLED_OPTIMIZERS))
    disabled_optimizer = {
        **base,
        "optimizer_names": [disabled_name, *base["optimizer_names"][1:]],
    }
    disabled_detail = _assert_rejected(
        _run_suite(client, workspace_id, csrf_token, disabled_optimizer),
        "unavailable",
        disabled_name,
    )
    assert MEALPY_DISABLED_OPTIMIZERS[disabled_name].split(":", 1)[0].lower()[:20] in disabled_detail


def test_standard_optimization_suite_outputs_are_complete_and_finite(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    payload = _standard_payload(catalog)

    response = _run_suite(client, workspace_id, csrf_token, payload)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    summary = result["summary"]

    assert summary["algorithm_count"] == MIN_STANDARD_ALGORITHMS
    assert summary["function_count"] == MIN_STANDARD_FUNCTIONS
    assert summary["run_count"] == MIN_STANDARD_RUNS
    assert summary["task_count"] == MIN_STANDARD_ALGORITHMS * MIN_STANDARD_FUNCTIONS * MIN_STANDARD_RUNS
    assert summary["success_count"] == summary["task_count"]
    assert summary["failure_count"] == 0
    assert summary["estimated_evaluations"] <= MAX_ESTIMATED_EVALUATIONS

    assert result["ranking_preview"]
    assert result["friedman_preview"]
    assert result["raw_curve_rows"]
    assert result["raw_run_rows"]
    assert result["artifacts"]["figures"]
    assert result["artifacts"]["tables"]
    assert all((asset.get("metadata") or {}).get("kind") != "image_svg" for asset in result["artifacts"]["figures"])

    _assert_finite_tree(result["ranking_preview"])
    _assert_finite_tree(result["friedman_preview"])
    _assert_finite_tree(result["raw_curve_rows"][:50])
    _assert_finite_tree(result["raw_run_rows"])
