from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research_agent import optimization_lab as opt


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
    payload = {
        "suite_label": "Correctness Optimization Suite",
        "optimizer_names": _available_names(catalog, "optimizers")[: opt.MIN_STANDARD_ALGORITHMS],
        "function_names": _available_names(catalog, "functions")[: opt.MIN_STANDARD_FUNCTIONS],
        "dimension": 5,
        "epoch": 4,
        "pop_size": 8,
        "runs": opt.MIN_STANDARD_RUNS,
        "workers": 1,
        "seed_base": 20260512,
    }
    assert len(payload["optimizer_names"]) == opt.MIN_STANDARD_ALGORITHMS
    assert len(payload["function_names"]) == opt.MIN_STANDARD_FUNCTIONS
    payload.update(overrides)
    return payload


def _post_suite(client, workspace_id: str, csrf_token: str, payload: dict[str, Any]):
    return client.post(
        f"/api/workspaces/{workspace_id}/optimization/run",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )


def _assert_finite_tree(value: Any) -> None:
    if value is None or isinstance(value, (str, bytes, bool)):
        return
    if isinstance(value, (int, float)):
        assert math.isfinite(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _assert_finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite_tree(item)


def test_optimization_suite_rejects_partial_matrix_failures(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    payload = _standard_payload(catalog)
    failed_key = (payload["optimizer_names"][0], payload["function_names"][0], 1)

    def fake_task(task: dict[str, Any]) -> dict[str, Any]:
        key = (task["optimizer_name"], task["function_name"], task["run_index"])
        if key == failed_key:
            return {
                **task,
                "status": "error",
                "error": "synthetic task failure",
                "curve": [],
                "curve_length": 0,
                "resolved_dimension": task["dimension"],
                "requested_dimension": task["dimension"],
                "optimizer_kwargs": {},
                "function_info": {"name": task["function_name"], "dimension": task["dimension"]},
            }
        return {
            **task,
            "status": "ok",
            "best_fitness": 1.0,
            "best_solution": [0.0] * int(task["dimension"]),
            "curve": [2.0, 1.0],
            "curve_length": 2,
            "resolved_dimension": task["dimension"],
            "requested_dimension": task["dimension"],
            "optimizer_kwargs": {"epoch": task["epoch"], "pop_size": task["pop_size"], "seed": task["seed"]},
            "function_info": {"name": task["function_name"], "dimension": task["dimension"]},
        }

    monkeypatch.setattr(opt, "_run_single_optimization_task", fake_task)
    response = _post_suite(client, workspace_id, csrf_token, payload)
    assert response.status_code == 400, response.text
    detail = response.json()["detail"].lower()
    assert "every algorithm-function-run task" in detail
    assert "synthetic task failure" in detail

    history = client.get(
        f"/api/workspaces/{workspace_id}/optimization/results",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"] == []


def test_effective_resource_caps_include_optimizer_minimum_overrides(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    catalog = _catalog(client, csrf_token)
    payload = _standard_payload(catalog, epoch=1000, pop_size=185)
    monkeypatch.setitem(opt.MEALPY_MIN_POP_SIZE, payload["optimizer_names"][0], opt.MAX_OPTIMIZATION_POP_SIZE)

    response = _post_suite(client, workspace_id, csrf_token, payload)
    assert response.status_code == 400, response.text
    detail = response.json()["detail"].lower()
    assert "evaluations" in detail
    assert f"{opt.MAX_ESTIMATED_EVALUATIONS:,}" in detail


def test_statistical_outputs_remain_finite_for_tied_scores():
    score_frame = pd.DataFrame(
        [
            {"optimizer_name": optimizer, "function_name": function, "mean_fitness": 1.0}
            for optimizer in ["alg-a", "alg-b", "alg-c"]
            for function in ["fn-a", "fn-b", "fn-c"]
        ]
    )

    ranking_frame, friedman_summary = opt._rank_table(score_frame)
    wilcoxon_frame, sign_frame = opt._pairwise_tests(score_frame)

    _assert_finite_tree(ranking_frame.to_dict(orient="records"))
    _assert_finite_tree(friedman_summary)
    _assert_finite_tree(wilcoxon_frame.to_dict(orient="records"))
    _assert_finite_tree(sign_frame.to_dict(orient="records"))
    assert friedman_summary["statistic"] == 0.0
    assert friedman_summary["pvalue"] == 1.0
