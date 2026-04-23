from __future__ import annotations

from typing import Any


def build_delivery_posterior_trace(
    *,
    citation_coverage: float,
    unsupported_claim_rate: float,
    review_block_precision: float,
    review_approved: bool,
    artifact_present: bool,
    engineering_gate_passed: bool,
    mode: str,
    threshold: float = 0.85,
) -> dict[str, Any]:
    adequacy = (
        0.34 * max(0.0, min(citation_coverage, 1.0))
        + 0.26 * max(0.0, min(1.0 - unsupported_claim_rate, 1.0))
        + 0.2 * max(0.0, min(review_block_precision, 1.0))
        + 0.1 * (1.0 if review_approved else 0.0)
        + 0.1 * (1.0 if artifact_present else 0.0)
    )
    governance = 1.0 if engineering_gate_passed else 0.0
    delivery_posterior = max(0.0, min(1.0, 0.78 * adequacy + 0.22 * governance))
    return {
        "mode": mode,
        "adequacy_evidence": round(adequacy, 6),
        "governance_evidence": round(governance, 6),
        "delivery_posterior": round(delivery_posterior, 6),
        "threshold": round(float(threshold), 6),
        "deliverable_proxy": delivery_posterior >= float(threshold) and engineering_gate_passed,
        "surrogate": "adequacy_governance_delivery_proxy",
    }
