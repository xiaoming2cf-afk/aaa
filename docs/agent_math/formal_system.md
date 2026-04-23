# Formal System

This document gives the strict system-level formulation of `ARBITER`. It is the most formal layer of the research pack.

The native architecture in [foundation_architecture.md](./foundation_architecture.md) is the conceptual source of truth. This document expresses that architecture as a constrained stochastic control system.

## 1. Spaces

Let:

- `mathcal{X}` be the user-input space
- `mathcal{Y}` be the output space
- `mathcal{Z}` be the latent task-and-environment space
- `mathcal{O}` be the observation space
- `mathcal{K}` be the knowledge-item space
- `mathcal{A}` be the action space
- `mathcal{M}` be the memory-state space
- `mathcal{C}` be the governance-state space
- `mathcal{E}` be the evaluation-state space

At runtime step `t`, the full state is:

`X_t = (G, W_t, M_t, C_t, E_t)`

with:

- `G = (theta, pi)`
- `W_t = (z_t, b_t, q_t)`
- `M_t in mathcal{M}`
- `C_t in mathcal{C}`
- `E_t in mathcal{E}`

## 2. Kernels And Operators

### 2.1 Generative Kernel

The pretrained model induces:

`P_theta(dy | x)`

The aligned runtime family induces:

`Pi(dy | x, q_t, M_t, E_t)`

### 2.2 Transition Kernel

The latent world evolves by:

`T_t(dz' | z, a)`

### 2.3 Observation Kernel

The next observation is drawn from:

`O_t(do | z', a)`

### 2.4 Query Operator

The internal query state is:

`q_t = Phi_q(x_user, o_0:t, M_t, E_t)`

### 2.5 Candidate-Set Operator

The active retrieval set is:

`K_t = Phi_K(M_t, q_t, C_t)`

with `K_t subseteq mathcal{K}` and finite for any concrete runtime step.

### 2.6 Exact Relevance Posterior

For `k in K_t`,

`rho_t(k) = P(g_t(k)=1 | q_t, o_0:t, M_t, C_t, K_t)`

where `g_t(k)` is the latent event that item `k` is useful at step `t`.

### 2.7 Variational Retrieval Surrogate

For `k in K_t`,

`tilde_rho_t(k) = [exp(sim(q_t, e_k) / tau_ret) * prior_t(k) * gamma_t(k)] / [sum_{j in K_t} exp(sim(q_t, e_j) / tau_ret) * prior_t(j) * gamma_t(j)]`

with:

- `tau_ret > 0`
- `prior_t(k) >= 0`
- `gamma_t(k) in [0, 1]`

### 2.8 Proposal Kernel

Candidate proposals are produced by:

`Q_t(dY | G, q_t, M_t, tilde_rho_t, E_t)`

### 2.9 Action Projection

Candidate actions are formed by:

`A_t^cand = Phi_A(Y_t, q_t, M_t)`

### 2.10 Governance Projector

The feasible action set is:

`A_t^F = Gamma_t(A_t^cand, C_t, M_t, E_t)`

Equivalently:

`A_t^F = { a in A_t^cand : G_safe(a, C_t)=1, G_budget(a, C_t)=1, G_prov(a, C_t, M_t)=1, G_eval(a, C_t, E_t)=1 }`

### 2.11 Utility Functional

`U_t(a) = w_s Succ_t(a) + w_i Info_t(a) + w_a Align_t(a) + w_p Trace_t(a) - w_r Risk_t(a) - w_c Cost_t(a) - w_h Human_t(a)`

### 2.12 Control Law

`a_t* = argmax_{a in A_t^F} E[U_t(a) | X_t]`

### 2.13 Ledger Updates

`M_{t+1} = Upd_M(M_t, o_{t+1}, a_t, y_t)`

`C_{t+1} = Upd_C(C_t, o_{t+1}, a_t, M_{t+1})`

`E_{t+1} = Upd_E(E_t, o_{t+1}, a_t, M_{t+1}, C_{t+1})`

### 2.14 Delivery Posterior

`eta_t = P(d_t=1 | W_t, M_t, C_t, E_t)`

## 3. Session Objective

Let `tau` be the first terminal step. The runtime objective is:

`max E[sum_{t=0}^{tau} lambda^t U_t(a_t)]`

subject to:

- `a_t in A_t^F`
- terminal delivery only if `eta_t >= delta_deliver`
- terminal blocking when no acceptable continuation remains

This makes the system a constrained partially observed control problem with native retrieval, governance, intervention, and delivery layers.

## 4. Action Partition

Let:

- `A_auto subseteq mathcal{A}`
- `A_intervene subseteq mathcal{A}`
- `A_terminal subseteq mathcal{A}`

with:

- pairwise disjoint families
- `mathcal{A} = A_auto union A_intervene union A_terminal`

Their feasible subsets are:

- `A_auto^F = A_t^F intersection A_auto`
- `A_intervene^F = A_t^F intersection A_intervene`
- `A_terminal^F = A_t^F intersection A_terminal`

This partition prevents circular definitions of intervention.

## 5. Assumptions

The formal system uses the following standing assumptions.

### Assumption A1. Measurability

All kernels and operators are measurable on their stated domains.

### Assumption A2. Candidate-Set Finiteness

`K_t` is finite at each concrete runtime step, so `tilde_rho_t` is well-defined by finite normalization.

### Assumption A3. Bounded Utility

Each component of `U_t(a)` is bounded on the feasible set, so expected utility is finite.

### Assumption A4. Governance Closure

If a candidate action fails governance, it is removed from optimization rather than merely penalized.

### Assumption A5. Ledger Closure

`Upd_M`, `Upd_C`, and `Upd_E` map valid states back into their own spaces.

### Assumption A6. Terminal Availability

There exists at least one admissible terminal action when autonomous and intervention actions are exhausted, typically `block`.

## 6. Interpretation

This system means:

- generation is a proposal mechanism, not the whole agent
- retrieval is an inference mechanism over candidate memory, not blind context stuffing
- governance is a projector on the action space, not a post-hoc decoration
- intervention is a native action family
- delivery is a posterior-governed terminal event

That is the mathematical reason ARBITER is a full foundational architecture rather than a prompt workflow.
