from __future__ import annotations

import math
import re
from typing import Any

from .calibration import calibrated_math_status
from .runtime import (
    MATH_STATUS_VARIATIONAL,
    BeliefState,
    CandidateObservation,
    build_shadow_comparison,
    clamp_unit,
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
_SOURCE_PRIOR = {
    "workspace_knowledge": 1.15,
    "team_library": 1.05,
    "method_hint": 0.95,
    "processing_catalog": 0.9,
    "model_catalog": 0.9,
}
_PREFERRED_POLICY = "interface_only_no_external_source_injection"
_DEFAULT_SOFT_ADMISSIBILITY = 0.7
_FEASIBILITY_THRESHOLD = 0.65


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if len(token) > 2
    }


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("title") or ""),
        str(candidate.get("summary") or ""),
        " ".join(str(tag) for tag in (candidate.get("tags") or [])),
        str((candidate.get("interface") or {}).get("method") or ""),
        str((candidate.get("interface") or {}).get("slug") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def _admissibility(candidate: dict[str, Any]) -> float:
    policy = str(candidate.get("policy") or "").strip()
    if policy == _PREFERRED_POLICY:
        return 1.0
    return _DEFAULT_SOFT_ADMISSIBILITY


def _feasible(admissibility: float) -> bool:
    return float(admissibility) >= _FEASIBILITY_THRESHOLD


def _numeric_vector(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    vector: list[float] = []
    for item in value:
        try:
            vector.append(float(item))
        except (TypeError, ValueError):
            return []
    return vector


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    cosine = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
    return clamp_unit((cosine + 1.0) / 2.0)


def _query_embedding(session: dict[str, Any] | None) -> list[float]:
    session = session or {}
    math_state = dict((session.get("math") or {}).get("internal_v2_state") or {})
    for value in (
        session.get("query_embedding"),
        math_state.get("query_embedding"),
        (math_state.get("W_t") or {}).get("query_embedding") if isinstance(math_state.get("W_t"), dict) else None,
    ):
        vector = _numeric_vector(value)
        if vector:
            return vector
    return []


def _semantic_similarity(*, query_tokens: set[str], candidate: dict[str, Any], session: dict[str, Any] | None) -> float:
    query_vector = _query_embedding(session)
    candidate_vector = _numeric_vector(candidate.get("embedding") or candidate.get("vector"))
    embedding_similarity = _cosine_similarity(query_vector, candidate_vector)
    if embedding_similarity > 0.0:
        return embedding_similarity
    candidate_tokens = _tokens(_candidate_text(candidate))
    if not query_tokens or not candidate_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / max(len(query_tokens | candidate_tokens), 1)


def _profile_tokens(session: dict[str, Any] | None) -> set[str]:
    assets = list((session or {}).get("assets") or [])
    if not assets:
        return set()
    profile = dict((assets[0] or {}).get("profile") or {})
    parts: list[str] = []
    parts.extend(str(item) for item in profile.get("column_names") or [])
    parts.extend(str(item) for item in profile.get("candidate_targets") or [])
    parts.extend(str(item) for item in profile.get("candidate_features") or [])
    parts.extend(str(item) for item in profile.get("quality_warnings") or [])
    return _tokens(" ".join(parts))


def _memory_tokens(session: dict[str, Any] | None) -> set[str]:
    parts: list[str] = []
    for cell in list((session or {}).get("cells") or [])[-4:]:
        parts.append(str(cell.get("code") or ""))
        parts.append(str(cell.get("stdout") or ""))
    for message in list((session or {}).get("messages") or [])[-6:]:
        parts.append(str(message.get("content") or ""))
        for trace in message.get("repair_trace") or []:
            if isinstance(trace, dict):
                parts.append(str(trace.get("error") or ""))
                parts.append(str(trace.get("suggestion") or ""))
    return _tokens(" ".join(parts))


def _baseline_rank(candidates: list[dict[str, Any]], query_tokens: set[str], *, mode: str) -> tuple[list[dict[str, Any]], dict[str, float]]:
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        text = _candidate_text(candidate).lower()
        hits = sum(1 for token in query_tokens if token in text)
        prior = float(_SOURCE_PRIOR.get(str(candidate.get("source_type") or ""), 1.0))
        admissibility = _admissibility(candidate)
        raw = float(hits + 1) * prior * admissibility
        scored.append(
            {
                "candidate": candidate,
                "hits": hits,
                "prior": prior,
                "admissibility": admissibility,
                "raw": raw,
            }
        )

    denominator = sum(item["raw"] for item in scored)
    if denominator <= 0:
        denominator = float(len(scored) or 1)
    ranked: list[dict[str, Any]] = []
    probabilities: dict[str, float] = {}
    for item in scored:
        posterior = item["raw"] / denominator
        updated = dict(item["candidate"])
        updated["score"] = max(int(updated.get("score") or 0), max(1, int(round(posterior * 1000))))
        updated["arbiter"] = {
            "surrogate_probability": round(posterior, 6),
            "lexical_hits": item["hits"],
            "prior": round(item["prior"], 4),
            "admissibility": round(item["admissibility"], 4),
            "mode": mode,
        }
        ranked.append(updated)
        probabilities[str(updated.get("id") or "")] = posterior

    ranked.sort(
        key=lambda item: (
            float((item.get("arbiter") or {}).get("surrogate_probability") or 0.0),
            int(item.get("score") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return ranked, probabilities


def _retrieval_belief_state(
    *,
    query_text: str,
    session: dict[str, Any] | None,
    query_tokens: set[str],
    profile_tokens: set[str],
    memory_tokens: set[str],
    candidate_count: int,
) -> BeliefState:
    session = session or {}
    math_state = dict((session.get("math") or {}).get("internal_v2_state") or {})
    return BeliefState(
        W_t={
            "query": query_text,
            "query_token_count": len(query_tokens),
            "candidate_count": candidate_count,
            "dataset_fingerprint": str((((session.get("assets") or [{}])[0] or {}).get("profile") or {}).get("schema_fingerprint") or ""),
        },
        M_t={
            "profile_token_count": len(profile_tokens),
            "memory_token_count": len(memory_tokens),
            "successful_cell_count": int(((math_state.get("M_t") or {}).get("successful_cell_count") or len(session.get("cells") or []))),
            "recent_failure_classes": list(((math_state.get("M_t") or {}).get("recent_failure_classes") or []))[-6:],
        },
        C_t={
            "requested_mode": str(((session.get("executor") or {}).get("requested_mode") or "")),
            "llm_ready": bool(((session.get("llm") or {}).get("ready"))),
            "safety_event_count": int(((math_state.get("C_t") or {}).get("safety_event_count") or len(session.get("safety_events") or []))),
        },
        E_t={
            "profile_snapshot_count": len(session.get("profile_snapshots") or []),
            "knowledge_candidates": candidate_count,
        },
    )


def rank_retrieval_candidates(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    session: dict[str, Any] | None = None,
    limit: int = 10,
    mode: str = "off",
    override_margin: float = 0.05,
    calibration_registry_path: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status = calibrated_math_status(
        subsystem="retrieval",
        status=MATH_STATUS_VARIATIONAL,
        derivation_ref="docs/agent_math/unified_symbol_system.md#7-retrieval-gibbs-surrogate-variational",
        gate="retrieval_calibration_required",
        default_validation_metrics={
            "top_k_recall": None,
            "baseline_top_k_recall": None,
            "baseline_delta": None,
            "golden_query_count": 0,
            "baseline": "lexical_knowledge_score",
        },
        registry_path=calibration_registry_path,
    )
    query_tokens = _tokens(query_text)
    baseline_ranked, baseline_probabilities = _baseline_rank(candidates, query_tokens, mode=mode)
    baseline_selected = baseline_ranked[: max(1, limit)]
    candidate_by_id = {str(item.get("id") or ""): item for item in baseline_ranked}

    profile_tokens = _profile_tokens(session)
    memory_tokens = _memory_tokens(session)
    belief_state = _retrieval_belief_state(
        query_text=query_text,
        session=session,
        query_tokens=query_tokens,
        profile_tokens=profile_tokens,
        memory_tokens=memory_tokens,
        candidate_count=len(candidates),
    )

    observations: list[CandidateObservation] = []
    raw_scores: list[float] = []
    for candidate in baseline_ranked:
        text = _candidate_text(candidate).lower()
        lexical_hits = sum(1 for token in query_tokens if token in text)
        profile_hits = sum(1 for token in profile_tokens if token in text)
        memory_hits = sum(1 for token in memory_tokens if token in text)
        prior = float(_SOURCE_PRIOR.get(str(candidate.get("source_type") or ""), 1.0))
        admissibility = _admissibility(candidate)
        feasible = _feasible(admissibility)
        semantic_similarity = _semantic_similarity(query_tokens=query_tokens, candidate=candidate, session=session)
        raw_score = (
            1.15 * lexical_hits
            + 0.75 * profile_hits
            + 0.45 * memory_hits
            + 0.55 * semantic_similarity
            + 0.22 * min(int(candidate.get("score") or 0) / 100.0, 1.0)
            + math.log(max(prior, 1e-6))
            + math.log(max(admissibility, 1e-6))
        )
        observations.append(
            CandidateObservation(
                candidate_id=str(candidate.get("id") or ""),
                title=str(candidate.get("title") or ""),
                source_type=str(candidate.get("source_type") or ""),
                feasible=feasible,
                lexical_hits=lexical_hits,
                profile_hits=profile_hits,
                memory_hits=memory_hits,
                semantic_similarity=semantic_similarity,
                prior=prior,
                admissibility=admissibility,
                baseline_probability=float(baseline_probabilities.get(str(candidate.get("id") or ""), 0.0)),
                math_status=status,
            )
        )
        raw_scores.append(raw_score)

    if raw_scores:
        max_raw = max(raw_scores)
        normalized = [math.exp(value - max_raw) for value in raw_scores]
        denominator = sum(normalized) or 1.0
    else:
        normalized = []
        denominator = 1.0
    for observation, value in zip(observations, normalized):
        observation.posterior = value / denominator

    proposed_observations = sorted(
        observations,
        key=lambda item: (item.feasible, item.posterior, item.baseline_probability, item.title),
        reverse=True,
    )
    proposed_ids = [item.candidate_id for item in proposed_observations[: max(1, limit)] if item.candidate_id]
    baseline_ids = [str(item.get("id") or "") for item in baseline_selected if item.get("id")]
    baseline_choice = baseline_ids[0] if baseline_ids else ""
    proposed_choice = proposed_ids[0] if proposed_ids else baseline_choice
    baseline_choice_posterior = next((item.posterior for item in observations if item.candidate_id == baseline_choice), 0.0)
    proposed_choice_posterior = next((item.posterior for item in observations if item.candidate_id == proposed_choice), baseline_choice_posterior)
    comparison = build_shadow_comparison(
        baseline_choice=baseline_choice,
        proposed_choice=proposed_choice,
        baseline_score=baseline_choice_posterior,
        proposed_score=proposed_choice_posterior,
        override_margin=float(override_margin),
        mode=mode,
        feasible=bool(proposed_choice and next((item.feasible for item in proposed_observations if item.candidate_id == proposed_choice), False)),
        calibrated=bool(status["calibrated"]),
        calibration_version=str(status["calibration_version"]),
        validation_metrics=dict(status["validation_metrics"]),
    )
    chosen_ids = proposed_ids if comparison.override_applied else baseline_ids
    chosen_ranked = [candidate_by_id[item_id] for item_id in chosen_ids if item_id in candidate_by_id]
    if not chosen_ranked:
        chosen_ranked = baseline_selected
    for item in chosen_ranked:
        candidate_id = str(item.get("id") or "")
        v2_observation = next((observation for observation in observations if observation.candidate_id == candidate_id), None)
        arbiter = dict(item.get("arbiter") or {})
        arbiter["v2"] = {
            "posterior": round(float(v2_observation.posterior if v2_observation is not None else 0.0), 6),
            "surrogate_probability": round(float(v2_observation.posterior if v2_observation is not None else 0.0), 6),
            "posterior_semantics": "uncalibrated_surrogate",
            "baseline_probability": round(float(v2_observation.baseline_probability if v2_observation is not None else 0.0), 6),
            "feasible": bool(v2_observation.feasible) if v2_observation is not None else False,
            "semantic_similarity": round(float(v2_observation.semantic_similarity if v2_observation is not None else 0.0), 6),
            "math_status": status,
        }
        item["arbiter"] = arbiter

    trace = {
        "mode": mode,
        "query_tokens": sorted(query_tokens),
        "candidate_count": len(candidates),
        "selected_count": len(chosen_ranked),
        "surrogate": "candidate_set_normalized_lexical_semantic_prior",
        "math_status": status,
        "calibration": status,
        "items": [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "source_type": str(item.get("source_type") or ""),
                "surrogate_probability": float((item.get("arbiter") or {}).get("surrogate_probability") or 0.0),
                "lexical_hits": int((item.get("arbiter") or {}).get("lexical_hits") or 0),
                "semantic_similarity": float(((item.get("arbiter") or {}).get("v2") or {}).get("semantic_similarity") or 0.0),
                "admissibility": float((item.get("arbiter") or {}).get("admissibility") or 0.0),
                "math_status": status,
            }
            for item in chosen_ranked
        ],
        "v2": {
            "normalization_domain": "candidate_set",
            "belief_state": belief_state.to_dict(),
            "baseline_selected_ids": baseline_ids,
            "proposed_selected_ids": proposed_ids,
            "chosen_selected_ids": chosen_ids,
            "comparison": comparison.to_dict(),
            "candidates": [item.to_dict() for item in proposed_observations],
            "fallback_reason": comparison.fallback_reason,
            "posterior_mass_top_k": round(clamp_unit(sum(item.posterior for item in proposed_observations[: max(1, limit)])), 6),
        },
    }
    return chosen_ranked, trace
