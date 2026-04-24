# Implementation Traceability Matrix

This matrix links ARBITER formulas to runtime code, tests, and the validation evidence required before `active` mode may change behavior.

## ARBITER Runtime Core

| Mathematical object | Status | Runtime anchor | Current implementation state | Required validation before active override | Test anchor |
| --- | --- | --- | --- | --- | --- |
| `tilde_rho_t(k)` retrieval surrogate | Variational | `agent_math/retrieval.py` | Candidate-set-normalized lexical/profile/memory proxy with optional embedding cosine similarity and unified soft admissibility. | Golden-query top-k recall must beat `_knowledge_score`; candidate-set miss audit must be recorded. | `tests/test_agent_math_v2.py` |
| `U_t(a)` repair utility | Operational | `agent_math/control.py` | Hand-weighted utility proxy over repair, human intervention, and terminal families. | Repair success rate, human false-positive rate, and human false-negative rate must be calibrated on session traces. | `tests/test_agent_math_v2.py` |
| Candidate draft utility | Operational | `agent_math/orchestrator.py` | Review-observable utility proxy with revision-cost term. | Candidate selection win rate and false approval rate must beat baseline review score. | `tests/test_agent_runtime.py` |
| `eta_t` delivery readiness | Operational | `agent_math/delivery.py` | Zero-safe weighted adequacy proxy multiplied by governance evidence; compatibility field remains `delivery_posterior` but is marked uncalibrated. | Brier score, expected calibration error, false publish rate, and false block rate must pass release thresholds. | `tests/test_delivery_review.py` |
| `Delta_v2` shadow advantage | Operational | `agent_math/runtime.py` | Relative advantage `(proposed - baseline) / max(abs(proposed), abs(baseline), eps)` plus raw delta for audit. | Active override requires calibrated subsystem, feasible proposal, and relative margin pass. | `tests/test_agent_math_v2.py` |
| Active override comparison | Operational | `agent_math/runtime.py` | Baseline-preserving unless calibrated metadata is present. | Calibration version and validation metrics must be attached to the subsystem trace. | `tests/test_agent_math_v2.py` |

## Data Lab Model Integrity

| Model family | Runtime anchor | No-risk rule | Current validation |
| --- | --- | --- | --- |
| Bayesian regression / panel / DID / ITS | `model_engine_bayesian.py` | NUTS is the default production inference method; ADVI is only explicit `advi_preview` and is labeled `Variational`. | `tests/test_math_model_integrity.py` checks method selection. |
| Synthetic control | `model_engine_causal.py` | Donor weights are solved under the simplex constraint and placebo gaps are reported. | `tests/test_math_model_integrity.py` checks simplex weights. |
| PPML | `model_engine_runtime.py`, `platform_core.py` | Negative dependent values fail validation; no clipping. | Covered by model validation path and audit trail. |
| Logit / Probit | `model_engine_runtime.py`, `platform_core.py` | Binary dependent values must be explicit 0/1 or yes/no labels; no thresholding, rounding, or clipping. | `tests/test_math_model_integrity.py` checks strict binary validation. |
| Engine winner selection | `scripts/compare_model_engines.py`, `model_engine_winners.json` | Speed cannot select a candidate engine by itself. | `tests/test_math_model_integrity.py` checks speed-only rejection. |

## Active-Mode Rule

`AGENT_MATH_MODE=active` is not sufficient to change behavior. A subsystem may override the baseline only when its trace has:

- `calibrated: true`
- a non-empty `calibration_version`
- validation metrics for the required acceptance criteria
- a derivation reference back to the symbol system or formal system

Until then, traces must record `uncalibrated_surrogate_blocked` and preserve the baseline decision.
