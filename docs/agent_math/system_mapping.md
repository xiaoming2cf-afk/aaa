# System Mapping

This document maps the proprietary framework onto the repository's current behavior.

The architecture itself is defined upstream in [foundation_architecture.md](./foundation_architecture.md). The repository is only a partial operational instance of that architecture.

## 1. Data Lab Agent

Primary file: [data_lab_agent.py](../../src/research_agent/data_lab_agent.py)

### Current Mathematical Fragments

| Repo Anchor | Current Behavior | ARBITER Interpretation |
| --- | --- | --- |
| `_profile_frame` at line 228 | builds role lists, schema details, warnings, candidate targets | observation model over uploaded data |
| `_numeric_column_summary` at line 319 | mean, std, quartiles, skew, IQR outlier count | low-level sufficient statistics in `o_t` |
| `_knowledge_score` at line 616 | token-overlap count | lexical surrogate baseline for the future retrieval surrogate |
| `AnalystCoder` at line 781 | code proposal from rules or LLM | `generate` action family |
| `ExecutionReviewer` at line 1061 | diagnose errors and suggest repair | `review` action family |
| `TrustedPythonExecutor` | trusted local execution with policy checks and artifact capture | `execute` action family |
| `validate_code_safety` at line 1237 | AST and text safety gate | `G_safe(a)` |
| `send_agent_message` at line 1576 | full loop across generate, execute, repair, and human code | operational surrogate controller over `A_auto`, `A_intervene`, and `A_terminal` |

### Current Gaps

- retrieval is lexical, not posterior
- repair stopping is capped by an operational retry budget, not by expected utility
- human escalation is reactive, not a subset comparison across action families
- execution mode selection is rule-based, not belief-driven
- provenance and auditability exist, but are not yet a first-class utility term

### ARBITER Upgrade Target

- `profile` becomes a structured observation family
- `knowledge_cards` become posterior-ranked memory candidates
- `repair_trace` becomes a decision ledger
- `human_intervention` becomes thresholded by comparative expected value
- `blocked` becomes a mathematically justified optimal action under empty feasible set

## 2. Research Orchestrator

Primary file: [orchestrator.py](../../src/research_agent/orchestrator.py)

### Current Mathematical Fragments

| Repo Anchor | Current Behavior | ARBITER Interpretation |
| --- | --- | --- |
| `_candidate_score` at line 229 | weighted penalty score with citation bonus | heuristic utility surrogate for a future expected-utility selector |
| `ResearchOrchestrator` at line 303 | planner, researcher, writer, reviewer sequence | multi-stage action controller |

### Current Gaps

- candidate selection is a static penalty formula
- missing-sections, unsupported-claims, and finding severity are not integrated into one posterior adequacy model
- the orchestrator has step logic but no explicit belief state
- traceability exists, but not as a formal utility reward term

### ARBITER Upgrade Target

- replace flat score with expected utility and delivery posterior
- treat review output as an observation update, not just a penalty event
- model candidate drafting as sequential control under uncertainty
- retain current public review payloads while changing internal decision math

## 3. Quality Center

Primary file: [quality_center.py](../../src/research_agent/quality_center.py)

### Current Mathematical Fragments

| Repo Anchor | Current Behavior | ARBITER Interpretation |
| --- | --- | --- |
| `_run_citation_coverage` at line 154 | scalar citation metric | provenance observable |
| `_run_unsupported_claim_rate` at line 162 | unsupported-claim penalty proxy | risk observable |
| `_run_review_block_precision` at line 169 | review decision correctness proxy | evaluation observable |
| `build_delivery_scorecard` at line 874 | dimension-wise 0/100 scoring and 500 total target | public operational mapping from internal delivery state |

### Current Gaps

- business score is deterministic and threshold-heavy
- there is no explicit posterior over delivery readiness
- engineering gate and business gate combine late rather than through one utility-and-constraint model

### ARBITER Upgrade Target

- internalize a delivery posterior using quality observables
- keep the public scorecard shape for compatibility
- treat publication readiness as a delivery event under constraints, not only as a pass/fail checklist

## 4. Cross-System Fragmentation

The repo already contains math, but it is fragmented:

- Data Lab uses statistics plus bounded-control heuristics
- Orchestrator uses fixed candidate penalties
- Quality Center uses deterministic score aggregation

`ARBITER` unifies them by treating all three as different surfaces over the same core objects:

- observation
- belief
- retrieval
- action utility
- risk
- provenance
- intervention
- delivery

It also classifies each current repo mechanism into one of three statuses:

- `Exact` observables: dataset statistics, review findings, citation coverage, safety events
- `Variational` surrogates: lexical retrieval score, heuristic candidate penalties
- `Operational` policies: retry caps, block behavior, public scorecard mapping

## 5. Future Integration Order

Recommended order for later implementation:

1. Data Lab retrieval posterior and repair decision
2. Orchestrator candidate utility and adequacy posterior
3. Quality delivery posterior with public compatibility mapping

That order minimizes breakage while replacing the most obviously fragmented math first.
