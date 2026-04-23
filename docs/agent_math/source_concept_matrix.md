# Source-to-Concept Matrix

This matrix maps each authority source to the mathematical objects used in the proprietary framework. It also records whether ARBITER adopts the imported concept as an `Exact`, `Variational`, or `Operational` object.

| ID | Primary Concepts | Imported Mathematical Objects | Status In ARBITER | What ARBITER Actually Uses |
| --- | --- | --- | --- | --- |
| S01 | self-attention, sequence modeling | token distribution, hidden state, attention map | Exact | `p_theta(y | x)` as the base generative prior |
| S02 | optimization, generalization, representation learning | loss, parameter update, regularization | Exact | training-layer notation and optimization language |
| S03 | Bayesian inference, latent variables | posterior, prior, likelihood, latent relevance | Exact | belief-state language and latent task-state abstraction |
| S04 | entropy, KL, mutual information | entropy, divergence, information gain | Exact | information-gain term in runtime utility |
| S05 | scaling laws | parameter-data-compute tradeoff | Exact | capability and budget frontier interpretation |
| S06 | RLHF | reward model, KL-regularized policy optimization | Exact | the RLHF family as one alignment mechanism |
| S07 | DPO | pairwise preference objective, reference-relative preference updates | Exact | the DPO family as another alignment mechanism |
| S08 | efficient training | data efficiency, post-training regimes | Exact | assumptions about capability transfer from training to deployment |
| S09 | reliability and responsibility | robustness, safety risk, deployment constraints | Exact | system-layer risk terms and admissibility constraints |
| S10 | training-free alignment | decoding-time steering, inference-time control | Exact | runtime alignment modifiers without weight updates |
| S11 | agentic RL | sequential decision process, policy over actions | Exact | agent runtime as a partially observed control process |
| S12 | rationality | utility, rational action quality, multimodal grounding | Exact | utility decomposition and action-quality criteria |
| S13 | planning formalization | structured plans, formal subgoal states | Exact | plan state and subtask-transition scaffolding |
| S14 | GUI agents | large action spaces, environment interaction | Exact | generalized action-space treatment beyond text-only outputs |
| S15 | social/game-theoretic agents | strategic belief, preference conflict | Exact | belief over external actors and intervention uncertainty |
| S16 | RPA evaluation | evaluation protocol, traceability, reproducibility | Exact | evaluation and delivery-readiness observables |
| S17 | formal methods for agents | specification, verification, safety contracts | Exact | constraint set and verifiability requirements |
| S18 | RAG | retriever, generator, external memory | Exact + Variational | strict relevance posterior plus practical retrieval surrogate |
| S19 | RAG-reasoning systems | retrieval-reasoning interleave | Exact + Operational | retrieval as a decision step rather than a static prelude |
| S20 | MDP | state, action, transition, reward, policy | Exact | utility-maximizing control language |
| S21 | POMDP | observation, belief update, partial observability | Exact | belief update and value-of-information framing |
| S22 | LAMBDA | programmer-inspector loop, knowledge integration, human intervention | Operational benchmark | domain benchmark for data-agent workflow design |
| S23 | stats/data-science agent survey | domain workflow taxonomy | Operational benchmark | mapping ARBITER to statistics and data-science tasks |
| S24 | data-science agent survey | current data-agent architecture landscape | Operational benchmark | latest benchmark for data-science agent system design |
| A01 | transformer circuits | circuit-level structure intuition | Auxiliary only | interpretability vocabulary, never a core axiom |

## ARBITER-Specific Syntheses

The framework uses several original syntheses. These are not direct quotations from any one source and must always be presented as ARBITER inventions.

| ARBITER Object | Source Support | Status |
| --- | --- | --- |
| native five-substrate architecture `X_t = (G, W_t, M_t, C_t, E_t)` | S01-S04, S09-S12, S16-S21 | Operational |
| preference-shaped policy family | S06, S07, S10 | Variational |
| retrieval posterior with admissibility and candidate-set restriction | S03, S18, S19, S21 | Exact |
| Gibbs retrieval surrogate over candidate memory items | S18, S19 | Variational |
| total runtime utility with provenance and human-burden terms | S04, S09, S12, S16, S17, S20 | Operational |
| intervention split into `A_auto`, `A_intervene`, and `A_terminal` | S11, S12, S17, S20, S21 | Operational |
| delivery posterior with public scorecard mapping | S09, S16, S17 | Operational |
| native operator chain `Phi_q -> belief -> Phi_K -> rho_t -> Phi_Y -> Phi_A -> governance -> utility -> delivery` | S03, S11-S12, S16-S21 | Operational |

## Derived Concept Bundles

| Bundle | Sources | Derived Concept | ARBITER Status |
| --- | --- | --- | --- |
| B1 | S01-S05 | LLM as a learned probabilistic prior over structured sequences | Exact |
| B2 | S06-S10 | Alignment as policy shaping under preference and safety constraints | Exact + Variational |
| B3 | S11-S17, S20-S21 | Agent as a constrained partially observed decision system | Exact + Operational |
| B4 | S18-S19 | Retrieval as relevance inference plus practical ranking surrogate | Exact + Variational |
| B5 | S22-S24 | Data-agent domain requirements: execution, repair, human intervention, reportability | Operational benchmark |
| B6 | S09, S16, S17 | Delivery and governance as explicit constraint and verification layers | Exact + Operational |

## Matrix Use

- [Native Foundation Architecture](./foundation_architecture.md) defines the canonical architectural state and operator chain.
- [Unified Symbol System](./unified_symbol_system.md) defines the notation used by these objects.
- [ARBITER Whitepaper](./whitepaper.md) integrates them into one full-stack theory.
- [System Mapping](./system_mapping.md) links them to current repo behavior.
- [Mathematical Validation](./mathematical_validation.md) checks whether each object is used at the correct status level.
