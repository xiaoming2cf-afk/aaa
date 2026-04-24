# Implementation Blueprint

This blueprint describes how the mathematical foundation should later enter the codebase. It is intentionally non-executable in this phase.

It assumes the canonical runtime architecture defined in [foundation_architecture.md](./foundation_architecture.md). Future code should be derived from that architecture, not the other way around.

The intended subsystem specializations are summarized in [subsystem_instantiations.md](./subsystem_instantiations.md).

Every future internal type should distinguish:

- strict mathematical object
- variational surrogate
- operational implementation field

## 1. Rollout Modes

Future implementation should support:

- `off`: current heuristics only
- `shadow`: compute ARBITER outputs in parallel without changing behavior
- `active`: ARBITER may become the runtime decision core only for calibrated subsystems; uncalibrated surrogates must preserve baseline behavior and record `uncalibrated_surrogate_blocked`

## 2. Future Internal Module Layout

Recommended package:

- `src/research_agent/agent_math/__init__.py`
- `src/research_agent/agent_math/architecture.py`
- `src/research_agent/agent_math/types.py`
- `src/research_agent/agent_math/belief.py`
- `src/research_agent/agent_math/retrieval.py`
- `src/research_agent/agent_math/utility.py`
- `src/research_agent/agent_math/intervention.py`
- `src/research_agent/agent_math/delivery.py`
- `src/research_agent/agent_math/traces.py`

## 3. Core Internal Types

The future runtime should preserve the native architectural substrates:

- generative substrate
- world substrate
- memory substrate
- governance substrate
- evaluation substrate

### BeliefState

- latent task state summary
- uncertainty level
- current adequacy posterior
- current delivery posterior
- active risk estimates
- status labels for exact versus surrogate quantities

### ObservationModel

- user instruction features
- dataset profile features
- execution signals
- review signals
- provenance signals
- safety signals

### RetrievalPosterior

- candidate set `K_t`
- latent relevance event definition
- exact posterior handle when available
- query embedding
- candidate knowledge embedding
- similarity term
- prior usefulness term
- soft admissibility factor
- hard admissibility mask
- normalized surrogate distribution

### ActionUtility

- action family: `A_auto`, `A_intervene`, or `A_terminal`
- success term
- information term
- alignment term
- provenance term
- risk term
- cost term
- human-burden term
- final utility

### RepairDecision

- current failure class
- best autonomous utility
- best intervention utility
- best terminal utility
- chosen action

### DeliveryPosterior

- adequacy probability
- delivery probability
- provenance completeness signal
- risk estimate
- gate compatibility summary

### NativeArchitectureState

- generative substrate handle `G`
- world substrate `W_t`
- memory substrate `M_t`
- governance substrate `C_t`
- evaluation substrate `E_t`
- current feasible action set `A_t^F`
- current chosen action `a_t*`

## 4. Subsystem Adoption

### Data Lab Agent

Replace:

- lexical `_knowledge_score`
- fixed retry interpretation
- rule-heavy human-escalation policy

With:

- posterior retrieval
- repair-vs-human value comparison
- explicit feasible-action filtering
- candidate-set restricted retrieval posterior

### Research Orchestrator

Replace:

- `_candidate_score` heuristic

With:

- candidate expected utility
- review-conditioned posterior adequacy
- explicit distinction between surrogate score and true delivery posterior

### Quality Center

Replace:

- purely deterministic internal score assembly

With:

- posterior delivery readiness
- compatibility mapper to the current public scorecard
- explicit separation between internal posterior and public 0-100 score

## 5. Persistence And Trace Policy

Internal traces should record:

- observations used
- belief deltas
- retrieval posterior summary
- utility decomposition
- action-family comparison summary
- chosen action
- blocking or intervention cause

Public APIs should not expose raw posterior vectors or internal optimization details by default.

## 6. Compatibility Rules

- preserve current public API shapes during the first implementation pass
- add only internal fields to storage or in-memory state until shadow mode is validated
- keep Data Lab safety policy hard and non-negotiable
- keep current delivery scorecard outputs stable while the internal math changes
- never expose a variational surrogate as if it were the exact mathematical object
- never let an uncalibrated surrogate override the baseline in `active` mode

## 7. Acceptance Conditions For Future Implementation

Implementation should only move from `shadow` to `active` when:

- retrieval quality beats lexical baseline on curated cases
- repair escalation decisions outperform fixed attempt count on failure cases
- orchestrator candidate selection is at least as safe as the current penalty score
- delivery posterior maps cleanly to current publish/no-publish behavior
- no circular action-set definition remains in runtime control
- each active subsystem trace carries `calibrated=true`, a calibration version, validation metrics, and a derivation reference
