from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


VALID_MATH_MODES = {"off", "shadow", "active"}
MATH_STATUS_EXACT = "Exact"
MATH_STATUS_VARIATIONAL = "Variational"
MATH_STATUS_OPERATIONAL = "Operational"
UNCALIBRATED_SURROGATE_REASON = "uncalibrated_surrogate_blocked"


def normalize_math_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in VALID_MATH_MODES:
        return mode
    return "off"


def settings_math_mode(settings: Any) -> str:
    return normalize_math_mode(getattr(settings, "agent_math_mode", "off"))


def clamp_unit(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def math_status_metadata(
    *,
    status: str,
    calibrated: bool = False,
    calibration_version: str = "",
    validation_metrics: dict[str, Any] | None = None,
    derivation_ref: str = "",
    gate: str = "",
) -> dict[str, Any]:
    normalized_status = str(status or MATH_STATUS_OPERATIONAL).strip()
    if normalized_status not in {MATH_STATUS_EXACT, MATH_STATUS_VARIATIONAL, MATH_STATUS_OPERATIONAL}:
        normalized_status = MATH_STATUS_OPERATIONAL
    return {
        "status": normalized_status,
        "calibrated": bool(calibrated),
        "calibration_version": str(calibration_version or ""),
        "validation_metrics": _json_ready(validation_metrics or {}),
        "derivation_ref": str(derivation_ref or ""),
        "gate": str(gate or ""),
        "active_decision_allowed": bool(calibrated),
    }


def probability_semantics(math_status: dict[str, Any] | None) -> str:
    return "calibrated_posterior" if bool((math_status or {}).get("calibrated")) else "uncalibrated_surrogate"


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return str(value)


@dataclass
class BeliefState:
    W_t: dict[str, Any] = field(default_factory=dict)
    M_t: dict[str, Any] = field(default_factory=dict)
    C_t: dict[str, Any] = field(default_factory=dict)
    E_t: dict[str, Any] = field(default_factory=dict)
    belief_distribution: dict[str, float] = field(default_factory=dict)

    def normalized_distribution(self) -> dict[str, float]:
        values = {
            str(key): max(0.0, float(value))
            for key, value in (self.belief_distribution or {}).items()
        }
        total = sum(values.values())
        if total <= 0.0:
            return {}
        return {key: value / total for key, value in values.items()}

    def entropy(self, *, base: float = 2.0) -> float:
        distribution = self.normalized_distribution()
        if not distribution:
            return 0.0
        log_base = math.log(float(base)) if base and base > 0.0 else 1.0
        return -sum(probability * (math.log(probability) / log_base) for probability in distribution.values() if probability > 0.0)

    def kl_divergence(self, reference_distribution: dict[str, float], *, base: float = 2.0, epsilon: float = 1e-12) -> float:
        posterior = self.normalized_distribution()
        reference_values = {str(key): max(0.0, float(value)) for key, value in (reference_distribution or {}).items()}
        reference_total = sum(reference_values.values())
        if not posterior or reference_total <= 0.0:
            return 0.0
        reference = {key: value / reference_total for key, value in reference_values.items()}
        states = set(posterior) | set(reference)
        log_base = math.log(float(base)) if base and base > 0.0 else 1.0
        return sum(
            max(posterior.get(state, 0.0), epsilon)
            * (math.log(max(posterior.get(state, 0.0), epsilon) / max(reference.get(state, 0.0), epsilon)) / log_base)
            for state in states
        )

    def information_gain(self, prior_distribution: dict[str, float], *, base: float = 2.0) -> float:
        return self.kl_divergence(prior_distribution, base=base)

    def update(
        self,
        *,
        observation: dict[str, Any] | None = None,
        action: str = "",
        transition: dict[str, dict[str, float]] | None = None,
        likelihood: dict[str, float] | None = None,
    ) -> "BeliefState":
        prior = self.normalized_distribution()
        if prior:
            predicted: dict[str, float] = {}
            if transition:
                for previous_state, previous_probability in prior.items():
                    row = transition.get(previous_state) or {}
                    if not row:
                        predicted[previous_state] = predicted.get(previous_state, 0.0) + previous_probability
                        continue
                    for next_state, probability in row.items():
                        predicted[str(next_state)] = predicted.get(str(next_state), 0.0) + previous_probability * max(0.0, float(probability))
            else:
                predicted = dict(prior)
            posterior = {
                state: probability * max(0.0, float((likelihood or {}).get(state, 1.0)))
                for state, probability in predicted.items()
            }
            total = sum(posterior.values())
            if total > 0.0:
                posterior = {state: probability / total for state, probability in posterior.items()}
            else:
                posterior = dict(prior)
        else:
            posterior = {}

        observation_payload = _json_ready(observation or {})
        updated = BeliefState(
            W_t={
                **dict(self.W_t),
                "last_action": str(action or ""),
                "last_observation": observation_payload,
            },
            M_t=dict(self.M_t),
            C_t=dict(self.C_t),
            E_t={
                **dict(self.E_t),
                "belief_entropy": round(
                    -sum(probability * math.log(probability, 2) for probability in posterior.values() if probability > 0.0),
                    6,
                )
                if posterior
                else 0.0,
            },
            belief_distribution=posterior,
        )
        if prior and posterior:
            updated.E_t["information_gain"] = round(updated.information_gain(prior), 6)
        return updated

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "W_t": _json_ready(self.W_t),
            "M_t": _json_ready(self.M_t),
            "C_t": _json_ready(self.C_t),
            "E_t": _json_ready(self.E_t),
        }
        if self.belief_distribution:
            payload["belief_distribution"] = _json_ready(self.normalized_distribution())
            payload["belief_entropy"] = round(self.entropy(), 6)
            if "information_gain" in self.E_t:
                payload["information_gain"] = _json_ready(self.E_t.get("information_gain"))
        return payload


@dataclass(frozen=True)
class ArbiterV2Metadata:
    utility: float = 0.0
    feasible: bool = False
    math_status: dict[str, Any] = field(default_factory=dict)
    present: bool = False
    warning: str = ""

    @classmethod
    def from_candidate_metadata(cls, metadata: dict[str, Any] | None) -> "ArbiterV2Metadata":
        arbiter = (metadata or {}).get("arbiter")
        if not isinstance(arbiter, dict):
            return cls(warning="missing_metadata_arbiter")
        v2 = arbiter.get("v2")
        if not isinstance(v2, dict):
            return cls(warning="missing_metadata_arbiter_v2")
        if "utility" not in v2 and "utility_proxy" not in v2:
            return cls(
                feasible=bool(v2.get("feasible", False)),
                math_status=dict(v2.get("math_status") or {}),
                present=True,
                warning="missing_v2_utility",
            )
        return cls(
            utility=float(v2.get("utility", v2.get("utility_proxy", 0.0)) or 0.0),
            feasible=bool(v2.get("feasible", True)),
            math_status=dict(v2.get("math_status") or {}),
            present=True,
            warning="",
        )


@dataclass
class CandidateObservation:
    candidate_id: str
    title: str
    source_type: str
    feasible: bool
    lexical_hits: int = 0
    profile_hits: int = 0
    memory_hits: int = 0
    semantic_similarity: float = 0.0
    prior: float = 1.0
    admissibility: float = 1.0
    baseline_probability: float = 0.0
    posterior: float = 0.0
    math_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "source_type": self.source_type,
            "feasible": self.feasible,
            "lexical_hits": self.lexical_hits,
            "profile_hits": self.profile_hits,
            "memory_hits": self.memory_hits,
            "semantic_similarity": round(self.semantic_similarity, 6),
            "prior": round(self.prior, 6),
            "admissibility": round(self.admissibility, 6),
            "baseline_probability": round(self.baseline_probability, 6),
            "posterior": round(self.posterior, 6),
            "surrogate_probability": round(self.posterior, 6),
            "posterior_semantics": probability_semantics(self.math_status),
            "math_status": _json_ready(self.math_status),
        }


@dataclass
class FeasibilityMask:
    action_family: str
    feasible: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_family": self.action_family,
            "feasible": self.feasible,
            "reason": self.reason,
        }


@dataclass
class ShadowComparison:
    baseline_choice: str
    proposed_choice: str
    chosen_choice: str
    baseline_score: float
    proposed_score: float
    advantage: float
    override_margin: float
    min_raw_advantage: float = 0.01
    raw_advantage: float = 0.0
    override_applied: bool = False
    fallback_reason: str = ""
    calibrated: bool = False
    calibration_version: str = ""
    validation_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_choice": self.baseline_choice,
            "proposed_choice": self.proposed_choice,
            "chosen_choice": self.chosen_choice,
            "baseline_score": round(self.baseline_score, 6),
            "proposed_score": round(self.proposed_score, 6),
            "advantage": round(self.advantage, 6),
            "advantage_semantics": "relative_to_max_abs_score",
            "raw_advantage": round(self.raw_advantage, 6),
            "override_margin": round(self.override_margin, 6),
            "min_raw_advantage": round(self.min_raw_advantage, 6),
            "override_applied": self.override_applied,
            "fallback_reason": self.fallback_reason,
            "calibrated": self.calibrated,
            "calibration_version": self.calibration_version,
            "validation_metrics": _json_ready(self.validation_metrics),
        }


@dataclass
class DecisionTrace:
    mode: str
    belief_state: BeliefState
    baseline_family_scores: dict[str, float]
    proposed_family_scores: dict[str, float]
    chosen_family_scores: dict[str, float]
    feasibility: dict[str, FeasibilityMask]
    baseline_family: str
    proposed_family: str
    chosen_family: str
    baseline_action: str
    proposed_action: str
    chosen_action: str
    comparison: ShadowComparison
    math_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "belief_state": self.belief_state.to_dict(),
            "baseline_family_scores": {key: round(value, 6) for key, value in self.baseline_family_scores.items()},
            "proposed_family_scores": {key: round(value, 6) for key, value in self.proposed_family_scores.items()},
            "chosen_family_scores": {key: round(value, 6) for key, value in self.chosen_family_scores.items()},
            "feasibility": {key: value.to_dict() for key, value in self.feasibility.items()},
            "baseline_family": self.baseline_family,
            "proposed_family": self.proposed_family,
            "chosen_family": self.chosen_family,
            "baseline_action": self.baseline_action,
            "proposed_action": self.proposed_action,
            "chosen_action": self.chosen_action,
            "comparison": self.comparison.to_dict(),
            "math_status": _json_ready(self.math_status),
        }


@dataclass
class DeliveryPosterior:
    mode: str
    belief_state: BeliefState
    adequacy_evidence: float
    governance_evidence: float
    delivery_posterior: float
    threshold: float
    baseline_deliverable: bool
    proposed_deliverable: bool
    chosen_deliverable: bool
    decomposition: dict[str, float]
    comparison: ShadowComparison
    math_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "belief_state": self.belief_state.to_dict(),
            "adequacy_evidence": round(self.adequacy_evidence, 6),
            "governance_evidence": round(self.governance_evidence, 6),
            "delivery_posterior": round(self.delivery_posterior, 6),
            "threshold": round(self.threshold, 6),
            "baseline_deliverable": self.baseline_deliverable,
            "proposed_deliverable": self.proposed_deliverable,
            "chosen_deliverable": self.chosen_deliverable,
            "decomposition": {key: round(value, 6) for key, value in self.decomposition.items()},
            "comparison": self.comparison.to_dict(),
            "posterior_semantics": probability_semantics(self.math_status),
            "math_status": _json_ready(self.math_status),
        }


def build_shadow_comparison(
    *,
    baseline_choice: str,
    proposed_choice: str,
    baseline_score: float,
    proposed_score: float,
    override_margin: float,
    mode: str,
    min_raw_advantage: float = 0.01,
    feasible: bool = True,
    fallback_reason: str = "",
    calibrated: bool = False,
    calibration_version: str = "",
    validation_metrics: dict[str, Any] | None = None,
) -> ShadowComparison:
    normalized_mode = normalize_math_mode(mode)
    baseline_value = float(baseline_score)
    proposed_value = float(proposed_score)
    raw_advantage = proposed_value - baseline_value
    score_scale = max(abs(baseline_value), abs(proposed_value), 1e-9)
    advantage = raw_advantage / score_scale
    metrics = dict(validation_metrics or {})
    calibration_evidence_complete = bool(calibrated) and metrics.get("calibration_gate_passed") is True
    chosen_choice = baseline_choice
    override_applied = False
    reason = fallback_reason
    if normalized_mode == "shadow":
        reason = reason or "shadow_mode_preserves_baseline"
    elif normalized_mode == "off":
        reason = reason or "math_mode_off"
    elif proposed_choice == baseline_choice:
        reason = reason or "proposed_choice_matches_baseline"
    elif not feasible:
        reason = reason or "proposed_choice_infeasible"
    elif not calibrated:
        reason = reason or UNCALIBRATED_SURROGATE_REASON
    elif not calibration_evidence_complete:
        reason = reason or "calibration_evidence_missing"
    elif raw_advantage < float(min_raw_advantage):
        reason = reason or "raw_advantage_below_minimum"
    elif advantage < float(override_margin):
        reason = reason or "advantage_below_override_margin"
    else:
        chosen_choice = proposed_choice
        override_applied = True
        reason = ""
    return ShadowComparison(
        baseline_choice=baseline_choice,
        proposed_choice=proposed_choice,
        chosen_choice=chosen_choice,
        baseline_score=baseline_value,
        proposed_score=proposed_value,
        advantage=advantage,
        min_raw_advantage=float(min_raw_advantage),
        raw_advantage=raw_advantage,
        override_margin=float(override_margin),
        override_applied=override_applied,
        fallback_reason=reason,
        calibrated=bool(calibrated),
        calibration_version=str(calibration_version or ""),
        validation_metrics=metrics,
    )
