# Data Lab Architecture

## Boundary

Data Lab 1.0 keeps the existing public API and database schema while adding a narrow `research_agent.datalab` package for new workflow helpers. The package is not a rewrite of `platform_core.py`; it documents and hosts extractable logic for preview, preflight, manifests, lineage, and model contracts.

## Module Roles

- `schemas.py`: shared typed aliases and lightweight payload helpers.
- `registry.py`: model and processing family descriptors for the existing catalog.
- `preparation_preview.py`: dry-run preview helpers.
- `preflight.py`: advisory validation checks and status aggregation.
- `manifest.py`: reproducibility manifest sanitization and construction.
- `lineage.py`: best-effort pipeline chain grouping.
- `datasets.py`: dataset loading, normalization, preview rows, profile summaries, and dataset ownership checks.
- `preparation.py`: preparation option normalization, sample preparation facade helpers, and prepared asset result assembly.
- `runs.py`: Data Lab run creation, completion, failure, listing, and history serialization.
- `model_contracts.py`: expected result contract fields.
- `errors.py`: Data Lab specific error classes.

## Compatibility

- `webapp.py` remains responsible for routing, authentication, CSRF, and workspace ownership checks.
- `platform_core.py` remains the import-compatible facade for current asset persistence, preparation execution, model execution, and serialization during this migration.
- New helper modules should be called by `platform_core.py` or `webapp.py` only where they reduce risk or duplication.
- `webapp.py` rejects blocked model preflight responses before launching the model endpoint path, preserving existing routes while avoiding ready records for blocked runs.

## Migration Path

1. Keep existing API responses compatible.
2. Extract read-only helpers first: manifest, lineage, registry, and contracts.
3. Extract pure transform helpers for preview.
4. Move preflight checks into the package while keeping model execution unchanged.
5. Only split model execution after correctness tests cover the relevant family.
