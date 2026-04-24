from __future__ import annotations

import math

from .runtime import (
    MATH_STATUS_OPERATIONAL,
    BeliefState,
    DeliveryPosterior,
    build_shadow_comparison,
    clamp_unit,
    math_status_metadata,
)


def build_delivery_posterior_trace(
    *,
    citation_coverage: float,
    unsupported_claim_rate: float,
    review_block_precision: float,
    review_approved: bool,
    artifact_present: bool,
    engineering_gate_passed: bool,
    baseline_deliverable: bool = False,
    mode: str,
    threshold: float = 0.85,
    override_margin: float = 0.05,
) -> dict[str, object]:
    status = math_status_metadata(
        status=MATH_STATUS_OPERATIONAL,
        calibrated=False,
        derivation_ref="docs/agent_math/unified_symbol_system.md#13-delivery-posterior-operational",
        gate="delivery_calibration_required",
        validation_metrics={
            "brier_score": None,
            "expected_calibration_error": None,
            "false_publish_rate": None,
            "false_block_rate": None,
            "calibration_sample_count": 0,
        },
    )
    coverage_term = clamp_unit(citation_coverage)
    unsupported_term = clamp_unit(1.0 - unsupported_claim_rate)
    precision_term = clamp_unit(review_block_precision)
    artifact_term = 1.0 if artifact_present else 0.0
    review_term = 1.0 if review_approved else 0.0
    adequacy = (
        0.3 * coverage_term
        + 0.24 * unsupported_term
        + 0.2 * precision_term
        + 0.14 * review_term
        + 0.12 * artifact_term
    )
    governance = 1.0 if engineering_gate_passed else 0.0
    logit = (
        -1.6
        + 2.3 * coverage_term
        + 1.9 * unsupported_term
        + 1.4 * precision_term
        + 0.7 * review_term
        + 0.5 * artifact_term
        + 0.8 * governance
    )
    delivery_posterior = 1.0 / (1.0 + math.exp(-logit))
    proposed_deliverable = delivery_posterior >= float(threshold) and engineering_gate_passed
    comparison = build_shadow_comparison(
        baseline_choice="deliver" if baseline_deliverable else "block",
        proposed_choice="deliver" if proposed_deliverable else "block",
        baseline_score=1.0 if baseline_deliverable else 0.0,
        proposed_score=float(delivery_posterior),
        override_margin=float(override_margin),
        mode=mode,
        feasible=bool(engineering_gate_passed and (baseline_deliverable or not proposed_deliverable)),
        fallback_reason="active_never_bypasses_baseline_gate"
        if not baseline_deliverable and proposed_deliverable
        else "",
        calibrated=bool(status["calibrated"]),
        calibration_version=str(status["calibration_version"]),
        validation_metrics=dict(status["validation_metrics"]),
    )
    chosen_deliverable = comparison.chosen_choice == "deliver"
    v2 = DeliveryPosterior(
        mode=mode,
        belief_state=BeliefState(
            W_t={
                "citation_coverage": round(coverage_term, 6),
                "unsupported_claim_rate": round(clamp_unit(unsupported_claim_rate), 6),
                "review_block_precision": round(precision_term, 6),
            },
            M_t={
                "artifact_present": artifact_present,
                "review_approved": review_approved,
            },
            C_t={
                "engineering_gate_passed": engineering_gate_passed,
                "baseline_deliverable": baseline_deliverable,
            },
            E_t={
                "threshold": round(float(threshold), 6),
            },
        ),
        adequacy_evidence=adequacy,
        governance_evidence=governance,
        delivery_posterior=delivery_posterior,
        threshold=float(threshold),
        baseline_deliverable=baseline_deliverable,
        proposed_deliverable=proposed_deliverable,
        chosen_deliverable=chosen_deliverable,
        decomposition={
            "coverage_term": coverage_term,
            "unsupported_term": unsupported_term,
            "precision_term": precision_term,
            "artifact_term": artifact_term,
            "review_term": review_term,
        },
        comparison=comparison,
        math_status=status,
    ).to_dict()
    return {
        "mode": mode,
        "adequacy_evidence": round(adequacy, 6),
        "governance_evidence": round(governance, 6),
        "delivery_posterior": round(delivery_posterior, 6),
        "delivery_probability_proxy": round(delivery_posterior, 6),
        "posterior_semantics": "uncalibrated_surrogate",
        "threshold": round(float(threshold), 6),
        "deliverable_proxy": chosen_deliverable,
        "surrogate": "adequacy_governance_delivery_proxy",
        "math_status": status,
        "calibration": status,
        "v2": v2,
    }
