# Economic Research Platform

Economic Research Platform is a private research workspace for literature, knowledge records, queued research runs, Data Lab runs, schedules, and public briefings.

## Local Run

### App Development Minimum

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
Copy-Item .env.example .env
.\.venv\Scripts\research-agent init-db
.\.venv\Scripts\research-agent serve --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Frontend shell files are not hot-reloaded by the default `serve` command. After changing `src/research_agent/web/*.html`, `src/research_agent/web/app.js`, `src/research_agent/web/locale_*.js`, or `src/research_agent/web/styles.css`, restart `research-agent serve` or launch with `--reload`.

### Backend And Worker

Research runs are queued through the API and processed asynchronously by the worker:

```powershell
.\.venv\Scripts\research-agent run-agent-worker --loop
```

This repository keeps queueing, review records, publishing, knowledge capture, team library, schedules, and Data Lab workflows in the product runtime.
Model-provider setup is not part of the production surface.

## Security Baseline

- Cookie session only for the built-in frontend. Legacy bearer/session token fields remain for external scripts.
- CSRF protection uses the double-submit pattern:
  - cookie: `erp_csrf_token`
  - request header: `X-CSRF-Token`
- Production startup requires an explicit strong `APP_SECRET`.
- Default session lifetime is `72` hours.
- CORS is same-origin by default. Extra origins must be added explicitly through `ALLOWED_ORIGINS`.
- Password reset requires SMTP configuration and uses explicit SMTP transport mode.
- Uploads are limited to approved formats and a maximum payload of `25 MiB`.

## Core Environment Variables

```env
APP_NAME=Economic Research Platform
APP_ENV=development
APP_SECRET=
DATABASE_URL=sqlite:///./storage/platform.db
STORAGE_DIR=storage
ASSET_STORAGE_BACKEND=local
RESEARCH_AGENT_REPORTS_DIR=storage/reports
PUBLIC_BASE_URL=http://127.0.0.1:8000
ENCRYPTION_KEY=
CRON_SECRET=

SESSION_TTL_HOURS=72
ALLOWED_ORIGINS=http://127.0.0.1:8000
TRUSTED_PROXY_IPS=

SMTP_HOST=
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_SECURITY=ssl
PASSWORD_RESET_TTL_MINUTES=30

DB_POOL_SIZE=8
DB_MAX_OVERFLOW=16
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=research-assets

# Compatibility-only / optional. The current production build does not execute inference at runtime.
# RESEARCH_AGENT_MODEL=qwen2.5:7b-instruct
# RESEARCH_AGENT_REASONING_EFFORT=medium

# Training-only / optional. Render production does not require this.
OPENAI_API_KEY=

GDELT_QUERY='"inflation" OR "interest rate" OR "central bank" OR "bond yield" OR "oil price" OR "tariff" OR "unemployment" OR "recession" OR "GDP" OR "trade"'
GDELT_MAX_RECORDS=15
DEFAULT_FRED_SERIES=FEDFUNDS,CPIAUCSL,UNRATE,DGS10
FRED_API_KEY=
PUBLIC_DIGEST_ENABLED=true
PUBLIC_DIGEST_TIMEZONE=Asia/Shanghai
PUBLIC_DIGEST_LOCAL_TIME=08:30
PUBLIC_DIGEST_TITLE=Global Economic Daily
PUBLIC_DIGEST_QUERY=
PUBLIC_DIGEST_MAX_RECORDS=30

DATA_LAB_AGENT_ENABLED=false
DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED=false
DATA_LAB_AGENT_MAX_ATTEMPTS=3
DATA_LAB_AGENT_TIMEOUT_SECONDS=20
DATA_LAB_AGENT_OUTPUT_LIMIT=12000
DATA_LAB_AGENT_EXECUTION_MODE=subprocess_replay
DATA_LAB_AGENT_IPYTHON_ENABLED=false
DATA_LAB_AGENT_LLM_ENABLED=false
DATA_LAB_AGENT_LLM_BASE_URL=
DATA_LAB_AGENT_LLM_API_KEY=
DATA_LAB_AGENT_CODER_MODEL=
DATA_LAB_AGENT_REVIEWER_MODEL=
DATA_LAB_AGENT_REPORT_MODEL=
DATA_LAB_AGENT_LLM_TIMEOUT_SECONDS=45

AGENT_MATH_MODE=off
AGENT_MATH_DELIVERY_THRESHOLD=0.85
AGENT_MATH_HUMAN_THRESHOLD=0.55
AGENT_MATH_OVERRIDE_MARGIN=0.05
```

Notes:

- Keep the whole `GDELT_QUERY` expression inside a single quoted string. This avoids `python-dotenv` parse warnings.
- Never commit or store real secrets in `.env`. Use placeholders in the repo and real values only in local or deployment secrets.
- Set `APP_SECRET` explicitly in every real environment. Development can run without it, but production should never rely on an implicit secret.
- Use `SMTP_SECURITY=ssl` with port `465` by default. Set `SMTP_SECURITY=starttls` only when your mail provider requires explicit STARTTLS, typically on port `587`.
- Rotate any leaked database, Supabase, or session credentials outside the codebase. The application can prevent future leaks, but it cannot rotate external secrets for you.

## Useful CLI Commands

```powershell
.\.venv\Scripts\research-agent doctor
.\.venv\Scripts\research-agent create-user your@email.com
.\.venv\Scripts\research-agent run-due-jobs
.\.venv\Scripts\research-agent run-agent-worker --loop
.\.venv\Scripts\research-agent prune-security-state
.\.venv\Scripts\research-agent scan-hygiene
.\.venv\Scripts\research-agent smoke-deploy --base-url https://economic-research-web.onrender.com
.\.venv\Scripts\python.exe scripts\verify_render_deploy.py --commit <commit_sha> --base-url https://economic-research-web.onrender.com --output output/render-deploy/render-deploy.<commit_sha>.json
```

- `prune-security-state` removes expired sessions, used or expired password reset tokens, and stale login-attempt rows.
- `scan-hygiene` scans the repository root for leaked secrets and stray temp artifacts.
- `doctor` reports business-platform configuration and upstream reachability only. It does not inspect model runtimes.

## Workflow Loop

- Schedule records now expose latest run state, failure summary, recent run list, and run count.
- Schedule management supports enable or disable, delete, and manual `run-now` execution from both API and frontend.
- Briefing records carry schedule context so a run can jump directly to the generated briefing and linked knowledge note.
- Knowledge, literature, case, processing, model, and optimization payloads expose a shared status contract: `status`, `reason`, `next_action`, and `detail_path`.
- Data Lab history is now a unified workspace feed across preparation, model, optimization, and Data Lab Agent outputs. `/data-lab/history` and the workspace shell read from the same source.
- Data Lab Agent is disabled by default. When `DATA_LAB_AGENT_ENABLED=true`, it runs clean-room natural-language analysis through bounded Python execution with safety checks, profile snapshots, knowledge cards, repair traces, human intervention, and report/notebook export. Scoped model configuration lives under the Data Lab Agent APIs and does not reopen the general provider center.
- The internal ARBITER math kernel is gated by `AGENT_MATH_MODE=off|shadow|active`. `shadow` computes retrieval / control / delivery traces without changing the public workflow, while `active` lets those surrogates influence candidate ranking, intervention, and delivery gating.
- `AGENT_MATH_OVERRIDE_MARGIN` sets the minimum v2 advantage required before `active` overrides a baseline choice.

## Workflow APIs

- `PATCH /api/workspaces/{workspace_id}/schedules/{schedule_id}`
- `DELETE /api/workspaces/{workspace_id}/schedules/{schedule_id}`
- `POST /api/workspaces/{workspace_id}/schedules/{schedule_id}/run-now`
- `GET /api/workspaces/{workspace_id}/schedules/{schedule_id}/runs`
- `GET /api/workspaces/{workspace_id}/job-runs`
- `GET /api/workspaces/{workspace_id}/data-lab/history`
- `GET /api/workspaces/{workspace_id}/data-lab/agent/llm-config`
- `PUT /api/workspaces/{workspace_id}/data-lab/agent/llm-config`
- `POST /api/workspaces/{workspace_id}/data-lab/agent/llm-config/test`
- `POST /api/workspaces/{workspace_id}/data-lab/agent/sessions`
- `POST /api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/messages`
- `GET /api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}`
- `POST /api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/report`
- `POST /api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/notebook` generates the notebook artifact and requires CSRF for cookie sessions.
- `GET /api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/notebook` downloads an existing notebook artifact only.
- `POST /api/internal/run-due-jobs`

The internal scheduler endpoint requires `X-Cron-Secret` and is intentionally excluded from OpenAPI. Use it from a trusted scheduler only.

## Research Docs

- Agent mathematics research pack: [docs/agent_math/README.md](./docs/agent_math/README.md)

## Scheduled Execution

For deployed environments, align these pieces together:

- Set `PUBLIC_BASE_URL` to the externally reachable base URL.
- Set `CRON_SECRET` explicitly. If omitted, the app derives one from `APP_SECRET`, which is acceptable for local use but less explicit for shared operations.
- Set `PUBLIC_DIGEST_*` values to the wall-clock schedule and timezone you want for the public briefing.
- Set `FRED_API_KEY` if schedule-generated briefings should include FRED snapshots.
- Trigger `POST /api/internal/run-due-jobs` on a cadence from GitHub Actions or another scheduler. The repo already includes `.github/workflows/run-due-jobs.yml`.

## Render Deployment

- `render.yaml` is the production contract for the single Render web service.
- The Render build must produce `frontend-spa/dist` before the Python app starts, so `/app` is always served by FastAPI from the built SPA assets.
- Production quality paths require a commit-bound engineering gate artifact. The app resolves the runtime commit from `RESEARCH_AGENT_ENGINEERING_GATE_COMMIT`, `RENDER_GIT_COMMIT`, `GITHUB_SHA`, `COMMIT_SHA`, or `SOURCE_VERSION`; if no matching artifact is found under `RESEARCH_AGENT_ENGINEERING_GATE_ARTIFACT`, `ENGINEERING_GATE_ARTIFACT_DIR`, or `STORAGE_DIR/quality/gates`, quality delivery gates fail closed.
- Render production must not define runtime inference variables such as `RESEARCH_AGENT_MODEL` or require `OPENAI_API_KEY`.
- Render defaults should keep `RESEARCH_RUNTIME_ENABLED=false`, `DATA_LAB_AGENT_ENABLED=false`, `DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED=false`, and `AGENT_MATH_MODE=shadow`, with delivery threshold and override margin configured explicitly in environment variables.
- Data Lab Agent Python execution is trusted local execution, not a sandbox. Only enable `DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED=true` in an authorized deployment that accepts that risk boundary.
- Main branch is the only release source. Merge only after the delivery gate and real workspace publish validation both pass.

## Release Gate

Run this sequence before merging to main:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend-spa
npm.cmd run test
npm.cmd run build
Set-Location ..
.\.venv\Scripts\research-agent review-delivery --workspace-id <workspace_id> --resource-type agent_run --resource-id <run_id>
.\.venv\Scripts\research-agent review-delivery --workspace-id <workspace_id> --resource-type knowledge_record --resource-id <record_id>
```

Release is complete only after:

- the engineering gate is fully green
- the uploaded engineering gate artifact contains the exact commit SHA and the critical gate checks, including backend pytest, frontend tests, frontend build, SPA shell asset validation, agent quality gate, and model engine comparison
- one real `AgentRun` passes delivery review and publishes successfully
- one real `KnowledgeRecord` passes delivery review and publishes successfully
- the deployed Render smoke report covers `/api/auth/me`, `/api/health`, `/app`, `/app/quality`, `/app/data-lab-agent`, and `/provider-center`; deep smoke additionally verifies authenticated `/api/auth/me`, workspace creation, upload, and quality scorecard access

## Testing

Static checks:

```powershell
node --check src/research_agent/web/app.js
node --check src/research_agent/web/locale_runtime.js
node --check src/research_agent/web/locale_init.js
python -m compileall src tests scripts
```

Automated tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`pytest` is intentionally scoped to the repo's `tests/` directory. Vendored `_import/` libraries are excluded from collection.

Live verification scripts:

```powershell
.\.venv\Scripts\python.exe scripts/verify_access_gate.py
.\.venv\Scripts\python.exe scripts/verify_security_and_literature.py
.\.venv\Scripts\python.exe scripts/verify_workbench_and_knowledge.py
.\.venv\Scripts\python.exe scripts/verify_public_monitor.py
.\.venv\Scripts\python.exe scripts/verify_data_lab.py
.\.venv\Scripts\python.exe scripts/verify_optimization_lab.py
.\.venv\Scripts\python.exe scripts/export_monte_carlo_site_audit.py
```

## Main Routes

- `/` public entry and authentication
- `/app/overview` SPA workspace command center
- `/app/data-lab` SPA Data Lab hub for legacy workbench routes, agent runtime, and recent activity
- `/app/data-lab-agent` SPA Data Lab Agent workspace
- `/workspace` private cockpit
- `/schedules` schedule list and recent execution state
- `/provider-center` disabled placeholder explaining that runtime provider management is out of scope
- `/paper-library` literature search and import
- `/knowledge-base` notes and case workflow
- `/public-monitor` public monitor and rolling summaries
- `/data-lab` dataset intake
- `/data-lab/preparation` preparation workflow
- `/data-lab/model` model and chart execution
- `/data-lab/results` latest result reading and export
- `/data-lab/history` run history
- `/data-lab` legacy full Data Lab workbench
- `/data-lab/optimization` optimization suite
