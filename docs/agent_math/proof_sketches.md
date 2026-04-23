# Proof Sketches

This document records proof obligations and proof sketches for the core ARBITER architecture. These are not publication-grade proofs, but they are stronger than plain prose claims.

## Proposition 1. Retrieval Surrogate Normalization

### Claim

Under Assumption `A2`, `tilde_rho_t` defines a probability distribution over `K_t`.

### Sketch

For each `k in K_t`, the numerator is nonnegative because:

- `exp(sim(q_t, e_k) / tau_ret) > 0`
- `prior_t(k) >= 0`
- `gamma_t(k) in [0, 1]`

The denominator is the finite sum of these nonnegative terms over `K_t`. If at least one term is positive, division is well-defined and:

- `tilde_rho_t(k) >= 0`
- `sum_{k in K_t} tilde_rho_t(k) = 1`

Hence `tilde_rho_t` is a normalized surrogate distribution on the active candidate set.

## Proposition 2. Non-Circular Intervention Criterion

### Claim

If `A_auto`, `A_intervene`, and `A_terminal` are pairwise disjoint and their union is the full action universe, then intervention can be defined without circularity.

### Sketch

The intervention comparison is made between:

- `max_{a in A_auto^F} E[U_t(a) | X_t]`
- `max_{a in A_intervene^F} E[U_t(a) | X_t]`
- `max_{a in A_terminal^F} E[U_t(a) | X_t]`

Because the families are disjoint, the intervention action set does not contain the autonomous actions whose utility it is being compared against. Therefore the event "intervene is optimal" is a proper cross-family comparison, not a self-referential rule.

## Proposition 3. Governance-First Control

### Claim

If feasibility is defined by the governance projector `Gamma_t`, then no inadmissible action can be selected by the control law.

### Sketch

The control law optimizes only over `A_t^F = Gamma_t(A_t^cand, C_t, M_t, E_t)`. Any action outside `A_t^F` is excluded before utility comparison. Therefore governance acts as a hard domain restriction on optimization rather than a soft penalty term.

## Proposition 4. State Closure

### Claim

Under Assumption `A5`, the runtime loop stays inside the native state space.

### Sketch

Suppose `X_t = (G, W_t, M_t, C_t, E_t)` is valid. By construction:

- belief update keeps `b_{t+1}` inside the belief space,
- `Upd_M` maps `M_t` back into `mathcal{M}`,
- `Upd_C` maps `C_t` back into `mathcal{C}`,
- `Upd_E` maps `E_t` back into `mathcal{E}`.

Therefore `X_{t+1}` remains a valid architecture state. This gives closure of the runtime loop.

## Proposition 5. Delivery Is Not A Formatting Rule

### Claim

If delivery is governed by `eta_t = P(d_t=1 | W_t, M_t, C_t, E_t)`, then delivery is a posterior event rather than a presentation-side action.

### Sketch

The delivery event depends jointly on:

- world state and belief,
- memory and evidence,
- governance constraints,
- evaluation ledger.

Therefore delivery cannot be reduced to output style alone. It is a state-dependent terminal decision.

## Proposition 6. Local Heuristics Require Reduced Conditions

### Claim

Any local inequality such as "retrieve if information gain exceeds cost" is valid only as a reduced approximation of the master utility rule.

### Sketch

The master rule depends on all utility components. A reduced retrieve heuristic drops terms such as alignment, provenance, risk, or human burden. Such a drop is legitimate only when those omitted terms are approximately constant across the local actions being compared. Therefore the local rule is a restricted consequence, not the primary law.

## Proof Obligation Register

Future implementation work should maintain these obligations:

- surrogate retrieval must remain normalized on the candidate set
- intervention logic must preserve action-family disjointness
- governance must remain a hard filter before optimization
- state updates must remain closed over the native state space
- delivery must remain posterior-governed
