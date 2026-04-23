# ARBITER Native Foundation Architecture

This document defines the proprietary first-principles architecture behind `ARBITER`. It is the canonical architectural layer of the research pack.

The goal is not to patch an existing workflow. The goal is to define a complete mathematical substrate from which future agent systems can be derived.

## 1. Design Objective

`ARBITER` treats an agent as a constrained stochastic system that must transform incomplete observations into admissible, evidence-bearing actions under uncertainty.

The architecture is designed to support:

- natural-language understanding,
- retrieval and memory selection,
- tool execution,
- self-repair,
- human intervention,
- delivery and reporting.

It does so without reducing the system to only text generation or only classical planning.

## 2. Native Primitives

At session step `t`, the native system state is:

`X_t = (G, W_t, M_t, C_t, E_t)`

where:

- `G = (theta, pi)` is the generative substrate
- `W_t = (z_t, b_t, q_t)` is the runtime world substrate
- `M_t` is the memory substrate
- `C_t` is the governance substrate
- `E_t` is the evaluation substrate

The action universe is:

`A = A_auto union A_intervene union A_terminal`

The observation stream is:

`o_0:t = (o_0, o_1, ..., o_t)`

The output stream is:

`y_0:t = (y_0, y_1, ..., y_t)`

## 3. Architectural Axioms

### Axiom 1. Capability Prior

The system begins with a learned generative prior:

`p_theta(y | x)`

This prior determines representational competence, but not by itself rational control.

### Axiom 2. Partial Observability

The true task-and-environment state `z_t` is not directly observed. The agent acts through a belief state:

`b_t(z) = P(z_t = z | o_0:t, a_0:t-1)`

### Axiom 3. Query Internalization

The user request is not itself the runtime control state. The runtime query state is an internalized object:

`q_t = Phi_q(x_user, o_0:t, M_t, E_t)`

This allows the same user request to induce different control states as evidence accumulates.

### Axiom 4. Memory Is State-Conditional

External or prior memory is not appended wholesale. It is selected relative to the current query state and governance state.

### Axiom 5. Governance Precedes Utility

An action is not eligible for optimization unless it passes governance constraints. Admissibility is logically prior to utility maximization.

### Axiom 6. Delivery Is A Posterior Event

A result is deliverable only when adequacy, provenance, and risk jointly support delivery. Delivery is not a formatting event.

### Axiom 7. Human Intervention Is Native

Human intervention is a first-class control action. It is neither an afterthought nor a mere exception path.

## 4. Native Substrates

### 4.1 Generative Substrate

`G = (theta, pi)`

- `theta` is the pretrained parameter state
- `pi` is the aligned runtime policy family

This substrate produces candidate continuations, candidate code, candidate plans, and candidate explanations.

### 4.2 World Substrate

`W_t = (z_t, b_t, q_t)`

- `z_t` is latent task-and-environment state
- `b_t` is belief over `z_t`
- `q_t` is the internalized control query

This substrate governs what the system currently thinks the task is and how uncertain it is.

### 4.3 Memory Substrate

`M_t = (K_t, R_t, Art_t, H_t)`

- `K_t` is the active candidate knowledge set
- `R_t` is the retrieval ledger
- `Art_t` is the artifact ledger
- `H_t` is the history and trace ledger

Memory therefore includes more than retrieved text. It also includes execution traces, code attempts, review outputs, and human notes.

### 4.4 Governance Substrate

`C_t = (S_t, B_t, P_t, V_t)`

- `S_t` is the safety state
- `B_t` is the budget state
- `P_t` is the provenance state
- `V_t` is the policy and verification state

This substrate decides whether an action is even admissible.

### 4.5 Evaluation Substrate

`E_t = (alpha_t, r_t, eta_t, sigma_t)`

- `alpha_t` is adequacy evidence
- `r_t` is risk evidence
- `eta_t` is delivery readiness
- `sigma_t` is public-facing scorecard state

This substrate links internal reasoning to externally consumable output decisions.

## 5. Native Operators

The architecture evolves through a fixed operator chain.

### 5.1 Query Formation Operator

`q_t = Phi_q(x_user, o_0:t, M_t, E_t)`

This operator converts the user request plus accumulated evidence into the current control query.

### 5.2 Belief Update Operator

`b_{t+1}(z) propto P(o_{t+1} | z, a_t) * sum_{z'} T(z | z', a_t) b_t(z')`

This is the strict partial-observation update.

### 5.3 Candidate Memory Operator

`K_t = Phi_K(M_t, q_t, C_t)`

This restricts retrieval to an active candidate set rather than the whole memory universe.

### 5.4 Relevance Posterior Operator

For `k in K_t`,

`rho_t(k) = P(g_t(k)=1 | q_t, o_0:t, M_t, C_t, K_t)`

where `g_t(k)=1` means that knowledge item `k` is truly useful at step `t`.

### 5.5 Retrieval Surrogate Operator

For `k in K_t`,

`tilde_rho_t(k) = [exp(sim(q_t, e_k) / tau_ret) * prior_t(k) * gamma_t(k)] / [sum_{j in K_t} exp(sim(q_t, e_j) / tau_ret) * prior_t(j) * gamma_t(j)]`

where:

- `sim(q_t, e_k)` is a retrieval similarity term,
- `prior_t(k)` is current usefulness prior,
- `gamma_t(k)` is a soft admissibility factor in `[0, 1]`.

### 5.6 Proposal Operator

`Y_t = Phi_Y(G, q_t, M_t, tilde_rho_t, E_t)`

This operator produces candidate plans, code, explanations, or tool calls.

### 5.7 Action Projection Operator

`A_t^cand = Phi_A(Y_t, q_t, M_t)`

This converts generated proposals into executable control actions.

### 5.8 Governance Filter

`A_t^F = { a in A_t^cand : G_safe(a, C_t)=1, G_budget(a, C_t)=1, G_prov(a, C_t, M_t)=1, G_eval(a, C_t, E_t)=1 }`

This is the native feasible action set.

### 5.9 Utility Operator

`U_t(a) = w_s Succ_t(a) + w_i Info_t(a) + w_a Align_t(a) + w_p Trace_t(a) - w_r Risk_t(a) - w_c Cost_t(a) - w_h Human_t(a)`

This is the native runtime value functional.

### 5.10 Control Operator

`a_t* = argmax_{a in A_t^F} E[U_t(a) | X_t]`

The architecture therefore defines the agent as a constrained inference-and-control system.

### 5.11 State Transition Operators

`M_{t+1} = Upd_M(M_t, o_{t+1}, a_t, y_t)`

`C_{t+1} = Upd_C(C_t, o_{t+1}, a_t, M_{t+1})`

`E_{t+1} = Upd_E(E_t, o_{t+1}, a_t, M_{t+1}, C_{t+1})`

### 5.12 Delivery Operator

`eta_t = P(d_t=1 | W_t, M_t, C_t, E_t)`

Deliver if and only if:

- `deliver in A_t^F`,
- `eta_t >= delta_deliver`,
- provenance is complete,
- terminal risk is below threshold.

## 6. Native Control Families

The architecture uses three native control families:

- `A_auto`: autonomous non-terminal actions
- `A_intervene`: intervention actions
- `A_terminal`: terminal actions

Their feasible subsets are:

- `A_auto^F = A_t^F intersection A_auto`
- `A_intervene^F = A_t^F intersection A_intervene`
- `A_terminal^F = A_t^F intersection A_terminal`

This yields a complete control partition:

`A_t^F = A_auto^F union A_intervene^F union A_terminal^F`

with:

- autonomous continuation,
- human escalation,
- terminal blocking or delivery

all treated within the same decision substrate.

## 7. Closed-Loop Runtime Logic

At each step:

1. internalize the current query state `q_t`
2. update belief `b_t`
3. form candidate memory set `K_t`
4. compute latent relevance and retrieval surrogate
5. generate proposals `Y_t`
6. project proposals into candidate actions
7. apply governance filtering
8. maximize expected utility over feasible actions
9. execute or escalate
10. update memory, governance, and evaluation ledgers
11. recompute delivery readiness

This is the native closed loop. Specific agents are implementations of this loop, not exceptions to it.

## 8. Architectural Consequences

From this architecture, the following follow immediately:

- profiling is an evidence-construction action,
- retrieval is a relevance-inference action,
- execution is an observation-producing action,
- repair is a utility-ranked autonomous action,
- human escalation is a native intervention action,
- report export is a terminal deliverable action.

Therefore Data Lab, research orchestration, and quality gating are not separate theories. They are domain-specific instantiations of the same foundational architecture.

## 9. Relationship To The Rest Of The Pack

- [Unified Symbol System](./unified_symbol_system.md) defines the stable notation.
- [Axiom Derivation](./axiom_derivation.md) explains how the native axioms are synthesized from the authority set.
- [Formal System](./formal_system.md) states the stochastic-control formulation.
- [ARBITER Whitepaper](./whitepaper.md) gives the conceptual and mathematical narrative.
- [Proof Sketches](./proof_sketches.md) records proof obligations and consistency sketches.
- [Boundary Conditions](./boundary_conditions.md) records identifiability limits and failure classes.
- [Subsystem Instantiations](./subsystem_instantiations.md) specializes the native architecture to the repository's major surfaces.
- [System Mapping](./system_mapping.md) maps the architecture onto current repository fragments.
- [Implementation Blueprint](./implementation_blueprint.md) describes how future runtime modules should instantiate the architecture.

This document is the architectural source of truth. Other documents should be read as refinements, mappings, or implementation consequences of this architecture.
