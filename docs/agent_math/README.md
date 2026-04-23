# Agent Math Research Pack

This folder contains the clean-room research artifacts for the platform's proprietary agent mathematics program.

## Scope

The pack treats the agent as a full-stack system:

- LLM pretraining and representation
- alignment and preference shaping
- runtime reasoning and action selection
- retrieval, memory, and tool use
- self-repair, human intervention, and delivery gating

It does not implement the runtime yet. It defines the mathematical foundation that later implementations must follow.

## Mathematical Status Tiers

The pack uses three status labels consistently:

- `Exact`: a direct object or objective from authoritative theory
- `Variational`: a unifying approximation or surrogate introduced by ARBITER
- `Operational`: a control rule or state update intended for implementation

## Artifacts

- [Native Foundation Architecture](./foundation_architecture.md)
- [Core Authority Sources](./core_authority_sources.md)
- [Source Status Log](./source_status_log.md)
- [Axiom Derivation](./axiom_derivation.md)
- [Source-to-Concept Matrix](./source_concept_matrix.md)
- [Unified Symbol System](./unified_symbol_system.md)
- [Formal System](./formal_system.md)
- [ARBITER Whitepaper](./whitepaper.md)
- [Proof Sketches](./proof_sketches.md)
- [Boundary Conditions](./boundary_conditions.md)
- [Subsystem Instantiations](./subsystem_instantiations.md)
- [System Mapping](./system_mapping.md)
- [Implementation Blueprint](./implementation_blueprint.md)
- [Mathematical Validation](./mathematical_validation.md)

## Framework Name

The proprietary framework defined in this pack is named `ARBITER`:

- `A`lignment
- `R`etrieval
- `B`elief
- `I`ntervention
- `T`ooling
- `E`valuation
- `R`isk

`ARBITER` is a native constrained inference-and-control architecture for the platform's agents. It starts from a generative substrate, then defines world, memory, governance, and evaluation substrates, and closes them through one runtime control loop.

The canonical architectural entrypoint is [Native Foundation Architecture](./foundation_architecture.md). The rest of the pack should be read as supporting theory, notation, mapping, and future implementation guidance.

## Repository Anchors

The current system fragments referenced by this pack live mainly in:

- [data_lab_agent.py](../../src/research_agent/data_lab_agent.py)
- [orchestrator.py](../../src/research_agent/orchestrator.py)
- [quality_center.py](../../src/research_agent/quality_center.py)

## Rules

- Core theory may only rely on formally published or formally accepted sources.
- Under-review and workshop-only sources cannot define the core framework.
- External prompts, file structure, and naming conventions are excluded.
- The mathematical notation and operational logic in this pack are original to this repository.
- No approximate formula may be presented as a strict equivalence without an explicit `Variational` label.
