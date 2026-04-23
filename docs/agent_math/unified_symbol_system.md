# Unified Symbol System

This document fixes the notation for the proprietary framework. The notation is original to this repository even when the underlying concepts come from standard literature.

## Mathematical Status

ARBITER uses three status labels:

- `Exact`: directly taken from authoritative theory
- `Variational`: a unifying approximation or surrogate introduced by ARBITER
- `Operational`: a control or implementation-facing object used to drive a system

## Layer 1: Model And Training

| Symbol | Meaning |
| --- | --- |
| `x` | input context |
| `y` | generated output sequence |
| `theta` | pretrained model parameters |
| `p_theta(y | x)` | pretrained conditional sequence model |
| `L_pre(theta)` | pretraining objective |
| `r_psi(x, y)` | learned or induced preference score |
| `pi(y | x)` | aligned runtime response policy |
| `beta_align` | alignment strength against the base prior |

## Layer 2: Runtime World Model

| Symbol | Meaning |
| --- | --- |
| `t` | decision step |
| `X_t` | full native architecture state at step `t` |
| `G` | generative substrate `(theta, pi)` |
| `W_t` | runtime world substrate `(z_t, b_t, q_t)` |
| `z_t` | latent task-and-environment state at step `t` |
| `o_t` | observation at step `t` |
| `b_t(z)` | belief over latent state after step `t` |
| `M_t` | external memory and artifact store |
| `Art_t` | artifact ledger inside `M_t` |
| `q_t` | retrieval query state derived from `x`, `o_0:t`, and `b_t` |
| `K_t` | candidate knowledge set considered at step `t` |
| `k` | retrievable knowledge item |
| `g_t(k)` | latent relevance event: item `k` is genuinely useful at step `t` |
| `rho_t(k)` | exact relevance posterior over items in `K_t` |
| `tilde_rho_t(k)` | variational retrieval surrogate over items in `K_t` |

## Layer 3: Action And Control

| Symbol | Meaning |
| --- | --- |
| `a_t` | candidate action at step `t` |
| `A_t` | full action set available at step `t` |
| `A_t^cand` | candidate actions projected from current proposals |
| `A_t^F` | full feasible action set after constraints |
| `A_auto` | autonomous non-terminal action family |
| `A_intervene` | intervention action family, including human handoff |
| `A_terminal` | terminal action family such as `block` and `deliver` |
| `A_auto^F` | feasible autonomous actions |
| `A_intervene^F` | feasible intervention actions |
| `A_terminal^F` | feasible terminal actions |
| `T(z_{t+1} | z_t, a_t)` | latent transition law |
| `P(o_{t+1} | z_{t+1}, a_t)` | observation model |
| `J_t(a)` | one-step action value under current belief |
| `V_t(b_t)` | value of acting from belief state `b_t` |

## Layer 4: Utility Decomposition

| Symbol | Meaning |
| --- | --- |
| `Succ_t(a)` | expected task-success contribution |
| `Info_t(a)` | expected information gain from the action |
| `Align_t(a)` | alignment and policy-consistency contribution |
| `Trace_t(a)` | provenance and auditability contribution |
| `Risk_t(a)` | expected safety, reliability, or correctness risk |
| `Cost_t(a)` | runtime, token, latency, and compute cost |
| `Human_t(a)` | expected human burden induced by the action |
| `U_t(a)` | total utility after combining rewards and penalties |

## Layer 5: Governance And Intervention

| Symbol | Meaning |
| --- | --- |
| `h_t` | human intervention signal |
| `C_t` | active constraint set |
| `E_t` | evaluation ledger |
| `G_safe(a)` | safety admissibility gate |
| `G_prov(a)` | provenance admissibility gate |
| `G_budget(a)` | budget admissibility gate |
| `G_eval(a)` | evaluation and delivery admissibility gate |
| `delta_deliver` | delivery threshold |
| `delta_human` | human-escalation threshold |
| `delta_block` | hard block threshold |
| `d_t` | latent delivery-readiness event at step `t` |
| `eta_t` | delivery posterior at step `t` |

## Native Architecture Identity

`X_t = (G, W_t, M_t, C_t, E_t)`

This is the canonical architectural state used by ARBITER.

## Observation Families

`o_t` may contain any of the following:

- user instruction text
- uploaded dataset profile
- retrieval hits
- tool outputs
- code execution traces
- review findings
- delivery-review metrics
- safety events
- human-written code or comments

## Action Families

`a_t` may belong to one of the following families:

- `A_auto = {generate, retrieve, plan, execute, review, repair, export, ...}`
- `A_intervene = {ask_human, request_manual_validation, request_manual_code, ...}`
- `A_terminal = {block, deliver, abort, ...}`

## Core Definitions Used By ARBITER

### 1. Pretraining Prior [`Exact`]

`theta* = argmin_theta E[-log p_theta(x_i | x_<i)]`

This is the canonical sequence-model pretraining view.

### 2. RLHF Policy Family [`Exact`]

`pi_RLHF = argmax_pi E_{y ~ pi(. | x)}[r_psi(x, y)] - beta_KL * KL(pi(. | x) || p_theta(. | x))`

This is the family-level policy-shaping view imported from RLHF-style alignment.

### 3. DPO Preference Objective [`Exact`]

`L_DPO(phi) = - E log sigma(beta_pref * [log pi_phi(y^+ | x) - log pi_phi(y^- | x) - log p_ref(y^+ | x) + log p_ref(y^- | x)])`

This is a pairwise preference objective. In ARBITER it is treated as a separate exact alignment family, not as the same object as RLHF.

### 4. Preference-Shaped Policy Family [`Variational`]

`pi(y | x) propto p_theta(y | x) exp(beta_align * r_psi(x, y))`

This is an ARBITER-level unifying approximation. It should be read as a preference-shaped policy family, not as a strict equivalence between RLHF and DPO.

### 5. Belief Update [`Exact`]

`b_{t+1}(z) propto P(o_{t+1} | z, a_t) * sum_{z'} T(z | z', a_t) b_t(z')`

### 6. Retrieval Relevance Posterior [`Exact`]

For `k in K_t`,

`rho_t(k) = P(g_t(k)=1 | q_t, o_0:t, M_t, C_t, K_t)`

This is the strict latent-relevance object. It is defined only over the active candidate set `K_t`.

### 7. Retrieval Gibbs Surrogate [`Variational`]

For `k in K_t`,

`tilde_rho_t(k) = [exp(sim(q_t, e_k) / tau_ret) * prior_t(k) * alpha_t(k)] / [sum_{j in K_t} exp(sim(q_t, e_j) / tau_ret) * prior_t(j) * alpha_t(j)]`

where:

- `prior_t(k)` is the current usefulness prior inside the candidate set
- `alpha_t(k)` is a soft admissibility factor in `[0, 1]`
- normalization is restricted to the current candidate set `K_t`

This object is the practical retrieval distribution. It is not the exact posterior itself.

### 8. Information Gain [`Exact`]

`Info_t(a) = E[ KL(b_{t+1} || b_t) | b_t, a ]`

### 9. Action Utility [`Operational`]

`U_t(a) = w_s Succ_t(a) + w_i Info_t(a) + w_a Align_t(a) + w_p Trace_t(a) - w_r Risk_t(a) - w_c Cost_t(a) - w_h Human_t(a)`

This is an ARBITER control functional. It is not imported as a theorem from any one source.

### 10. Feasible Action Sets [`Operational`]

`A_auto^F = { a in A_auto : G_safe(a)=1, G_prov(a)=1, G_budget(a)=1, G_eval(a)=1 }`

`A_intervene^F = { a in A_intervene : G_safe(a)=1, G_prov(a)=1, G_budget(a)=1, G_eval(a)=1 }`

`A_terminal^F = { a in A_terminal : G_safe(a)=1, G_prov(a)=1, G_budget(a)=1, G_eval(a)=1 }`

`A_t^F = A_auto^F union A_intervene^F union A_terminal^F`

### 11. Runtime Decision Rule [`Operational`]

`a_t* = argmax_{a in A_t^F} E[ U_t(a) | b_t ]`

### 12. Human Escalation Rule [`Operational`]

Escalate when:

- `max_{a in A_intervene^F} E[U_t(a) | b_t] > max_{a in A_auto^F} E[U_t(a) | b_t]`, or
- `max_{a in A_auto^F} E[U_t(a) | b_t] < delta_human`, or
- `A_auto^F = emptyset`, or
- `inf_{a in A_auto^F} Risk_t(a) > delta_block`, or
- provenance-complete autonomy is unavailable.

### 13. Delivery Posterior [`Operational`]

`eta_t = P(d_t=1 | b_t, M_t, C_t, E_t)`

This is the system's internal delivery-readiness object.

### 14. Delivery Rule [`Operational`]

Deliver only if:

- `eta_t >= delta_deliver`
- risk stays below threshold
- provenance is complete
- evaluation gates pass

### 15. State Updates [`Operational`]

`M_{t+1} = Upd_M(M_t, o_{t+1}, a_t)`

`C_{t+1} = Upd_C(C_t, o_{t+1}, a_t)`

`E_{t+1} = Upd_E(E_t, o_{t+1}, a_t, M_{t+1})`

Interpretation:

- `M_t` is a monotone-or-revised memory ledger containing retrieved items, artifacts, traces, and review records
- `C_t` is an active constraint mask updated by safety events, budget depletion, and provenance state
- `E_t` is an evaluation ledger updated by adequacy evidence, review outcomes, and delivery checks

## Naming Discipline

Future implementation must keep this notation stable. New symbols may be added, but these symbols cannot be silently redefined.
