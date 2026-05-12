# Architecture Upgrade Plan

## Current Problems

- The SPA workbench needs stable entry routes for overview and Data Lab workflows.
- Legacy Data Lab pages still own the full dataset, preparation, model, results, and history workflow.
- `src/research_agent/web/app.js` carries broad page state for public pages, private workspace pages, Data Lab, Optimization Lab, and knowledge flows.
- `src/research_agent/platform_core.py` mixes upload validation, auth helpers, asset serialization, Data Lab processing, model execution, chart generation, and result serialization.
- Runtime safety boundaries need stronger static headers, fail-closed SPA serving, SVG rejection, and explicit trusted execution warnings.

## Target Architecture

- Keep FastAPI and SQLAlchemy as the backend surface while extracting Data Lab helpers into `src/research_agent/datalab/`.
- Keep legacy Data Lab pages available as the full workbench until the SPA can replace specific workflows.
- Use the SPA as the command center for workbench navigation, Data Lab aggregation, agent sessions, research runs, knowledge, and quality.
- Keep production SPA serving dist assets only; source fallback remains development/test-only.

## Backend Layering Plan

- `webapp.py` remains the API routing layer and performs request/session/workspace authorization.
- `platform_core.py` remains the compatibility facade for existing model and asset behavior during migration.
- Future `webapp.py` router splitting should group auth/workspaces, assets, Data Lab, Data Lab Agent, research runs, quality, and optimization into focused router modules without changing public paths.
- Future `platform_core.py` splitting should move upload policy, preparation transforms, model execution families, manifest serialization, and knowledge/case helpers behind stable internal interfaces.
- `datalab/preparation_preview.py` contains dry-run preview helpers.
- `datalab/preflight.py` contains advisory model validation checks.
- `datalab/manifest.py` contains reproducibility manifest construction.
- `datalab/lineage.py` contains best-effort Data Lab history chain assembly.
- `datalab/datasets.py`, `datalab/preparation.py`, and `datalab/runs.py` now host extracted dataset, preparation, and run lifecycle helpers while `platform_core.py` remains the facade.
- `datalab/registry.py` and `datalab/model_contracts.py` document model/processing contracts before deeper extraction.

## Frontend SPA Migration Plan

- Add `/app/overview` as the default command center.
- Add `/app/data-lab` as the aggregation hub for legacy workbench routes, agent runtime, history counts, and safety state.
- Keep legacy `/data-lab*` pages for full Data Lab operations while adding preview, preflight, manifest, and history chain affordances.
- Incrementally move reusable UI primitives into `frontend-spa/src/components/ui/` without rewriting every page at once.

## Legacy Strategy

- Preserve `src/research_agent/web/*.html` IDs, forms, and `verify_data_lab.py` markers.
- Apply only targeted copy, filtering, result display, and page-state fixes to legacy pages.
- Avoid deleting legacy routes until equivalent SPA flows are complete and tested.

## Risks And Rollback

- Data Lab model behavior is broad; correctness tests validate reasonableness but are not a statistical proof.
- Trusted Python execution remains unsafe outside an isolated worker/container.
- Optimization suites can be compute-heavy, so server-side caps are mandatory.
- Model run requests with blocked preflight results fail with HTTP 400 before a ready result record is created.
- Optimization benchmark suites are all-or-fail for requested matrices and reject non-finite outputs.
- Rollback is per feature: static serving, upload policy, SPA routes, preview/preflight/manifest, and UI changes are isolated enough to revert independently.
