# Project Rules For Codex

## Project Stack

- Backend: FastAPI / SQLAlchemy / Python
- Frontend SPA: React / Vite / TypeScript
- Legacy frontend: `src/research_agent/web/*.html` and `src/research_agent/web/app.js`
- Data Lab: dataset processing, econometric/statistical models, Data Lab Agent, Optimization Lab

## Required Commands

Backend:

- `python -m compileall src tests scripts`
- `python -m pytest -q`

Frontend:

- `cd frontend-spa && npm test`
- `cd frontend-spa && npm run build`

Verification:

- `python scripts/verify_data_lab.py`
- `python scripts/verify_optimization_lab.py`

## Forbidden Commits

Never commit:

- `.env`
- `storage/`
- `reports/`
- `output/`
- `frontend-spa/dist/`
- `frontend-spa/node_modules/`
- `node_modules/`
- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- real API keys, tokens, cookies, DB URLs, Supabase service role keys, private keys

## Security Rules

- Data Lab Agent trusted Python execution is not a sandbox.
- Do not enable trusted execution in production.
- Do not weaken CSRF, session, cookie, or upload validation.
- Production must not serve `/src/main.tsx`.
- SVG upload is forbidden.

## Data Lab Rules

- Do not add new models before fixing workflow, validation, and reproducibility.
- Model outputs must be reproducible.
- Preflight is required before treating model output as reliable.
- Optimization Lab must enforce resource limits.
