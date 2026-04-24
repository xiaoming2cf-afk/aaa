from __future__ import annotations

from typing import Any

from .runtime import ArbiterV2Metadata, MATH_STATUS_OPERATIONAL, build_shadow_comparison, clamp_unit, math_status_metadata


def score_candidate_review(
    *,
    review_status: str,
    unsupported_claim_count: int,
    missing_section_count: int,
    invalid_source_id_count: int,
    finding_count: int,
    cited_source_count: int,
    mode: str,
) -> tuple[float, dict[str, Any]]:
    status = math_status_metadata(
        status=MATH_STATUS_OPERATIONAL,
        calibrated=False,
        derivation_ref="docs/agent_math/unified_symbol_system.md#9-action-utility-operational",
        gate="candidate_selection_calibration_required",
        validation_metrics={
            "candidate_selection_win_rate": None,
            "false_approval_rate": None,
            "calibration_sample_count": 0,
        },
    )
    approved = 1.0 if str(review_status or "").strip().lower() == "approved" else 0.0
    evidence = min(float(cited_source_count), 8.0) / 8.0
    structure = max(0.0, 1.0 - 0.18 * float(missing_section_count) - 0.22 * float(invalid_source_id_count))
    risk = min(1.0, 0.22 * float(unsupported_claim_count) + 0.08 * float(finding_count) + (0.35 if approved == 0.0 else 0.0))
    baseline_utility = (
        0.52 * approved
        + 0.18 * evidence
        + 0.15 * structure
        + 0.08 * (1.0 - min(float(finding_count), 5.0) / 5.0)
        - 0.27 * risk
    )
    baseline_score = round(max(0.0, baseline_utility) * 100.0, 3)
    citation_validity = max(0.0, 1.0 - 0.35 * float(invalid_source_id_count))
    revision_cost = clamp_unit(0.16 * float(missing_section_count) + 0.12 * float(finding_count) + (0.18 if approved == 0.0 else 0.0))
    v2_utility = clamp_unit(
        0.36 * approved
        + 0.18 * evidence
        + 0.16 * structure
        + 0.14 * citation_validity
        + 0.08 * (1.0 - risk)
        - 0.22 * revision_cost
    )
    metadata = {
        "mode": mode,
        "approved": approved,
        "evidence_support": round(evidence, 6),
        "structure_support": round(structure, 6),
        "risk": round(risk, 6),
        "utility": round(baseline_utility, 6),
        "baseline_score": baseline_score,
        "baseline_utility": round(baseline_utility, 6),
        "surrogate": "utility_from_review_observables",
        "math_status": status,
        "calibration": status,
        "v2": {
            "utility": round(v2_utility, 6),
            "utility_proxy": round(v2_utility, 6),
            "utility_semantics": "uncalibrated_surrogate",
            "citation_validity": round(citation_validity, 6),
            "revision_cost": round(revision_cost, 6),
            "evidence_support": round(evidence, 6),
            "structure_support": round(structure, 6),
            "risk": round(risk, 6),
            "feasible": True,
            "surrogate": "utility_with_revision_cost_and_citation_validity",
            "math_status": status,
        },
    }
    return baseline_score, metadata


def select_candidate_draft(
    *,
    candidates: list[Any],
    mode: str,
    override_margin: float,
) -> tuple[Any, dict[str, Any]]:
    if not candidates:
        raise ValueError("select_candidate_draft requires at least one candidate.")
    baseline_sorted = sorted(
        candidates,
        key=lambda item: (item.status == "approved", float(item.score or 0.0), -int(item.variant_index or 0)),
        reverse=True,
    )
    v2_by_draft_id = {
        str(item.draft_id): ArbiterV2Metadata.from_candidate_metadata(item.metadata or {})
        for item in candidates
    }
    proposed_sorted = sorted(
        candidates,
        key=lambda item: (
            item.status == "approved",
            v2_by_draft_id[str(item.draft_id)].present,
            v2_by_draft_id[str(item.draft_id)].utility,
            -int(item.variant_index or 0),
        ),
        reverse=True,
    )
    baseline_candidate = baseline_sorted[0]
    proposed_candidate = proposed_sorted[0]
    baseline_v2 = v2_by_draft_id[str(baseline_candidate.draft_id)]
    proposed_v2 = v2_by_draft_id[str(proposed_candidate.draft_id)]
    baseline_v2_utility = baseline_v2.utility
    proposed_v2_utility = proposed_v2.utility
    proposed_status = dict(proposed_v2.math_status)
    comparison = build_shadow_comparison(
        baseline_choice=str(baseline_candidate.draft_id),
        proposed_choice=str(proposed_candidate.draft_id),
        baseline_score=baseline_v2_utility,
        proposed_score=proposed_v2_utility,
        override_margin=float(override_margin),
        mode=mode,
        feasible=bool(proposed_v2.feasible),
        calibrated=bool(proposed_status.get("calibrated")),
        calibration_version=str(proposed_status.get("calibration_version") or ""),
        validation_metrics=dict(proposed_status.get("validation_metrics") or {}),
    )
    chosen_candidate = proposed_candidate if comparison.override_applied else baseline_candidate
    trace = {
        "mode": mode,
        "candidate_count": len(candidates),
        "baseline_draft_id": baseline_candidate.draft_id,
        "proposed_draft_id": proposed_candidate.draft_id,
        "chosen_draft_id": chosen_candidate.draft_id,
        "comparison": comparison.to_dict(),
        "baseline_score": float(baseline_candidate.score or 0.0),
        "proposed_v2_utility": round(proposed_v2_utility, 6),
        "proposed_v2_utility_proxy": round(proposed_v2_utility, 6),
        "math_status": proposed_status,
        "metadata_warnings": {
            str(candidate.draft_id): v2_by_draft_id[str(candidate.draft_id)].warning
            for candidate in candidates
            if v2_by_draft_id[str(candidate.draft_id)].warning
        },
        "items": [
            {
                "draft_id": candidate.draft_id,
                "status": candidate.status,
                "baseline_score": float(candidate.score or 0.0),
                "v2_utility": v2_by_draft_id[str(candidate.draft_id)].utility,
                "v2_utility_proxy": v2_by_draft_id[str(candidate.draft_id)].utility,
                "v2_metadata_present": v2_by_draft_id[str(candidate.draft_id)].present,
                "v2_metadata_warning": v2_by_draft_id[str(candidate.draft_id)].warning,
                "math_status": dict(v2_by_draft_id[str(candidate.draft_id)].math_status),
            }
            for candidate in candidates
        ],
    }
    return chosen_candidate, trace
