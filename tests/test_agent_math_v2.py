from __future__ import annotations

import math
from types import SimpleNamespace

from research_agent.agent import AcademicResearchAgent
from research_agent.agent_math import (
    BeliefState,
    build_shadow_comparison,
    build_data_lab_repair_decision,
    build_delivery_posterior_trace,
    rank_retrieval_candidates,
    select_candidate_draft,
)


def _session_state() -> dict[str, object]:
    return {
        "assets": [
            {
                "profile": {
                    "column_names": ["y", "x", "group"],
                    "candidate_targets": ["y"],
                    "candidate_features": ["x"],
                    "quality_warnings": ["Column x has potential numeric outliers."],
                    "schema_fingerprint": "abc123",
                }
            }
        ],
        "cells": [{"code": "print(df[['y', 'x']].corr())", "stdout": "ok"}],
        "messages": [{"content": "Use y and x for analysis."}],
        "profile_snapshots": [{"id": "snap-1"}],
        "safety_events": [],
        "executor": {"requested_mode": "subprocess_replay"},
        "llm": {"ready": False},
        "math": {
            "internal_v2_state": {
                "M_t": {
                    "successful_cell_count": 1,
                    "recent_failure_classes": ["schema"],
                },
                "C_t": {"safety_event_count": 0},
            }
        },
    }


def test_retrieval_v2_posterior_normalizes_and_shadow_preserves_baseline():
    candidates = [
        {
            "id": "card-1",
            "title": "Regression quickstart",
            "summary": "Use y and x columns for linear regression diagnostics.",
            "source_type": "workspace_knowledge",
            "policy": "interface_only_no_external_source_injection",
            "score": 10,
        },
        {
            "id": "card-2",
            "title": "Clustering note",
            "summary": "Unsupervised clustering for text corpora.",
            "source_type": "team_library",
            "policy": "interface_only_no_external_source_injection",
            "score": 5,
        },
    ]

    ranked, trace = rank_retrieval_candidates(
        query_text="Run regression on y and x",
        candidates=candidates,
        session=_session_state(),
        limit=1,
        mode="shadow",
        override_margin=0.05,
    )

    posteriors = [float(item["posterior"]) for item in trace["v2"]["candidates"]]
    assert ranked[0]["id"] == "card-1"
    assert math.isclose(sum(posteriors), 1.0, rel_tol=1e-6, abs_tol=1e-6)
    assert trace["v2"]["comparison"]["fallback_reason"] == "shadow_mode_preserves_baseline"
    assert trace["v2"]["chosen_selected_ids"] == trace["v2"]["baseline_selected_ids"]


def test_active_retrieval_uncalibrated_surrogate_cannot_override_baseline():
    session = _session_state()
    session["assets"][0]["profile"]["column_names"] = ["outcome", "leverage", "growth", "revenue"]
    session["assets"][0]["profile"]["candidate_targets"] = ["outcome"]
    session["assets"][0]["profile"]["candidate_features"] = ["leverage", "growth", "revenue"]
    candidates = [
        {
            "id": "baseline-card",
            "title": "Run report",
            "summary": "General report workflow.",
            "source_type": "workspace_knowledge",
            "policy": "interface_only_no_external_source_injection",
            "score": 10,
        },
        {
            "id": "profile-card",
            "title": "Outcome leverage growth revenue model",
            "summary": "Use outcome with leverage, growth, and revenue features.",
            "source_type": "workspace_knowledge",
            "policy": "interface_only_no_external_source_injection",
            "score": 10,
        },
    ]

    ranked, trace = rank_retrieval_candidates(
        query_text="Run report",
        candidates=candidates,
        session=session,
        limit=1,
        mode="active",
        override_margin=0.01,
    )

    assert trace["v2"]["proposed_selected_ids"][0] == "profile-card"
    assert trace["v2"]["baseline_selected_ids"][0] == "baseline-card"
    assert ranked[0]["id"] == "baseline-card"
    assert trace["v2"]["comparison"]["fallback_reason"] == "uncalibrated_surrogate_blocked"
    assert trace["math_status"]["calibrated"] is False


def test_retrieval_admissibility_is_consistent_between_baseline_and_v2():
    candidates = [
        {
            "id": "soft-card",
            "title": "General regression note",
            "summary": "Regression note",
            "source_type": "workspace_knowledge",
            "policy": "legacy_policy",
            "score": 10,
        }
    ]

    ranked, trace = rank_retrieval_candidates(
        query_text="regression",
        candidates=candidates,
        session=_session_state(),
        limit=5,
        mode="shadow",
    )

    assert ranked[0]["arbiter"]["admissibility"] == 0.7
    assert trace["v2"]["candidates"][0]["admissibility"] == 0.7
    assert trace["v2"]["candidates"][0]["feasible"] is True


def test_retrieval_handles_empty_candidates_and_large_limit():
    ranked, trace = rank_retrieval_candidates(
        query_text="anything",
        candidates=[],
        session=_session_state(),
        limit=20,
        mode="shadow",
    )

    assert ranked == []
    assert trace["selected_count"] == 0
    assert trace["v2"]["posterior_mass_top_k"] == 0.0


def test_retrieval_uses_optional_embedding_similarity_when_available():
    candidates = [
        {
            "id": "baseline-card",
            "title": "Run report",
            "summary": "General report workflow.",
            "source_type": "workspace_knowledge",
            "policy": "interface_only_no_external_source_injection",
            "score": 10,
            "embedding": [0.0, 1.0],
        },
        {
            "id": "semantic-card",
            "title": "Different words",
            "summary": "No direct overlap here.",
            "source_type": "workspace_knowledge",
            "policy": "interface_only_no_external_source_injection",
            "score": 10,
            "embedding": [1.0, 0.0],
        },
    ]
    session = _session_state()
    session["query_embedding"] = [1.0, 0.0]

    _, trace = rank_retrieval_candidates(
        query_text="Run report",
        candidates=candidates,
        session=session,
        limit=1,
        mode="shadow",
    )

    semantic = next(item for item in trace["v2"]["candidates"] if item["candidate_id"] == "semantic-card")
    baseline = next(item for item in trace["v2"]["candidates"] if item["candidate_id"] == "baseline-card")
    assert semantic["semantic_similarity"] == 1.0
    assert baseline["semantic_similarity"] == 0.5


def test_shadow_comparison_reports_normalized_advantage():
    comparison = build_shadow_comparison(
        baseline_choice="baseline",
        proposed_choice="proposed",
        baseline_score=0.001,
        proposed_score=0.006,
        override_margin=0.05,
        mode="active",
        calibrated=True,
    )

    payload = comparison.to_dict()
    assert comparison.override_applied is True
    assert math.isclose(payload["advantage"], 0.833333, rel_tol=1e-6)
    assert payload["raw_advantage"] == 0.005
    assert payload["advantage_semantics"] == "relative_to_max_abs_score"


def test_belief_state_update_normalizes_and_tracks_entropy():
    state = BeliefState(belief_distribution={"ok": 0.5, "risky": 0.5})
    updated = state.update(
        action="review",
        observation={"finding": "low risk"},
        transition={
            "ok": {"ok": 0.9, "risky": 0.1},
            "risky": {"ok": 0.3, "risky": 0.7},
        },
        likelihood={"ok": 0.8, "risky": 0.2},
    )

    distribution = updated.normalized_distribution()
    assert math.isclose(sum(distribution.values()), 1.0, abs_tol=1e-9)
    assert distribution["ok"] > distribution["risky"]
    assert updated.to_dict()["belief_entropy"] > 0.0


def test_control_v2_feasibility_blocks_auto_repair_for_safety_errors():
    decision = build_data_lab_repair_decision(
        error_message="Blocked by safety policy: os.system is not allowed",
        attempt_index=1,
        max_attempts=3,
        mode="active",
        human_threshold=0.55,
        override_margin=0.05,
        session_state={
            "M_t": {"recent_failure_classes": ["safety"], "successful_cell_count": 1},
            "C_t": {"safety_event_count": 1},
            "E_t": {"profile_snapshot_count": 1},
        },
    )

    assert decision["best_action"] == "block"
    assert decision["best_family"] == "A_terminal"
    assert decision["v2"]["feasibility"]["A_auto"]["feasible"] is False
    assert decision["v2"]["comparison"]["chosen_choice"] == "block"


def test_active_repair_uncalibrated_surrogate_cannot_stop_baseline_repair():
    decision = build_data_lab_repair_decision(
        error_message="SyntaxError: invalid syntax",
        attempt_index=1,
        max_attempts=3,
        mode="active",
        human_threshold=0.55,
        override_margin=0.01,
        session_state={"M_t": {"recent_failure_classes": ["syntax"]}},
    )

    assert decision["v2"]["proposed_action"] == "ask_human"
    assert decision["best_action"] == "repair"
    assert decision["v2"]["comparison"]["fallback_reason"] == "uncalibrated_surrogate_blocked"
    assert decision["math_status"]["calibrated"] is False


def test_delivery_v2_never_overrides_a_blocked_baseline_gate():
    trace = build_delivery_posterior_trace(
        citation_coverage=1.0,
        unsupported_claim_rate=0.0,
        review_block_precision=1.0,
        review_approved=True,
        artifact_present=True,
        engineering_gate_passed=True,
        baseline_deliverable=False,
        mode="active",
        threshold=0.5,
        override_margin=0.05,
    )

    assert trace["v2"]["proposed_deliverable"] is True
    assert trace["deliverable_proxy"] is False
    assert trace["v2"]["comparison"]["fallback_reason"] == "active_never_bypasses_baseline_gate"


def test_active_delivery_uncalibrated_surrogate_cannot_block_baseline_delivery():
    trace = build_delivery_posterior_trace(
        citation_coverage=0.0,
        unsupported_claim_rate=1.0,
        review_block_precision=0.0,
        review_approved=False,
        artifact_present=False,
        engineering_gate_passed=True,
        baseline_deliverable=True,
        mode="active",
        threshold=0.95,
        override_margin=0.01,
    )

    assert trace["v2"]["proposed_deliverable"] is False
    assert trace["deliverable_proxy"] is True
    assert trace["v2"]["comparison"]["fallback_reason"] == "uncalibrated_surrogate_blocked"
    assert trace["math_status"]["validation_metrics"]["brier_score"] is None


def test_delivery_empty_evidence_proxy_is_zero_when_gate_passes():
    trace = build_delivery_posterior_trace(
        citation_coverage=0.0,
        unsupported_claim_rate=1.0,
        review_block_precision=0.0,
        review_approved=False,
        artifact_present=False,
        engineering_gate_passed=True,
        baseline_deliverable=False,
        mode="shadow",
        threshold=0.5,
    )

    assert trace["delivery_probability_proxy"] == 0.0
    assert trace["deliverable_proxy"] is False
    assert trace["surrogate"] == "zero_safe_weighted_delivery_evidence_proxy"


def test_candidate_selection_records_missing_v2_metadata_without_overriding_baseline():
    baseline = SimpleNamespace(
        draft_id="baseline",
        status="approved",
        score=80.0,
        variant_index=0,
        metadata={},
    )
    candidate = SimpleNamespace(
        draft_id="candidate",
        status="approved",
        score=20.0,
        variant_index=1,
        metadata={},
    )

    chosen, trace = select_candidate_draft(
        candidates=[baseline, candidate],
        mode="active",
        override_margin=0.01,
    )

    assert chosen.draft_id == "baseline"
    assert trace["metadata_warnings"]["baseline"] == "missing_metadata_arbiter"
    assert trace["comparison"]["fallback_reason"] == "proposed_choice_matches_baseline"


def test_unknown_agent_tool_is_fatal_and_lists_available_tools():
    agent = object.__new__(AcademicResearchAgent)
    agent._handlers = {"known_tool": lambda: {"status": "ok"}}

    result = agent._invoke_tool("missing_tool", {})

    assert result["status"] == "error"
    assert result["fatal"] is True
    assert result["available_tools"] == ["known_tool"]
