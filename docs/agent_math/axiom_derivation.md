# Axiom Derivation

This document explains how the native ARBITER axioms are synthesized from the core authority set without copying any external framework verbatim.

It is the bridge between [core_authority_sources.md](./core_authority_sources.md) and [foundation_architecture.md](./foundation_architecture.md).

## Derivation Rule

Each ARBITER axiom must satisfy one of the following:

- it is a direct restatement of a canonical theoretical object in repository-native notation, or
- it is a documented synthesis over multiple core sources, with a new decomposition specific to this repository.

## Axiom 1. Capability Prior

### ARBITER Statement

The agent begins with a learned generative prior `p_theta(y | x)` that governs representational competence but not by itself rational control.

### Source Support

- `S01`: sequence modeling and Transformer base
- `S02`: optimization and representation learning language
- `S05`: capability frontier from scaling behavior

### Why It Is Not A Copy

ARBITER turns these model-centric sources into a systems axiom: the LLM is treated as one substrate in a larger architecture, not the whole architecture.

## Axiom 2. Partial Observability

### ARBITER Statement

The true task-and-environment state is latent, so runtime control must proceed through a belief state.

### Source Support

- `S03`: latent variables and posterior reasoning
- `S21`: belief-state control under partial observability

### Why It Is Not A Copy

ARBITER imports the belief-state view but reanchors it to modern agent state rather than a classical robotics or planning environment alone.

## Axiom 3. Query Internalization

### ARBITER Statement

The user request is not identical to the runtime control state; the agent forms an internal query state `q_t`.

### Source Support

- `S11`: sequential agent control
- `S12`: rational action quality and grounded agent behavior
- `S13`: formal planning structure
- `S19`: retrieval-reasoning interaction

### Why It Is Not A Copy

None of the sources define this exact substrate-level object. `q_t` is an ARBITER-native synthesis that explains how one user instruction can evolve into multiple internal control states as evidence changes.

## Axiom 4. Memory Is State-Conditional

### ARBITER Statement

Memory is not appended wholesale. It is selected relative to query state and governance state.

### Source Support

- `S18`: retrieval-augmented generation
- `S19`: retrieval-reasoning systems
- `S03`: latent relevance reasoning

### Why It Is Not A Copy

ARBITER moves from "retriever + generator" to "candidate-set construction + relevance posterior + governance-conditioned admissibility", which is a stronger architectural decomposition than vanilla RAG.

## Axiom 5. Governance Precedes Utility

### ARBITER Statement

An action must first be admissible before it is eligible for utility maximization.

### Source Support

- `S09`: reliable and responsible deployment constraints
- `S16`: evaluation and traceability requirements
- `S17`: formal-method and verifiability perspective
- `S20`: constrained decision logic

### Why It Is Not A Copy

ARBITER does not treat safety and provenance as soft preferences alone. It elevates them into a governance projector that restricts the feasible action domain before optimization.

## Axiom 6. Delivery Is A Posterior Event

### ARBITER Statement

Delivery is a state-dependent posterior event rather than a formatting milestone.

### Source Support

- `S09`: deployment reliability
- `S16`: evaluation and delivery criteria
- `S17`: verifiability and release constraints
- `S22-S24`: domain need for final reportability and deliverable outputs

### Why It Is Not A Copy

ARBITER fuses delivery readiness, provenance, and risk into one posterior-governed terminal concept. This is not inherited as-is from the source set.

## Axiom 7. Human Intervention Is Native

### ARBITER Statement

Human intervention is a first-class action family within the control system.

### Source Support

- `S11`: agentic control framing
- `S12`: rationality under action alternatives
- `S21`: partial observability and value under uncertainty
- `S22-S24`: data-agent workflows with human intervention

### Why It Is Not A Copy

ARBITER embeds intervention directly into the control partition `A_auto / A_intervene / A_terminal` rather than treating humans as an external exception path.

## Architectural Originality Rule

The source set supports the ingredients. The architecture itself is original only because ARBITER introduces:

- the five-substrate state decomposition,
- the operator chain from query formation to delivery,
- the governance-first admissibility projector,
- the delivery posterior as a terminal control object,
- the subsystem-instantiation rule that unifies Data Lab, Research, and Quality.

Without those original constructions, the pack would still be a literature summary rather than a repository-native foundation.
