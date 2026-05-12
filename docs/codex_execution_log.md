# Codex Execution Log

## Baseline

- Branch: `love/strange`.
- Dirty worktree was preserved with safety branches and patch snapshots before additional changes.
- Existing implementation already contained the main P0/P1/P2 code paths for SPA overview, Data Lab hub, ASGI hardening, SVG rejection, preview, preflight, manifests, model correctness, and optimization limits.

## Stage 0 - Audit And Rules

- Added/updated project rules and architecture/security/Data Lab/UI documentation.
- Added `src/research_agent/datalab/` helper package for registry, preflight, manifest, preparation preview, lineage, contracts, schemas, and errors.
- Remaining follow-up: deeper extraction from `platform_core.py` into focused modules.

## Stage 1 - P0 Security

- ASGI static short-circuit responses include browser hardening headers and restrictive CSP.
- Source SPA fallback is dev/test-only with explicit opt-in.
- Missing `/app/assets/*` and `/assets/*` return 404.
- `/api/health` probe responses are covered by the same ASGI security header test.
- `/provider-center` no longer depends on inline styles that would be blocked by the strict CSP.
- SVG upload is rejected; SVG is also removed from multimodal inline attachment handling.
- Cookie flags are covered by tests for default HTTP and HTTPS public base URL.

## Stage 2 - P0 SPA Entry

- Added `/app/overview` and `/app/data-lab`.
- `/app` redirects to overview and wildcard app routes do not white-screen.
- Session-expired state includes a `/#auth-panel` login link.

## Stage 3 - P1 Legacy Data Lab Boundary

- Data Lab upload copy separates modelable datasets from documents.
- Dataset selectors are limited to `dataset_csv`, `dataset_excel`, and `dataset_json`.
- Non-modelable uploads show an explicit Data Lab modeling boundary warning.

## Stage 4 - P1 Data Lab Backend

- Added helper package for Data Lab architecture without changing database schema.
- `webapp.py` and `platform_core.py` remain compatibility entry points.

## Stage 5 - P1 Preparation Preview

- Added dry-run preparation preview endpoint.
- Preview returns row/column deltas, missingness changes, warnings, sample rows, and specification summary without creating result assets.

## Stage 6 - P1 Model Preflight

- Added model preflight endpoint returning `ok`, `warning`, or `blocked`.
- Checks cover generic field existence, missingness, variance, and model-specific feasibility for major model families.

## Stage 7 - P1 Manifest And Lineage

- Processing/model detail responses include `reproducibility_manifest`.
- Data Lab history includes best-effort `pipeline_chains` while preserving existing list fields.

## Stage 8 - P1 Data Lab Agent Boundary

- Agent config/session payloads include public `risk_summary`.
- Public session payloads omit local work directories and local profile paths.
- Frontend displays trusted execution and sandbox boundary messaging.

## Stage 9 - P2 Model Correctness

- Added deterministic model correctness tests for coefficients, directions, finite outputs, constraints, and documented edge behavior.
- No new model families were added.

## Stage 10 - P2 Optimization Limits

- Added resource-limit and sanity tests for small suites, oversized suites, NaN/inf input, disabled optimizers, and standard suite outputs.
- Existing backend caps remain enforced.

## Stage 11 - P3 UI Foundation

- Added neutral design token aliases and lightweight UI primitives.
- Prioritized SPA overview, Data Lab hub, and Data Lab Agent risk messaging.
- Full legacy redesign remains incremental to preserve current markers and workflows.

## Final Validation Notes

- Use `.venv\Scripts\python.exe` for pytest and verification if system Python lacks project dependencies.
- Use `npm.cmd` on Windows when PowerShell blocks `npm.ps1`.

## Final Validation Run - 2026-05-12

- `python -m compileall src tests scripts`: passed.
- Safety snapshot created: branch `love/safety-upgrade-completion-20260512-013502`, patch/files under `C:\Users\lhy18\AppData\Local\Temp\aaa-upgrade-snapshot-20260512-013502`.
- `python -m pytest -q tests/test_asgi_static_security.py tests/test_upload_security.py tests/test_auth_cookie_security.py`: failed under system Python after 6 ASGI tests passed because `python-dotenv` is not installed in that interpreter.
- `.venv\Scripts\python.exe -m pytest -q tests/test_asgi_static_security.py tests/test_upload_security.py tests/test_auth_cookie_security.py`: passed, 9 tests.
- `.venv\Scripts\python.exe -m pytest -q tests/test_data_lab_preparation_preview.py tests/test_data_lab_model_preflight.py tests/test_data_lab_result_manifest.py tests/test_data_lab_history_lineage.py tests/test_data_lab_agent_risk_boundary.py`: passed, 12 tests.
- `.venv\Scripts\python.exe -m pytest -q tests/test_data_lab_model_correctness.py tests/test_optimization_lab_limits.py`: passed, 7 tests.
- `node --check src/research_agent/web/app.js`: passed.
- `npm.cmd test`: passed, 22 frontend tests.
- `npm.cmd run build`: passed.
- `.venv\Scripts\python.exe scripts\verify_data_lab.py`: passed against the available local service, 33 models verified.
- `.venv\Scripts\python.exe scripts\verify_optimization_lab.py`: passed with upstream Mealpy/PyTensor runtime warnings.
- `.venv\Scripts\python.exe -m pytest -q`: passed, 177 tests.
- `python -m pytest -q`: failed under system Python because the interpreter lacks package installation/path setup and dependencies including `research_agent`, `sqlalchemy`, `dotenv`, and `arviz`.
- Hygiene check: forbidden/generated paths remain ignored; secret keyword scan found placeholders and test fixtures, not real credentials.
