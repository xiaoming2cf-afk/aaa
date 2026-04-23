from __future__ import annotations

from typing import Any

from .runtime import BeliefState, DecisionTrace, FeasibilityMask, build_shadow_comparison, clamp_unit


def _error_class(error_message: str) -> str:
    lowered = (error_message or "").lower()
    if any(token in lowered for token in ("not allowed", "safety", "blocked by")):
        return "safety"
    if any(token in lowered for token in ("syntaxerror", "unexpected eof", "invalid syntax")):
        return "syntax"
    if any(token in lowered for token in ("keyerror", "nameerror", "attributeerror", "missing", "available columns")):
        return "schema"
    return "runtime"


def build_data_lab_repair_decision(
    *,
    error_message: str,
    attempt_index: int,
    max_attempts: int,
    mode: str,
    has_human_code: bool = False,
    human_threshold: float = 0.55,
    override_margin: float = 0.05,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cls = _error_class(error_message)
    progress_ratio = 1.0 if max_attempts <= 0 else min(max(float(attempt_index) / float(max_attempts), 0.0), 1.0)
    baseline_scores = {
        "A_auto": round(max(0.0, {"syntax": 0.62, "schema": 0.57, "runtime": 0.44, "safety": 0.02}.get(cls, 0.4) - 0.32 * progress_ratio), 6),
        "A_intervene": round(min(1.0, 0.28 + 0.42 * progress_ratio + (0.18 if has_human_code else 0.0) + (0.1 if cls in {"syntax", "runtime"} else 0.0)), 6),
        "A_terminal": round(0.96 if cls == "safety" else (0.18 if progress_ratio < 1.0 else 0.38), 6),
    }
    baseline_family = max(baseline_scores, key=baseline_scores.get)
    baseline_action = {
        "A_auto": "repair",
        "A_intervene": "ask_human",
        "A_terminal": "block",
    }[baseline_family]

    state = dict(session_state or {})
    memory_state = dict(state.get("M_t") or {})
    constraint_state = dict(state.get("C_t") or {})
    evaluation_state = dict(state.get("E_t") or {})
    recent_failure_classes = [str(item) for item in memory_state.get("recent_failure_classes") or []]
    repeated_failures = recent_failure_classes.count(cls)
    successful_cells = int(memory_state.get("successful_cell_count") or 0)
    human_interventions = int(memory_state.get("human_intervention_count") or 0)
    safety_events = int(constraint_state.get("safety_event_count") or 0)
    profile_snapshots = int(evaluation_state.get("profile_snapshot_count") or 0)

    belief_state = BeliefState(
        W_t={
            "error_class": cls,
            "attempt_index": int(attempt_index),
            "max_attempts": int(max_attempts),
            "has_human_code": bool(has_human_code),
        },
        M_t={
            "recent_failure_classes": recent_failure_classes[-6:],
            "repeated_failures": repeated_failures,
            "successful_cell_count": successful_cells,
            "human_intervention_count": human_interventions,
        },
        C_t={
            "safety_event_count": safety_events,
            "profile_snapshot_count": profile_snapshots,
        },
        E_t={
            "progress_ratio": round(progress_ratio, 6),
        },
    )

    feasibility = {
        "A_auto": FeasibilityMask(
            action_family="A_auto",
            feasible=cls != "safety" and attempt_index <= max_attempts,
            reason="safety_error" if cls == "safety" else ("attempt_budget_exhausted" if attempt_index > max_attempts else ""),
        ),
        "A_intervene": FeasibilityMask(
            action_family="A_intervene",
            feasible=True,
            reason="",
        ),
        "A_terminal": FeasibilityMask(
            action_family="A_terminal",
            feasible=True,
            reason="",
        ),
    }

    proposed_scores = {
        "A_auto": round(
            clamp_unit(
                {"syntax": 0.64, "schema": 0.59, "runtime": 0.46, "safety": 0.01}.get(cls, 0.42)
                + 0.05 * min(successful_cells, 4) / 4.0
                - 0.11 * repeated_failures
                - 0.29 * progress_ratio
                - 0.08 * safety_events
            ),
            6,
        ),
        "A_intervene": round(
            clamp_unit(
                max(float(human_threshold), 0.32)
                + 0.2 * progress_ratio
                + (0.15 if cls in {"syntax", "runtime"} else 0.05)
                + 0.08 * repeated_failures
                + 0.08 * human_interventions
                + (0.14 if has_human_code else 0.0)
            ),
            6,
        ),
        "A_terminal": round(
            clamp_unit(
                1.0
                if cls == "safety"
                else 0.12
                + (0.24 if attempt_index >= max_attempts else 0.0)
                + 0.09 * repeated_failures
                + 0.08 * safety_events
            ),
            6,
        ),
    }
    feasible_scores = {
        key: (value if feasibility[key].feasible else -1.0)
        for key, value in proposed_scores.items()
    }
    proposed_family = max(feasible_scores, key=feasible_scores.get)
    proposed_action = {
        "A_auto": "repair",
        "A_intervene": "ask_human",
        "A_terminal": "block",
    }[proposed_family]

    comparison = build_shadow_comparison(
        baseline_choice=baseline_action,
        proposed_choice=proposed_action,
        baseline_score=baseline_scores[baseline_family],
        proposed_score=proposed_scores[proposed_family],
        override_margin=float(override_margin),
        mode=mode,
        feasible=feasibility[proposed_family].feasible,
    )
    chosen_action = comparison.chosen_choice
    chosen_family = {
        "repair": "A_auto",
        "ask_human": "A_intervene",
        "block": "A_terminal",
    }[chosen_action]
    chosen_scores = proposed_scores if comparison.override_applied else baseline_scores

    v2_trace = DecisionTrace(
        mode=mode,
        belief_state=belief_state,
        baseline_family_scores=baseline_scores,
        proposed_family_scores=proposed_scores,
        chosen_family_scores=chosen_scores,
        feasibility=feasibility,
        baseline_family=baseline_family,
        proposed_family=proposed_family,
        chosen_family=chosen_family,
        baseline_action=baseline_action,
        proposed_action=proposed_action,
        chosen_action=chosen_action,
        comparison=comparison,
    ).to_dict()
    return {
        "mode": mode,
        "error_class": cls,
        "attempt_index": int(attempt_index),
        "max_attempts": int(max_attempts),
        "family_scores": {key: round(value, 6) for key, value in chosen_scores.items()},
        "best_family": chosen_family,
        "best_action": chosen_action,
        "active_override": bool(comparison.override_applied),
        "v2": v2_trace,
    }
