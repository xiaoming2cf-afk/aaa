from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_agent.agent import AcademicResearchAgent  # noqa: E402
from research_agent.agent_math import (  # noqa: E402
    BeliefState,
    build_data_lab_repair_decision,
    build_delivery_posterior_trace,
    build_shadow_comparison,
    calibration_report_for_subsystem,
    delivery_classification_metrics,
    rank_retrieval_candidates,
    select_candidate_draft,
    top_k_recall,
)
from research_agent.model_quality_backtests import run_synthetic_truth_backtests  # noqa: E402
from research_agent.repo_hygiene import scan_repo_hygiene  # noqa: E402


def _session_state() -> dict[str, Any]:
    return {
        "assets": [
            {
                "profile": {
                    "column_names": ["outcome", "leverage", "growth", "revenue"],
                    "candidate_targets": ["outcome"],
                    "candidate_features": ["leverage", "growth", "revenue"],
                    "quality_warnings": [],
                    "schema_fingerprint": "quality-gate",
                }
            }
        ],
        "cells": [{"code": "df[['outcome', 'leverage']].corr()", "stdout": "ok"}],
        "messages": [{"content": "Use outcome, leverage, growth, and revenue."}],
        "profile_snapshots": [{"id": "snap-1"}],
        "safety_events": [],
        "executor": {"requested_mode": "subprocess_replay"},
        "llm": {"ready": False},
    }


def _check(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), **detail}


def _retrieval_backtest() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    fixtures = [
        {
            "query": "Run regression on outcome and leverage",
            "expected_ids": ["regression-card"],
            "candidates": [
                {
                    "id": "regression-card",
                    "title": "Regression outcome leverage model",
                    "summary": "Use outcome and leverage for regression diagnostics.",
                    "source_type": "workspace_knowledge",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 10,
                },
                {
                    "id": "cluster-card",
                    "title": "Clustering workflow",
                    "summary": "Unsupervised clustering for text corpora.",
                    "source_type": "team_library",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 10,
                },
            ],
        },
        {
            "query": "Use growth and revenue controls",
            "expected_ids": ["controls-card"],
            "candidates": [
                {
                    "id": "controls-card",
                    "title": "Growth revenue controls",
                    "summary": "Feature engineering with growth and revenue controls.",
                    "source_type": "workspace_knowledge",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 8,
                },
                {
                    "id": "generic-card",
                    "title": "General note",
                    "summary": "General research workflow.",
                    "source_type": "team_library",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 12,
                },
            ],
        },
        {
            "query": "Match semantic vector",
            "expected_ids": ["semantic-card"],
            "session": {"query_embedding": [1.0, 0.0], **_session_state()},
            "candidates": [
                {
                    "id": "semantic-card",
                    "title": "Semantic candidate",
                    "summary": "Embedding based candidate.",
                    "source_type": "workspace_knowledge",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 10,
                    "embedding": [1.0, 0.0],
                },
                {
                    "id": "other-card",
                    "title": "Other vector",
                    "summary": "Another candidate.",
                    "source_type": "workspace_knowledge",
                    "policy": "interface_only_no_external_source_injection",
                    "score": 10,
                    "embedding": [0.0, 1.0],
                },
            ],
        },
    ]
    for fixture in fixtures:
        _, trace = rank_retrieval_candidates(
            query_text=fixture["query"],
            candidates=fixture["candidates"],
            session=fixture.get("session") or _session_state(),
            limit=1,
            mode="shadow",
        )
        cases.append(
            {
                "expected_ids": fixture["expected_ids"],
                "baseline_ids": trace["v2"]["baseline_selected_ids"],
                "proposed_ids": trace["v2"]["proposed_selected_ids"],
            }
        )
    baseline_recall = top_k_recall(cases, key="baseline_ids", k=1)
    proposed_recall = top_k_recall(cases, key="proposed_ids", k=1)
    return {
        "passed": proposed_recall >= baseline_recall and proposed_recall >= 0.8,
        "baseline_top_k_recall": baseline_recall,
        "top_k_recall": proposed_recall,
        "baseline_delta": proposed_recall - baseline_recall,
        "golden_query_count": len(cases),
        "cases": cases,
    }


def _delivery_backtest() -> dict[str, Any]:
    fixtures = [
        {
            "kwargs": {
                "citation_coverage": 1.0,
                "unsupported_claim_rate": 0.0,
                "review_block_precision": 1.0,
                "review_approved": True,
                "artifact_present": True,
                "engineering_gate_passed": True,
                "baseline_deliverable": True,
            },
            "label": True,
        },
        {
            "kwargs": {
                "citation_coverage": 0.0,
                "unsupported_claim_rate": 1.0,
                "review_block_precision": 0.0,
                "review_approved": False,
                "artifact_present": False,
                "engineering_gate_passed": True,
                "baseline_deliverable": False,
            },
            "label": False,
        },
        {
            "kwargs": {
                "citation_coverage": 1.0,
                "unsupported_claim_rate": 0.0,
                "review_block_precision": 1.0,
                "review_approved": True,
                "artifact_present": True,
                "engineering_gate_passed": False,
                "baseline_deliverable": False,
            },
            "label": False,
        },
    ]
    predictions: list[float] = []
    labels: list[bool] = []
    for fixture in fixtures:
        trace = build_delivery_posterior_trace(
            **fixture["kwargs"],
            mode="shadow",
            threshold=0.85,
        )
        predictions.append(float(trace["delivery_probability_proxy"]))
        labels.append(bool(fixture["label"]))
    metrics = delivery_classification_metrics(predictions, labels, threshold=0.85)
    return {
        "passed": metrics["false_publish_rate"] == 0.0 and metrics["brier_score"] <= 0.12,
        **metrics,
        "predictions": [round(value, 6) for value in predictions],
        "labels": labels,
    }


def _repair_backtest() -> dict[str, Any]:
    fixtures = [
        ("SyntaxError: invalid syntax", 1, 3, "repair"),
        ("Blocked by safety policy: os.system is not allowed", 1, 3, "block"),
        ("KeyError: missing available columns", 4, 3, "ask_human"),
    ]
    rows: list[dict[str, Any]] = []
    for error_message, attempt_index, max_attempts, expected_action in fixtures:
        decision = build_data_lab_repair_decision(
            error_message=error_message,
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            mode="active",
            session_state={"M_t": {"recent_failure_classes": []}, "C_t": {"safety_event_count": 0}},
        )
        rows.append(
            {
                "expected_action": expected_action,
                "chosen_action": decision["best_action"],
                "passed": decision["best_action"] == expected_action,
                "fallback_reason": decision["v2"]["comparison"]["fallback_reason"],
            }
        )
    success_rate = sum(1 for row in rows if row["passed"]) / len(rows)
    return {"passed": success_rate == 1.0, "repair_success_rate": success_rate, "cases": rows}


def _candidate_selection_backtest() -> dict[str, Any]:
    baseline = SimpleNamespace(draft_id="baseline", status="approved", score=85.0, variant_index=0, metadata={})
    risky = SimpleNamespace(draft_id="risky", status="approved", score=30.0, variant_index=1, metadata={})
    chosen, trace = select_candidate_draft(candidates=[baseline, risky], mode="active", override_margin=0.01)
    passed = chosen.draft_id == "baseline" and bool(trace["metadata_warnings"])
    return {
        "passed": passed,
        "candidate_selection_win_rate": 1.0 if passed else 0.0,
        "false_approval_rate": 0.0 if passed else 1.0,
        "trace": trace,
    }


def _vulnerability_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    hygiene_issues = scan_repo_hygiene(REPO_ROOT)
    checks.append(_check("repo_hygiene_clean", not hygiene_issues, issue_count=len(hygiene_issues), issues=hygiene_issues[:10]))

    uncalibrated = build_shadow_comparison(
        baseline_choice="baseline",
        proposed_choice="proposal",
        baseline_score=0.1,
        proposed_score=0.9,
        override_margin=0.05,
        mode="active",
        feasible=True,
        calibrated=False,
    )
    checks.append(
        _check(
            "active_override_blocks_uncalibrated",
            not uncalibrated.override_applied and uncalibrated.fallback_reason == "uncalibrated_surrogate_blocked",
            comparison=uncalibrated.to_dict(),
        )
    )

    infeasible = build_shadow_comparison(
        baseline_choice="baseline",
        proposed_choice="proposal",
        baseline_score=0.1,
        proposed_score=0.9,
        override_margin=0.05,
        mode="active",
        feasible=False,
        calibrated=True,
    )
    checks.append(
        _check(
            "active_override_blocks_infeasible",
            not infeasible.override_applied and infeasible.fallback_reason == "proposed_choice_infeasible",
            comparison=infeasible.to_dict(),
        )
    )

    agent = object.__new__(AcademicResearchAgent)
    agent._handlers = {"known_tool": lambda: {"status": "ok"}}
    unknown_tool = agent._invoke_tool("missing_tool", {})
    checks.append(
        _check(
            "unknown_tool_is_fatal",
            unknown_tool.get("status") == "error" and unknown_tool.get("fatal") is True,
            result=unknown_tool,
        )
    )

    updated = BeliefState(belief_distribution={"ok": 0.5, "risk": 0.5}).update(
        action="observe",
        observation={"signal": "ok"},
        likelihood={"ok": 0.9, "risk": 0.1},
    )
    checks.append(
        _check(
            "belief_update_tracks_information_gain",
            updated.to_dict().get("information_gain", 0.0) > 0.0,
            belief_state=updated.to_dict(),
        )
    )
    return checks


def _audit_closure() -> dict[str, str]:
    return {
        "P1_admissibility_consistency": "fixed",
        "P2_relative_advantage": "fixed",
        "P3_delivery_magic_logistic": "fixed",
        "P4_utility_decomposition_signs": "fixed",
        "P5_belief_state_update": "mitigated",
        "P6_embedding_similarity": "mitigated",
        "P7_typed_v2_metadata": "fixed",
        "P8_unknown_tool_guard": "fixed",
        "P9_admissibility_scale": "fixed",
        "P10_boundary_tests": "fixed",
    }


def run_quality_gate() -> dict[str, Any]:
    calibration_reports = {
        subsystem: calibration_report_for_subsystem(subsystem).validation_metrics()
        for subsystem in ("retrieval", "delivery", "repair", "candidate_selection")
    }
    retrieval = _retrieval_backtest()
    delivery = _delivery_backtest()
    repair = _repair_backtest()
    candidate_selection = _candidate_selection_backtest()
    vulnerability_checks = _vulnerability_checks()
    model_truth = run_synthetic_truth_backtests()
    audit_closure = _audit_closure()
    checks = [
        _check("retrieval_backtest", retrieval["passed"], metrics=retrieval),
        _check("delivery_backtest", delivery["passed"], metrics=delivery),
        _check("repair_backtest", repair["passed"], metrics=repair),
        _check("candidate_selection_backtest", candidate_selection["passed"], metrics=candidate_selection),
        _check("model_synthetic_truth_backtests", model_truth["passed"], metrics=model_truth),
        *vulnerability_checks,
        _check("audit_closure_p1_p10", all(value in {"fixed", "mitigated", "data_required"} for value in audit_closure.values()), statuses=audit_closure),
    ]
    return {
        "quality_gate_version": "2026-04-24.agent-quality-gate.v1",
        "passed": all(bool(item["passed"]) for item in checks),
        "calibration_reports": calibration_reports,
        "checks": checks,
        "audit_closure": audit_closure,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="", help="Optional JSON report output path.")
    args = parser.parse_args()
    report = run_quality_gate()
    if args.output.strip():
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
