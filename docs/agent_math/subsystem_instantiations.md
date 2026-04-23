# Subsystem Instantiations

This document instantiates the native ARBITER architecture for the repository's three primary agent surfaces.

It is more formal than [system_mapping.md](./system_mapping.md). The goal here is not to describe current heuristics, but to show how each subsystem should be represented inside the common architecture.

## 1. Data Lab Agent Instantiation

### User Input

- dataset uploads
- workspace context
- natural-language analysis request
- optional human-written repair code

### World Substrate

- `z_t`: latent data-analysis task state
- `b_t`: belief over data quality, task progress, and code adequacy
- `q_t`: current analysis query derived from user request, dataset profile, prior execution, and repair history

### Memory Substrate

- `K_t`: candidate knowledge cards, catalog methods, workspace knowledge, team-library notes
- `R_t`: retrieval hits and ranking traces
- `Art_t`: plots, tables, generated files, notebook cells
- `H_t`: messages, code attempts, execution errors, repair traces, intervention notes

### Governance Substrate

- safety restrictions on code execution
- file-system scope restrictions
- time and output limits
- provenance requirements for reportable claims

### Evaluation Substrate

- adequacy evidence from successful execution
- risk evidence from blocked code, failing code, or low-support analysis
- delivery readiness for report and notebook export
- compatibility scorecard for user-facing summaries

### Native Action Families

- `A_auto`: profile, retrieve, generate code, execute, review, repair, export
- `A_intervene`: ask for human code, request validation, request clarification
- `A_terminal`: block, deliver report, deliver notebook, abort

### Architectural Reading

Data Lab is therefore an evidence-producing analytical control loop, not merely a chat wrapper around Python.

## 2. Research Orchestrator Instantiation

### User Input

- research question
- evidence scope
- output expectations
- review constraints

### World Substrate

- `z_t`: latent research-state over coverage, adequacy, and claim support
- `b_t`: belief over what is known, missing, or weakly supported
- `q_t`: current retrieval-and-writing control query

### Memory Substrate

- `K_t`: candidate sources, notes, snippets, retrieval results
- `R_t`: retrieval and citation traces
- `Art_t`: draft sections, supporting excerpts, revision artifacts
- `H_t`: planner outputs, reviewer findings, revision history

### Governance Substrate

- citation and supportability constraints
- scope restrictions
- latency and budget limits
- publication safety and policy constraints

### Evaluation Substrate

- adequacy evidence from coverage and support
- risk evidence from unsupported claims and missing sections
- delivery readiness for draft shipment
- public quality score compatibility

### Native Action Families

- `A_auto`: plan, retrieve, draft, review, revise, structure, export
- `A_intervene`: ask for missing scope, request human judgment, request manual review
- `A_terminal`: block, deliver draft, abort

### Architectural Reading

Research orchestration is a belief-and-evidence control problem with explicit delivery uncertainty, not a fixed planner pipeline.

## 3. Quality Center Instantiation

### User Input

- completed or candidate artifact
- reference evidence
- review traces
- publication criteria

### World Substrate

- `z_t`: latent publication-readiness state
- `b_t`: belief over adequacy, support, and release risk
- `q_t`: current evaluation query over artifact quality

### Memory Substrate

- `K_t`: candidate review rules, evidence spans, source snippets
- `R_t`: evaluation retrieval traces
- `Art_t`: reviewed artifact, score components, diagnostic artifacts
- `H_t`: review history, issue findings, gating records

### Governance Substrate

- release policy
- provenance and citation requirements
- business and engineering threshold requirements

### Evaluation Substrate

- adequacy evidence from artifact completeness
- risk evidence from unsupported claims and poor review precision
- delivery posterior for release readiness
- public scorecard state

### Native Action Families

- `A_auto`: inspect, score, compare, verify, aggregate, summarize
- `A_intervene`: request reviewer attention, request manual override
- `A_terminal`: block release, approve delivery, abort

### Architectural Reading

Quality Center is a posterior-estimation surface over delivery readiness, not merely a deterministic scoring utility.

## 4. Why The Instantiations Matter

These instantiations do two things:

- they show that one architecture can govern all three subsystems,
- they prevent subsystem-specific heuristics from masquerading as separate theories.

If a future subsystem cannot be expressed in this form, then either:

- the subsystem is not yet aligned with ARBITER, or
- the architecture itself requires extension.
