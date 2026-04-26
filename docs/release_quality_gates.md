# Release Quality Gates

Production quality and publish paths must not execute `pytest` or `npm run build` at request time. They read a commit-bound engineering gate artifact and fail closed when the artifact is missing, invalid, or bound to a different commit.

## Engineering Gate Artifact

CI writes the artifact after these gates pass:

- `python -m pytest -q`
- `npm run test` and `npm run build` in `frontend-spa`
- `PYTHONPATH=src python scripts/scan_repo_hygiene.py .`
- `python scripts/verify_agent_quality_gate.py`
- `python scripts/compare_model_engines.py`
- built SPA shell validation: `frontend-spa/dist/index.html` must reference `/app/assets/` and must not reference `/src/main.tsx`
- SPA dist manifest validation: every shell or bundle asset reference must exist, every `dist/assets` file must be reachable from `index.html`, and each file hash is recorded in the artifact

The artifact is generated with:

```powershell
python scripts/write_engineering_gate_artifact.py --commit <commit_sha>
```

Runtime lookup uses the current commit from `RESEARCH_AGENT_ENGINEERING_GATE_COMMIT`, `RENDER_GIT_COMMIT`, `GITHUB_SHA`, `COMMIT_SHA`, or `SOURCE_VERSION`. The default artifact locations are:

- `storage/quality/gates/engineering-gate.<commit>.json`
- `storage/quality/engineering-gate.<commit>.json`
- `storage/quality/engineering-gate.json`, only if the JSON includes a matching `commit_sha`

Set `RESEARCH_AGENT_ENGINEERING_GATE_ARTIFACT` or `ENGINEERING_GATE_ARTIFACT_PATH` to point at an explicit artifact path.

The artifact includes `commit_sha`, `artifact_schema`, `checked_at`, `source`, `passed`, the per-gate `checks` array, and a `spa_dist` manifest with the built SPA entrypoints plus SHA-256 hashes for the exact `frontend-spa/dist` file set. A failed SPA shell or manifest validation makes the artifact writer exit non-zero, so a deployment serving the Vite source entry, missing a referenced hashed asset, or carrying stale unreachable assets cannot be promoted as a green gate.

In Render auto-deploy scenarios, the runtime commit is discovered from Render's commit environment when available. If Render does not expose a commit or the matching artifact is not installed in one of the lookup locations, quality and publish gates report `engineering_gate_runtime_commit_missing` or `engineering_gate_artifact_missing` and fail closed.

## Deploy Artifact Consistency

CI verifies the deploy artifacts before a manual Render deploy job can start:

```powershell
python scripts/verify_deploy_artifacts.py --commit <commit_sha> --engineering-gate output/engineering-gate/engineering-gate.<commit_sha>.json --output output/deploy-artifacts/deploy-artifacts.<commit_sha>.json
```

The verifier blocks when the engineering gate JSON is unreadable, uses the wrong `artifact_schema`, has `passed: false`, embeds a different `commit_sha`, has a filename that is not bound to the same commit, or is missing a commit-bound `spa_dist` manifest. When the frontend dist artifact is available, add `--spa-dist frontend-spa/dist`; the current file hashes and entrypoints must exactly match the manifest. It can also validate a Render deploy report with `--render-deploy`; in that mode the deploy report must be green, must include a passing `spa_assets` verification, and must match the same commit in both JSON content and filename.

## Deploy Smoke

The deploy smoke command always checks:

- `/api/auth/me` returns `401` for anonymous requests
- `/api/health` returns healthy JSON
- `/provider-center` remains scoped out
- `/app`, `/app/quality`, and `/app/data-lab-agent` either redirect anonymous users to `/` or serve a built SPA shell
- any served SPA shell must reference `/app/assets/` and must not reference `/src/main.tsx`

Optional authenticated deep checks cover registration or login, workspace creation, CSV upload, and the quality scorecard:

```powershell
research-agent smoke-deploy --base-url https://economic-research-web.onrender.com --deep --register
```

## Render Deploy Verifier

Render deploys can be triggered with either a deploy hook or the Render API:

```powershell
$env:RENDER_DEPLOY_HOOK = "<deploy hook url>"
python scripts/verify_render_deploy.py --commit <commit_sha> --base-url https://economic-research-web.onrender.com --deep --register --engineering-gate output/engineering-gate/engineering-gate.<commit_sha>.json --output output/render-deploy/render-deploy.<commit_sha>.json
```

or:

```powershell
$env:RENDER_API_KEY = "<api key>"
$env:RENDER_SERVICE_ID = "<service id>"
python scripts/verify_render_deploy.py --commit <commit_sha> --base-url https://economic-research-web.onrender.com --deep --register --engineering-gate output/engineering-gate/engineering-gate.<commit_sha>.json --output output/render-deploy/render-deploy.<commit_sha>.json
```

Promotion requires `--base-url`, authenticated deep smoke (`--deep` with credentials or `--register`), and a commit-bound SPA dist manifest from `--engineering-gate`, `--spa-manifest`, or the engineering gate artifact environment variables. If those requirements are missing, the verifier writes blocking JSON and does not trigger Render. After smoke passes, the verifier fetches the deployed `/app/assets/*` files and compares their SHA-256 hashes to the manifest; if `/app` serves a shell instead of redirecting to login, its entrypoints must also match the manifest. If neither trigger is configured, the verifier writes blocking JSON, identifies which credential set is missing, and exits non-zero. CI uploads this report as `render-deploy-<sha>` when the workflow dispatch deploy job runs.
