# Mathematical Validation

This document defines the review rubric for ARBITER's mathematical quality. It is not a style guide. It is a logical validation standard.

## 1. Source Authority

### Current Gap

The source list is strong, but future edits could accidentally downgrade the framework by mixing in non-core sources without clearly labeling them.

### Revision Target

Every core object in ARBITER must be anchored to:

- a canonical exact source, or
- a documented synthesis over core sources

### Pass Condition

- no core formula depends only on a blog, workshop paper, or under-review source
- every latest-state claim cites a 2025-2026 formally published or accepted source
- every foundational claim cites a canonical paper or textbook
- every native axiom can be traced through [axiom_derivation.md](./axiom_derivation.md)

## 2. Symbol Closure

### Current Gap

A symbol system looks rigorous only if every posterior, threshold, and state object is actually defined.

### Revision Target

Every symbol used in the whitepaper must have:

- a definition
- an interpretation
- a status label: `Exact`, `Variational`, or `Operational`

### Pass Condition

- no undefined posterior objects remain
- no threshold appears without a role
- no state component is named without an update rule or a frozen-state rationale

## 3. Formula Semantics

### Current Gap

The earlier draft risked presenting approximation formulas as if they were strict equivalences.

### Revision Target

All formulas must respect their mathematical status.

### Pass Condition

- RLHF and DPO remain distinct exact families
- the preference-shaped policy family is explicitly labeled `Variational`
- the Gibbs retrieval distribution is not mislabeled as the exact posterior

## 4. Decision Derivability

### Current Gap

Local rules for retrieve, repair, and human escalation can drift away from the master utility rule.

### Revision Target

Every local decision rule must either:

- be a direct corollary of the master utility maximization rule, or
- be labeled as a restricted local approximation

### Pass Condition

- retrieve, repair, ask-human, block, and deliver all reduce to the same master rule
- any simplified local inequality explains which terms were held approximately constant
- no action family is used to define itself circularly

## 5. System Mapping

### Current Gap

A mathematically elegant framework is still weak if it cannot explain the current repo.

### Revision Target

Every major heuristic in the repo must be classified as:

- exact observable
- variational surrogate
- operational policy

### Pass Condition

- `_knowledge_score` is explicitly treated as a lexical surrogate baseline
- `_candidate_score` is explicitly treated as a heuristic utility surrogate
- `build_delivery_scorecard` is explicitly treated as a public operational mapping

## 6. Clean-Room Originality

### Current Gap

A framework can become derivative if it silently inherits terminology or logic from external agents.

### Revision Target

ARBITER must remain a repository-native theory.

### Pass Condition

- no external prompt structures appear
- no borrowed variable system replaces ARBITER notation
- no external workflow is copied and relabeled without a new mathematical decomposition

## 7. Architectural Completeness

### Current Gap

A framework can be locally rigorous while still failing to define a complete native architecture.

### Revision Target

ARBITER must define its own native substrates, operator chain, and closed-loop runtime logic.

### Pass Condition

- the architecture has a canonical state decomposition
- the architecture has a fixed operator chain from query formation to delivery
- current repository subsystems are described as instantiations of that architecture rather than as the source of the theory

## 8. Full-Score Standard

ARBITER is considered mathematically strong enough for later implementation only if all of the following hold:

- no approximate formula is presented as a theorem
- no posterior object is left semantically ambiguous
- no intervention rule depends on a circular action set
- no state object lacks a defined update path or frozen-state rationale
- no major current heuristic in the repo remains unmapped
- no core claim depends on non-authoritative sources
- no architectural layer is left implicit or defined only by current code fragments
- boundary conditions and failure modes are explicitly documented

## 9. Proof Obligations

The framework is not considered mature unless the following obligations are at least sketched and tracked:

- retrieval surrogate normalization
- non-circular intervention logic
- governance-first admissibility
- state-space closure under updates
- delivery as a posterior event
