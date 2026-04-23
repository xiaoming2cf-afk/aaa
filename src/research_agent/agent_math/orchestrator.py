from __future__ import annotations

from typing import Any


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
    approved = 1.0 if str(review_status or "").strip().lower() == "approved" else 0.0
    evidence = min(float(cited_source_count), 8.0) / 8.0
    structure = max(0.0, 1.0 - 0.18 * float(missing_section_count) - 0.22 * float(invalid_source_id_count))
    risk = min(1.0, 0.22 * float(unsupported_claim_count) + 0.08 * float(finding_count) + (0.35 if approved == 0.0 else 0.0))
    utility = (
        0.52 * approved
        + 0.18 * evidence
        + 0.15 * structure
        + 0.08 * (1.0 - min(float(finding_count), 5.0) / 5.0)
        - 0.27 * risk
    )
    score = round(max(0.0, utility) * 100.0, 3)
    metadata = {
        "mode": mode,
        "approved": approved,
        "evidence_support": round(evidence, 6),
        "structure_support": round(structure, 6),
        "risk": round(risk, 6),
        "utility": round(utility, 6),
        "surrogate": "utility_from_review_observables",
    }
    return score, metadata
