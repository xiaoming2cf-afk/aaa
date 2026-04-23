# Boundary Conditions And Failure Modes

This document states where the ARBITER architecture is expected to weaken, fail, or require special handling. A foundational architecture is incomplete if it specifies only success logic.

## 1. Identifiability Limits

`ARBITER` maintains beliefs over latent task-and-environment state, but the true latent state is not generally identifiable from finite observations.

Consequences:

- multiple latent explanations may fit the same observation trace,
- the belief state may stay multimodal,
- high-confidence utility estimates can be falsely concentrated if observation diversity is weak.

Design implication:

- belief concentration must not be treated as proof of truth,
- retrieval and review should sometimes be selected for uncertainty reduction rather than immediate task progress.

## 2. Retrieval Misspecification

The retrieval surrogate `tilde_rho_t` is only a variational proxy for the exact relevance posterior.

Failure modes:

- semantically relevant items absent from `K_t`,
- embedding similarity misaligned with task usefulness,
- overly sharp temperature causing brittle retrieval collapse,
- overly flat temperature causing noisy memory stuffing.

Design implication:

- candidate-set construction `Phi_K` is as important as scoring,
- retrieval quality should be audited at the candidate-set level, not only at the final rank level.

## 3. Distribution Shift

The pretrained prior and aligned policy may face tasks that are materially outside their effective training support.

Failure modes:

- policy overconfidence under unfamiliar domains,
- degraded code generation under novel data layouts,
- brittle preference transfer across domains or languages.

Design implication:

- out-of-support signals should raise `Risk_t(a)`,
- shift indicators should influence intervention thresholds,
- unsupported-domain autonomy should not be mistaken for normal low-confidence behavior.

## 4. Governance Feasibility Collapse

The governance projector may remove nearly all candidate actions.

Failure modes:

- no autonomous action survives safety gates,
- provenance constraints invalidate attractive outputs,
- budget exhaustion leaves only low-value or terminal actions.

Design implication:

- `block` must remain a native terminal action,
- the system must distinguish "no good action exists" from "optimization failed".

## 5. Human-Burden Leakage

An agent can appear highly autonomous while exporting difficult cleanup to the user.

Failure modes:

- proposing code that technically runs only after heavy user repair,
- escalating too late after repeated weak repair attempts,
- delivering outputs whose verification burden is implicitly shifted to humans.

Design implication:

- `Human_t(a)` cannot be omitted from utility,
- intervention policy should compare expected human burden against expected autonomous value.

## 6. Provenance Illusion

Trace volume is not the same as trace quality.

Failure modes:

- many artifacts but weak causal link to conclusions,
- numerous citations with poor support alignment,
- execution traces that do not justify the final narrative.

Design implication:

- `Trace_t(a)` must reward evidential usefulness, not artifact count alone,
- provenance completeness should be treated jointly with adequacy and risk.

## 7. Delivery Calibration Drift

The delivery posterior `eta_t` can drift away from real publishability or usability.

Failure modes:

- optimistic delivery under weak review coverage,
- pessimistic delivery under conservative risk estimates,
- public scorecard compatibility masking internal uncertainty.

Design implication:

- delivery calibration should be audited over realized outcomes,
- public-facing scorecards must remain compatibility layers rather than the true posterior itself.

## 8. Strategic Or Multi-Actor Uncertainty

When humans, reviewers, or external systems respond strategically or unpredictably, state uncertainty is not only environmental but interactive.

Failure modes:

- human feedback shifts the task objective mid-session,
- reviewer standards change across contexts,
- tool outputs are conditionally adversarial or unstable.

Design implication:

- `W_t` should permit external-actor uncertainty,
- intervention and review outcomes should update belief, not only utility.

## 9. Foundation-Level Rule

The architecture should never be evaluated only by its best-case loop.

`ARBITER` is mature only if:

- it specifies its own failure boundaries,
- those boundaries connect back to risk, intervention, and governance,
- future implementations can expose diagnostics for these failure classes.
