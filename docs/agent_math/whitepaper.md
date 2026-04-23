# ARBITER: A Proprietary Mathematical Foundation For The Platform's Agents

## Abstract

This whitepaper defines `ARBITER`, the platform's proprietary mathematical framework for intelligent agents. `ARBITER` is not a patch over an existing workflow. It is a native foundation architecture whose canonical source is [foundation_architecture.md](./foundation_architecture.md). This whitepaper explains the mathematical logic of that architecture.

`ARBITER` treats the system as a full-stack composition of:

1. a pretrained sequence model that acts as a learned probabilistic prior,
2. an alignment layer that reshapes that prior under preference and safety pressure,
3. a partially observed runtime controller that maintains beliefs over latent task state,
4. a retrieval-and-memory mechanism that selects external knowledge by posterior value,
5. a constrained decision process that balances success, information, auditability, risk, cost, and human burden.

The framework is clean-room: it is informed by authoritative literature, but the symbol system, operational decomposition, and control logic are original to this repository.

## Mathematical Status

ARBITER uses three status labels:

- `Exact`: a direct mathematical object or objective from authoritative theory
- `Variational`: a unifying approximation or surrogate used to relate multiple exact families
- `Operational`: a control rule or ledger update used to govern a deployed system

This distinction is critical. ARBITER intentionally preserves a large unified framework, but it does not permit an approximate expression to masquerade as a strict equivalence.

## 0. Native Architecture Position

The core architectural claim of `ARBITER` is:

- the agent is not only a language model,
- the agent is not only a planner,
- the agent is not only a retrieval wrapper,
- the agent is not only an execution loop.

Instead, the agent is a native five-substrate system:

`X_t = (G, W_t, M_t, C_t, E_t)`

where:

- `G` is the generative substrate,
- `W_t` is the runtime world substrate,
- `M_t` is the memory substrate,
- `C_t` is the governance substrate,
- `E_t` is the evaluation substrate.

This whitepaper should therefore be read as the mathematical explanation of that architecture rather than as a list of heuristics attached to current code.

The native operator chain is:

`Phi_q -> belief update -> Phi_K -> rho_t / tilde_rho_t -> Phi_Y -> Phi_A -> governance filter -> utility control -> state update -> delivery posterior`

This operator chain is what makes ARBITER a complete architecture rather than only a notation layer.

## 1. Problem Statement

The current platform already contains mathematical fragments:

- dataset profiling and outlier heuristics in [data_lab_agent.py](../../src/research_agent/data_lab_agent.py)
- heuristic draft selection in [orchestrator.py](../../src/research_agent/orchestrator.py)
- scorecard gating in [quality_center.py](../../src/research_agent/quality_center.py)

What it lacks is a unified theory that explains:

- where model capability comes from,
- how alignment modifies behavior,
- how the agent should update uncertainty at runtime,
- how retrieval should interact with reasoning,
- how self-repair should compare against human intervention,
- how delivery should be treated as a mathematical decision rather than a flat checklist.

`ARBITER` fills that gap.

## 2. Layered View

### 2.1 Model Layer

The pretrained language model is represented as:

`p_theta(y | x)`

where `theta` is learned through a token-prediction objective:

`theta* = argmin_theta E[-log p_theta(x_i | x_<i)]`

This layer explains statistical fluency, pattern compression, and broad latent knowledge. It does not by itself explain reliable goal-directed action.

### 2.2 Alignment Layer

ARBITER does not treat RLHF and DPO as literally the same object.

The imported exact families are:

- `pi_RLHF = argmax_pi E_{y ~ pi(. | x)}[r_psi(x, y)] - beta_KL * KL(pi(. | x) || p_theta(. | x))`
- `L_DPO(phi) = - E log sigma(beta_pref * [log pi_phi(y^+ | x) - log pi_phi(y^- | x) - log p_ref(y^+ | x) + log p_ref(y^- | x)])`

These remain distinct exact families in ARBITER.

ARBITER then introduces one variational unifier:

`pi(y | x) propto p_theta(y | x) exp(beta_align * r_psi(x, y))`

This should be read as a preference-shaped policy family. It is a unifying approximation that preserves the large-frame story:

- the base model supplies the generative prior,
- preferences inject directional pressure,
- alignment strength determines how far the runtime policy may drift from the original prior.

It is not claimed to be a strict equivalence between RLHF and DPO.

### 2.3 Runtime World Layer

At runtime the agent does not observe the true task state directly. It acts under partial observability.

- `z_t`: latent task-and-environment state
- `o_t`: observable signals
- `b_t(z)`: belief over `z_t`

Belief is updated by:

`b_{t+1}(z) propto P(o_{t+1} | z, a_t) * sum_{z'} T(z | z', a_t) b_t(z')`

This turns the agent from a one-shot generator into an uncertainty-tracking decision system.

### 2.4 Retrieval Layer

Memory retrieval is not treated as a static append-only helper. ARBITER separates the strict object from the practical surrogate.

The exact object is the latent relevance posterior:

For `k in K_t`,

`rho_t(k) = P(g_t(k)=1 | q_t, o_0:t, M_t, C_t, K_t)`

where:

- `g_t(k)=1` means item `k` is truly useful at step `t`
- `K_t` is the active candidate set rather than the whole universe of memory
- `q_t` is the current retrieval query state

For implementation-facing reasoning ARBITER uses a variational surrogate:

For `k in K_t`,

`tilde_rho_t(k) = [exp(sim(q_t, e_k) / tau_ret) * prior_t(k) * alpha_t(k)] / [sum_{j in K_t} exp(sim(q_t, e_j) / tau_ret) * prior_t(j) * alpha_t(j)]`

where:

- `prior_t(k)` is a current usefulness prior within the candidate set
- `alpha_t(k)` is a soft admissibility factor in `[0, 1]`
- normalization is carried out only over the current candidate set `K_t`

This closes the earlier gap: the softmax object is no longer mislabeled as the exact posterior.

### 2.5 Control Layer

To avoid circular definitions, ARBITER splits the action space into three families:

- `A_auto = {generate, retrieve, plan, execute, review, repair, export, ...}`
- `A_intervene = {ask_human, request_manual_validation, request_manual_code, ...}`
- `A_terminal = {block, deliver, abort, ...}`

After admissibility filtering:

- `A_auto^F`
- `A_intervene^F`
- `A_terminal^F`

The full feasible set is:

`A_t^F = A_auto^F union A_intervene^F union A_terminal^F`

The master decision rule is:

`a_t* = argmax_{a in A_t^F} E[ U_t(a) | b_t ]`

This means the agent is neither a pure planner nor a pure generator. It is a constrained controller over action families.

## 3. The ARBITER Utility

`ARBITER` defines runtime value as:

`U_t(a) = w_s Succ_t(a) + w_i Info_t(a) + w_a Align_t(a) + w_p Trace_t(a) - w_r Risk_t(a) - w_c Cost_t(a) - w_h Human_t(a)`

Each term is operationally meaningful.

### 3.1 Success Term

`Succ_t(a)` measures expected task progress:

- improved answer adequacy,
- increased code executability,
- better evidence coverage,
- stronger delivery readiness.

### 3.2 Information Term

`Info_t(a) = E[ KL(b_{t+1} || b_t) | b_t, a ]`

The agent should prefer actions that reduce uncertainty when uncertainty is decision-relevant. This is why profiling, retrieval, and review are mathematically valuable even before they yield final outputs.

### 3.3 Alignment Term

`Align_t(a)` measures consistency with learned preference and policy structure:

- user intent fidelity,
- format adherence,
- domain appropriateness,
- alignment with post-training norms.

### 3.4 Trace Term

`Trace_t(a)` rewards provenance, auditability, and reproducibility:

- cited evidence,
- execution traces,
- explicit artifacts,
- reviewable intermediate state.

This term is necessary because a platform agent is not only judged by answer quality but by whether the result can be defended.

### 3.5 Risk Term

`Risk_t(a)` aggregates:

- safety violations,
- hallucination exposure,
- unsupported-claim probability,
- execution hazard,
- policy breach,
- silent provenance failure.

### 3.6 Cost Term

`Cost_t(a)` includes:

- token cost,
- latency,
- compute,
- external tool overhead,
- repeated execution burden.

### 3.7 Human Burden Term

`Human_t(a)` measures intervention demand:

- code the user must repair,
- review load,
- ambiguity left unresolved,
- manual validation effort.

This prevents the system from maximizing nominal autonomy while secretly offloading work onto the user.

## 4. Runtime Logic

### 4.1 Master Principle

All local runtime choices are corollaries of one rule:

`a_t* = argmax_{a in A_t^F} E[ U_t(a) | b_t ]`

No local rule is allowed to override this principle without being explicitly marked as a simplification.

### 4.2 Corollary: Generate

Generation is selected when it maximizes expected utility among feasible autonomous actions. In practice this usually coincides with:

- sufficiently concentrated belief,
- low marginal value of additional retrieval,
- acceptable risk and provenance state.

### 4.3 Corollary: Retrieve

Retrieve when:

`E[U_t(retrieve) | b_t] = max_{a in A_auto^F} E[U_t(a) | b_t]`

Under a reduced-risk local approximation, retrieval may be summarized by:

`E[Info_t(retrieve) + Succ_t(retrieve)] > E[Cost_t(retrieve)]`

but this reduced inequality is only valid when alignment, provenance, and risk terms are approximately constant across the compared local actions.

### 4.4 Corollary: Execute

Execution is selected when its expected utility dominates other feasible autonomous actions. It is often valuable because it creates new observations:

- state transition evidence,
- correctness signals,
- artifact generation,
- reviewable intermediate outputs.

### 4.5 Corollary: Repair

Repair is selected when:

`E[U_t(repair) | b_t] = max_{a in A_auto^F} E[U_t(a) | b_t]`

and in particular when:

`E[U_t(repair) | b_t] > max(max_{a in A_intervene^F} E[U_t(a) | b_t], max_{a in A_terminal^F} E[U_t(a) | b_t])`

So self-repair is not a ritual retry count. It is a value comparison under uncertainty.

### 4.6 Corollary: Ask Human

Human escalation occurs when:

`max_{a in A_intervene^F} E[U_t(a) | b_t] > max(max_{a in A_auto^F} E[U_t(a) | b_t], max_{a in A_terminal^F} E[U_t(a) | b_t])`

Operationally this appears when:

- autonomy has low expected value,
- risk dominates feasible autonomous actions,
- provenance-complete autonomy is unavailable,
- human input is expected to reduce uncertainty more efficiently than another autonomous cycle.

### 4.7 Corollary: Block

Blocking is selected when the best feasible terminal action is `block`, especially when:

- no safe autonomous continuation remains,
- intervention is also dominated by risk or policy failure,
- the feasible autonomous set is effectively empty.

### 4.8 Corollary: Deliver

Delivery is a posterior event, not a stylistic milestone. Define:

`eta_t = P(d_t=1 | b_t, M_t, C_t, E_t)`

Deliver when:

- `deliver` is the highest-utility feasible terminal action, and
- `eta_t >= delta_deliver`, and
- provenance is complete, and
- delivery evaluation gates pass.

## 5. Full-Stack State Evolution

`ARBITER` couples training and runtime through a capability ledger:

- pretraining shapes what the model can represent,
- alignment shapes which trajectories are favored,
- runtime observations reveal which trajectories are currently credible,
- retrieval changes the available evidence,
- evaluation modifies delivery readiness.

This can be written abstractly as:

`S_t = (theta, pi, b_t, M_t, C_t, E_t)`

where:

- `theta` is the frozen capability prior,
- `pi` is the aligned policy,
- `b_t` is runtime belief,
- `M_t` is memory,
- `C_t` is the active constraint mask,
- `E_t` is the evaluation ledger.

Here the status of each component is:

- `theta`: exogenous and frozen during a runtime session
- `pi`: quasi-static aligned policy family for the session
- `b_t`: endogenous belief state
- `M_t`: endogenous memory and artifact ledger
- `C_t`: endogenous constraint ledger
- `E_t`: endogenous evaluation ledger

The system evolves by:

1. observation ingestion
2. belief update
3. candidate-set formation and retrieval update
4. constraint update
5. evaluation-ledger update
6. feasible-action filtering
7. utility maximization
8. transition and audit logging

The operational state updates are:

`M_{t+1} = Upd_M(M_t, o_{t+1}, a_t)`

`C_{t+1} = Upd_C(C_t, o_{t+1}, a_t)`

`E_{t+1} = Upd_E(E_t, o_{t+1}, a_t, M_{t+1})`

Interpretation:

- `Upd_M` records retrieved items, artifacts, repair traces, human notes, and review outputs
- `Upd_C` records safety events, budget depletion, provenance failures, and policy restrictions
- `Upd_E` records adequacy evidence, delivery evidence, reviewer findings, and scorecard-relevant signals

## 6. Why ARBITER Is Not A Rephrased POMDP

`ARBITER` borrows the belief-state perspective from POMDP theory, but it is not just a renamed POMDP.

It adds:

- an explicit pretrained generative prior,
- a separate alignment layer,
- retrieval as posterior memory selection,
- provenance as a first-class utility term,
- human burden as a cost term,
- delivery gating as a mathematical event.

These extensions are required for modern LLM-centered product agents and are not captured by a bare classical control formulation.

## 7. Why ARBITER Is Not A Rephrased LAMBDA

`LAMBDA` is an important domain reference, especially for:

- programmer-inspector decomposition,
- knowledge integration,
- human intervention in data analysis,
- report and notebook export.

But `ARBITER` differs in purpose and mathematical scope:

- `LAMBDA` is mainly a data-agent workflow architecture.
- `ARBITER` is a full-stack mathematical foundation from training to delivery.
- `LAMBDA` formalizes a repair loop and a retrieval rule.
- `ARBITER` unifies training priors, alignment, belief updates, retrieval posteriors, utility, risk, human burden, and delivery.

## 8. Consequences For This Repository

The framework implies the following future direction:

- lexical knowledge scoring should become posterior retrieval,
- fixed repair loops should become value-based repair decisions,
- heuristic candidate penalties should become expected utility with risk terms,
- binary delivery scoring should become posterior delivery readiness with mapped public outputs.

Those changes are described in the separate blueprint document and are not implemented in this pack.

## 9. Boundary And Failure Logic

No foundational architecture is complete if it describes only the ideal control loop.

The most important failure boundaries for `ARBITER` are:

- latent-state non-identifiability under weak observations,
- retrieval misspecification when `K_t` omits useful knowledge or the surrogate is poorly calibrated,
- distribution shift between training support and runtime tasks,
- governance-feasibility collapse when few or no autonomous actions survive filtering,
- human-burden leakage when nominal autonomy exports hidden work to the user,
- delivery-calibration drift when `eta_t` diverges from real release readiness.

These boundaries are not afterthoughts. They are the reason `Risk_t(a)`, `Human_t(a)`, governance projection, and delivery posterior all remain first-class architectural objects.

The detailed boundary register is maintained in [boundary_conditions.md](./boundary_conditions.md).

## 10. Architectural Instantiation Rule

The native architecture is intended to instantiate multiple agent surfaces without changing its mathematical core.

Within this repository:

- Data Lab is the analytical execution instantiation,
- Research Orchestrator is the evidence-synthesis instantiation,
- Quality Center is the delivery-evaluation instantiation.

Each one must still be representable as:

- a world substrate,
- a memory substrate,
- a governance substrate,
- an evaluation substrate,
- one common feasible-action control loop.

This prevents subsystem-local heuristics from being mistaken for separate theories.

The formal subsystem specializations are recorded in [subsystem_instantiations.md](./subsystem_instantiations.md).

## 11. Reference Anchors

Core anchors for this whitepaper are:

- `S01-S05` for model and information foundations
- `S06-S10` for alignment
- `S11-S17` for agent runtime, planning, evaluation, and formal safety
- `S18-S21` for retrieval and partially observed decision logic
- `S22-S24` for data-agent domain grounding

Formal companions:

- [Formal System](./formal_system.md)
- [Proof Sketches](./proof_sketches.md)
- [Boundary Conditions](./boundary_conditions.md)
- [Subsystem Instantiations](./subsystem_instantiations.md)

## 12. Mathematical Status Summary

The most important status assignments in ARBITER are:

- `Exact`: pretraining objective, RLHF family, DPO family, belief update, latent relevance posterior
- `Variational`: preference-shaped policy family, Gibbs retrieval surrogate
- `Operational`: utility function, action-set partition, intervention rule, delivery posterior, state-ledger updates

This final section exists to prevent category mistakes during future implementation or review.
