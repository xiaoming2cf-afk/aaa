# Data Lab 1.0 Scope

## Included

- Dataset intake for CSV, XLSX/XLS, and JSON modelable datasets.
- Document asset storage for PDF, TXT, and MD through Knowledge/Paper workflows rather than direct modeling.
- Preparation preview for dry-run cleaning, filtering, type coercion, missingness handling, scaling, outlier handling, and time-series feature effects.
- Model preflight for advisory checks before model execution.
- Reproducibility manifests for processing and model result detail responses.
- Best-effort history chain grouping from source dataset to preparation, model, optimization, and agent activity.
- Data Lab Agent risk summary that states trusted execution is not sandboxed.

## Not Included

- No new econometric, statistical, finance, derivative, risk, or optimization model families.
- No PDF-to-table extraction for direct modeling.
- No schema migration unless a later PR proves it is required.
- No claim that preflight confirms statistical validity.
- No production trusted Python execution enablement.

## Definitions

- Preview: a dry-run preparation response showing row/column impact, missingness changes, warnings, and a small row sample without creating assets or mutating database state.
- Preflight: advisory model validation that returns `ok`, `warning`, or `blocked` with checks, warnings, and blocking reasons.
- Manifest: a path-safe, secret-free result summary with source dataset, workflow/model, variables, specification, generated artifacts, and warnings.
- History Chain: best-effort lineage grouping using source asset IDs, generated asset IDs, result records, and Data Lab run metadata.

## Correctness Testing Scope

- Model tests use deterministic synthetic data to verify coefficient direction, rough magnitude, finite outputs, sample sizes, forecast lengths, constraints, and warning/block behavior.
- Optimization tests verify bounded resources, disabled/unknown selection rejection, finite statistical outputs, ranking previews, raw rows, and artifact metadata.
- Tests do not replace domain expert review for publication-grade econometric or statistical claims.

## Simplified Model Boundaries

- Toy RBC / DSGE is a simplified teaching-oriented implementation and must be treated as illustrative unless a later specialist review upgrades it.
- IV tests currently verify instrument specification and coefficient direction; richer first-stage diagnostics remain a follow-up unless already exposed by a specific result.
- Time-series and volatility models are checked for finite forecasts and requested horizon behavior; they do not prove forecasting validity.
- Risk models document sign conventions in tests and verify finite VaR/ES outputs; users must still validate the loss/return convention before publication.
- Optimization Lab benchmark outputs are comparative diagnostics over bounded suites, not a proof of global optimizer dominance.
