from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import requests
import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from sqlalchemy import and_, select

from .agent_diagnostics import build_agent_eval_dataset_preview
from .orchestration_prompts import (
    PLANNER_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    WRITER_INSTRUCTIONS,
)
from .config import get_settings
from .db import init_database, session_scope
from .auth_support import purge_expired_sessions, purge_stale_login_attempts, purge_used_or_expired_reset_tokens
from .entities import AgentRun, KnowledgeRecord, User, Workspace
from .platform_core import list_workspaces, register_user, serialize_workspace, serialize_user
from .platform_research import ensure_public_daily_briefing, run_due_schedule_jobs, serialize_public_briefing
from .quality_center import (
    build_delivery_scorecard,
    review_agent_run_delivery,
    review_knowledge_record_delivery,
)
from .repo_hygiene import scan_repo_hygiene
from .service import run_agent_worker_iteration


app = typer.Typer(help="Economic research platform CLI.")
console = Console()


def _write_stdout_json(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")


def _load_workspace_agent_runs(*, workspace_id: str, limit: int, status: str) -> list[AgentRun]:
    normalized_status = status.strip().lower()
    with session_scope() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if workspace is None:
            console.print(f"[red]Workspace not found: {workspace_id}[/red]")
            raise typer.Exit(code=1)
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc(), AgentRun.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        if normalized_status:
            stmt = stmt.where(AgentRun.status == normalized_status)
        return list(db.scalars(stmt))


def _write_agent_eval_export(
    *,
    payload: dict[str, object],
    output: str,
    settings,
    workspace_id: str,
    default_filename: str,
    title: str,
) -> Path:
    output_path = (
        Path(output).expanduser().resolve()
        if output.strip()
        else (settings.storage_dir / "agent-evals" / default_filename).resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"workspace_id={workspace_id}",
                    f"output={output_path}",
                    f"dataset_version={payload.get('dataset_version', 'unknown') if isinstance(payload, dict) else 'unknown'}",
                    f"count={summary.get('count', 0)}",
                    f"approved={summary.get('approved_count', 0)}",
                    f"blocked={summary.get('blocked_count', 0)}",
                    f"ready_for_prompt_optimizer={summary.get('ready_for_prompt_optimizer_count', 0)}",
                    f"needs_human_annotation={summary.get('needs_human_annotation_count', 0)}",
                ]
            ),
            title=title,
        )
    )
    return output_path


def _load_workspace_context(*, workspace_id: str) -> tuple[Workspace, User]:
    with session_scope() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if workspace is None:
            console.print(f"[red]Workspace not found: {workspace_id}[/red]")
            raise typer.Exit(code=1)
        user = db.scalar(select(User).where(User.id == workspace.owner_user_id))
        if user is None:
            console.print(f"[red]Workspace owner not found for: {workspace_id}[/red]")
            raise typer.Exit(code=1)
        return workspace, user


def _prompt_optimizer_payload(runs: list[AgentRun]) -> dict[str, object]:
    blocked_runs = [run for run in runs if (run.status or "").strip().lower() == "blocked"]
    blocked_reasons: dict[str, int] = {}
    for run in blocked_runs:
        review_json = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
        findings = list(review_json.get("findings") or [])
        if findings:
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                code = str(finding.get("code") or "unknown").strip() or "unknown"
                blocked_reasons[code] = blocked_reasons.get(code, 0) + 1
        else:
            code = str(review_json.get("summary") or "blocked").strip() or "blocked"
            blocked_reasons[code] = blocked_reasons.get(code, 0) + 1
    optimization_notes = [
        "Always preserve strict citation coverage for every substantive claim.",
        "Never cite source IDs outside the evidence pack or attachment evidence.",
        "Prefer rejecting weakly supported sections instead of filling with generic prose.",
    ]
    for code, count in sorted(blocked_reasons.items(), key=lambda item: (-item[1], item[0]))[:6]:
        optimization_notes.append(f"Observed blocker `{code}` {count} time(s); strengthen instructions against it.")
    return {
        "summary": {
            "run_count": len(runs),
            "blocked_run_count": len(blocked_runs),
            "blocked_reason_frequency": blocked_reasons,
        },
        "optimized_prompts": {
            "planner": "\n\n".join([PLANNER_INSTRUCTIONS, "Optimization notes:\n- " + "\n- ".join(optimization_notes)]),
            "researcher": "\n\n".join([RESEARCHER_INSTRUCTIONS, "Optimization notes:\n- Rank evidence freshness and relevance before summarizing."]),
            "writer": "\n\n".join([WRITER_INSTRUCTIONS, "Optimization notes:\n- Every analytical paragraph must explicitly cite evidence IDs."]),
            "reviewer": "\n\n".join([REVIEWER_INSTRUCTIONS, "Optimization notes:\n- Block any unsupported or weakly grounded paragraph without exception."]),
        },
        "rubric": {
            "planner": {
                "must_emit_structured_queries": True,
                "must_include_required_sections": True,
            },
            "reviewer": {
                "block_on_invalid_source_ids": True,
                "block_on_missing_sections": True,
                "block_on_unsupported_claims": True,
            },
        },
    }

@app.command("init-db")
def init_db() -> None:
    """Initialize local database tables."""
    settings = get_settings()
    init_database()
    console.print(f"Initialized database at {settings.database_url}")


@app.command()
def doctor() -> None:
    """Validate configuration and primary external dependencies."""
    settings = get_settings()
    checks: list[str] = [
        f"App: {settings.app_name}",
        f"Environment: {settings.app_env}",
        f"Database: {settings.database_url}",
        f"Asset storage backend: {settings.asset_storage_backend}",
        f"Storage: {settings.storage_dir}",
        f"Reports dir: {settings.reports_dir}",
        f"Public base URL: {settings.public_base_url or 'missing'}",
        f"Allowed origins: {len(settings.allowed_origin_list)} configured",
        f"SMTP: {'configured' if settings.smtp_is_configured else 'missing'} ({settings.smtp_security})",
        f"Cron trigger secret: {'explicit' if settings.cron_secret.strip() else 'derived from APP_SECRET'}",
        (
            "Public digest: "
            f"{'enabled' if settings.public_digest_enabled else 'disabled'} "
            f"({settings.public_digest_timezone} {settings.public_digest_local_time})"
        ),
        f"FRED API key: {'configured' if settings.fred_api_key.strip() else 'missing'}",
    ]
    if settings.uses_supabase_asset_storage:
        checks.append(f"Supabase storage config: {'ok' if settings.has_supabase_storage_config else 'missing'}")

    def _append_http_check(label: str, url: str, *, params: dict[str, object]) -> None:
        try:
            response = requests.get(url, params=params, timeout=15)
        except Exception as exc:  # pragma: no cover
            checks.append(f"{label}: failed ({exc})")
            return
        if 200 <= response.status_code < 400:
            checks.append(f"{label}: ok ({response.status_code})")
            return
        checks.append(f"{label}: failed ({response.status_code})")

    _append_http_check(
        "OpenAlex",
        "https://api.openalex.org/works",
        params={"search": "monetary policy", "per-page": 1},
    )
    _append_http_check(
        "World Bank API",
        "https://api.worldbank.org/v2/country/US/indicator/FP.CPI.TOTL.ZG",
        params={"format": "json", "per_page": 1},
    )

    console.print(Panel.fit("\n".join(checks), title="Platform Doctor"))


@app.command("create-user")
def create_user(
    email: str = typer.Argument(..., help="User email."),
    full_name: str = typer.Option(..., prompt=True, help="Display name."),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True, help="Password."),
) -> None:
    """Create a user account directly from the CLI."""
    init_database()
    try:
        with session_scope() as db:
            user = register_user(db, email=email, password=password, full_name=full_name)
            workspaces = [serialize_workspace(item) for item in list_workspaces(db, user=user)]
            console.print(Panel.fit(f"{serialize_user(user)}\nworkspaces={workspaces}", title="User Created"))
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("run-due-jobs")
def run_jobs() -> None:
    """Run scheduled jobs that are due now."""
    settings = get_settings()
    init_database()
    with session_scope() as db:
        public_briefing = ensure_public_daily_briefing(db, settings)
        results = run_due_schedule_jobs(db, settings)
    console.print(
        Panel.fit(
            str(
                {
                    "public_briefing": serialize_public_briefing(public_briefing) if public_briefing else None,
                    "items": results,
                }
            ),
            title="Scheduled Jobs",
        )
    )


@app.command("run-agent-worker")
def run_agent_worker(
    limit: int = typer.Option(1, help="Maximum queued research runs to process."),
    worker_id: str = typer.Option("cli-worker", help="Worker identifier written onto claimed runs."),
    loop: bool = typer.Option(False, help="Keep polling for queued runs."),
    poll_seconds: int = typer.Option(5, help="Sleep interval between loop iterations."),
) -> None:
    """Process queued research-agent runs from the database-backed worker queue."""
    settings = get_settings()
    init_database()
    processed: list[dict[str, object] | None] = []
    if loop:
        console.print(Panel.fit(f"worker_id={worker_id}\nloop=true\npoll_seconds={poll_seconds}", title="Research Worker Loop"))
        try:
            while True:
                with session_scope() as db:
                    result = run_agent_worker_iteration(settings=settings, db=db, worker_id=worker_id)
                if result is not None:
                    processed.append(result)
                    console.print(json.dumps(result, ensure_ascii=False, indent=2))
                time.sleep(max(1, poll_seconds))
        except KeyboardInterrupt:
            pass
    else:
        with session_scope() as db:
            for _ in range(max(1, limit)):
                result = run_agent_worker_iteration(settings=settings, db=db, worker_id=worker_id)
                if result is None:
                    break
                processed.append(result)
    console.print(
        Panel.fit(
            json.dumps(
                {
                    "processed": len(processed),
                    "items": processed,
                },
                ensure_ascii=False,
                indent=2,
            ),
            title="Research Worker",
        )
    )


@app.command("prune-security-state")
def prune_security_state() -> None:
    """Delete expired sessions, reset tokens, and stale login attempt rows."""
    init_database()
    with session_scope() as db:
        deleted_sessions = purge_expired_sessions(db)
        deleted_reset_tokens = purge_used_or_expired_reset_tokens(db)
        deleted_login_attempts = purge_stale_login_attempts(db)
    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"expired_sessions={deleted_sessions}",
                    f"expired_reset_tokens={deleted_reset_tokens}",
                    f"stale_login_attempts={deleted_login_attempts}",
                ]
            ),
            title="Security State Pruned",
        )
    )


@app.command("scan-hygiene")
def scan_hygiene(
    root: str = typer.Option(".", help="Repository root to scan."),
) -> None:
    """Scan the repository root for leaked credentials and stray temp artifacts."""
    issues = scan_repo_hygiene(Path(root).resolve())
    if not issues:
        console.print(Panel.fit("No hygiene issues found.", title="Repo Hygiene"))
        return
    lines = []
    for item in issues:
        location = item["path"]
        if item.get("line_number"):
            location = f"{location}:{item['line_number']}"
        lines.append(f"{item['kind']}: {item['label']} ({location})")
    console.print(Panel.fit("\n".join(lines), title="Repo Hygiene Issues"))
    raise typer.Exit(code=1)


@app.command("export-agent-evals")
def export_agent_evals(
    workspace_id: str = typer.Argument(..., help="Workspace ID to export."),
    limit: int = typer.Option(50, help="Maximum number of recent agent runs to export."),
    status: str = typer.Option("", help="Optional run status filter, for example saved or blocked."),
    output: str = typer.Option("", help="Optional output file path."),
) -> None:
    """Export recent agent runs into an eval-candidate JSON preview."""
    settings = get_settings()
    init_database()
    runs = _load_workspace_agent_runs(workspace_id=workspace_id, limit=limit, status=status)
    payload = build_agent_eval_dataset_preview(runs)
    _write_agent_eval_export(
        payload=payload,
        output=output,
        settings=settings,
        workspace_id=workspace_id,
        default_filename=f"{workspace_id}-eval-preview.json",
        title="Agent Eval Export",
    )


@app.command("export-agent-eval-dataset")
def export_agent_eval_dataset(
    workspace_id: str = typer.Argument(..., help="Workspace ID to export."),
    limit: int = typer.Option(100, help="Maximum number of recent agent runs to include."),
    status: str = typer.Option("", help="Optional run status filter, for example saved or blocked."),
    output: str = typer.Option("", help="Optional output file path."),
) -> None:
    """Export a v2 research-agent eval dataset built from persisted agent runs."""
    settings = get_settings()
    init_database()
    runs = _load_workspace_agent_runs(workspace_id=workspace_id, limit=limit, status=status)
    payload = build_agent_eval_dataset_preview(runs)
    _write_agent_eval_export(
        payload=payload,
        output=output,
        settings=settings,
        workspace_id=workspace_id,
        default_filename=f"{workspace_id}-eval-dataset.json",
        title="Agent Eval Dataset",
    )


@app.command("optimize-agent-prompts")
def optimize_agent_prompts(
    workspace_id: str = typer.Argument(..., help="Workspace ID to analyze."),
    limit: int = typer.Option(50, help="Maximum number of recent runs to inspect."),
    output: str = typer.Option("", help="Optional output file path."),
) -> None:
    """Generate offline prompt and rubric optimization suggestions from recent runs."""
    settings = get_settings()
    init_database()
    runs = _load_workspace_agent_runs(workspace_id=workspace_id, limit=limit, status="")
    payload = _prompt_optimizer_payload(runs)
    output_path = (
        Path(output).expanduser().resolve()
        if output.strip()
        else (settings.storage_dir / "agent-optimizations" / workspace_id / "prompt-optimization.json").resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(Panel.fit(f"workspace_id={workspace_id}\noutput={output_path}\nblocked_run_count={payload['summary']['blocked_run_count']}", title="Prompt Optimizer"))


@app.command("review-delivery")
def review_delivery(
    workspace_id: str = typer.Option(..., help="Workspace ID to review."),
    resource_type: str = typer.Option("", help="Optional resource type: agent_run or knowledge_record."),
    resource_id: str = typer.Option("", help="Optional resource ID."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Run the full 100% delivery review gate for a workspace or a specific artifact."""
    settings = get_settings()
    init_database()
    resource_kind = resource_type.strip().lower()
    if bool(resource_kind) != bool(resource_id.strip()):
        console.print("[red]resource-type and resource-id must be provided together.[/red]")
        raise typer.Exit(code=1)
    with session_scope() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if workspace is None:
            console.print(f"[red]Workspace not found: {workspace_id}[/red]")
            raise typer.Exit(code=1)
        user = db.scalar(select(User).where(User.id == workspace.owner_user_id))
        if user is None:
            console.print(f"[red]Workspace owner not found for: {workspace_id}[/red]")
            raise typer.Exit(code=1)

        if resource_kind == "agent_run":
            run = db.scalar(
                select(AgentRun).where(
                    and_(
                        AgentRun.id == resource_id.strip(),
                        AgentRun.workspace_id == workspace.id,
                        AgentRun.owner_user_id == user.id,
                    )
                )
            )
            if run is None:
                console.print(f"[red]Agent run not found: {resource_id}[/red]")
                raise typer.Exit(code=1)
            delivery_review, engineering_gate = review_agent_run_delivery(
                run,
                settings=settings,
                refresh_engineering=True,
                auto_refresh_if_missing=True,
            )
            payload = {
                "workspace_id": workspace.id,
                "resource_type": resource_kind,
                "resource_id": run.id,
                "delivery_review": delivery_review,
                "engineering_gate": engineering_gate,
            }
            passed = bool(delivery_review.get("deliverable"))
        elif resource_kind == "knowledge_record":
            record = db.scalar(
                select(KnowledgeRecord).where(
                    and_(
                        KnowledgeRecord.id == resource_id.strip(),
                        KnowledgeRecord.workspace_id == workspace.id,
                        KnowledgeRecord.owner_user_id == user.id,
                    )
                )
            )
            if record is None:
                console.print(f"[red]Knowledge record not found: {resource_id}[/red]")
                raise typer.Exit(code=1)
            delivery_review, engineering_gate = review_knowledge_record_delivery(
                db,
                record,
                settings=settings,
                refresh_engineering=True,
                auto_refresh_if_missing=True,
            )
            payload = {
                "workspace_id": workspace.id,
                "resource_type": resource_kind,
                "resource_id": record.id,
                "delivery_review": delivery_review,
                "engineering_gate": engineering_gate,
            }
            passed = bool(delivery_review.get("deliverable"))
        else:
            payload = build_delivery_scorecard(
                db,
                user=user,
                workspace=workspace,
                settings=settings,
                refresh_engineering=True,
                auto_refresh_if_missing=True,
            )
            passed = bool(payload.get("deliverable"))

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if json_output:
        _write_stdout_json(rendered)
    else:
        console.print(Panel.fit(rendered, title="Delivery Review"))
    if not passed:
        raise typer.Exit(code=1)


@app.command("smoke-deploy")
def smoke_deploy(
    base_url: str = typer.Option(..., help="Public deployment base URL, for example https://example.onrender.com"),
    output: str = typer.Option("", help="Optional JSON output path."),
    expect_authenticated: bool = typer.Option(
        False,
        help="Require authenticated SPA routes to return 200 instead of allowing login redirects.",
    ),
    deep: bool = typer.Option(False, "--deep", help="Run optional authenticated registration/login/workspace/upload/quality checks."),
    register: bool = typer.Option(False, "--register", help="Create a smoke-test account before authenticated checks."),
    auth_email: str = typer.Option("", help="Email for authenticated smoke checks."),
    auth_password: str = typer.Option("", help="Password for authenticated smoke checks."),
) -> None:
    """Smoke-test a deployed web surface after Render finishes deploying."""
    try:
        payload = _run_deploy_smoke(
            base_url=base_url,
            expect_authenticated=expect_authenticated,
            deep=deep or register,
            register=register,
            auth_email=auth_email,
            auth_password=auth_password,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if output.strip():
        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    console.print(Panel.fit(rendered, title="Deploy Smoke"))
    if not payload["passed"]:
        raise typer.Exit(code=1)


def _run_deploy_smoke(
    *,
    base_url: str,
    expect_authenticated: bool = False,
    deep: bool = False,
    register: bool = False,
    auth_email: str = "",
    auth_password: str = "",
) -> dict[str, Any]:
    normalized_base_url = base_url.strip().rstrip("/")
    if not normalized_base_url.startswith(("http://", "https://")):
        raise ValueError("base-url must start with http:// or https://")

    checks: list[dict[str, object]] = []
    session = requests.Session()

    def _record(path: str, *, passed: bool, status_code: int, detail: str = "") -> None:
        checks.append(
            {
                "path": path,
                "passed": passed,
                "status_code": status_code,
                "detail": detail,
            }
        )

    def _try_request(path: str, *, allow_redirects: bool = False) -> requests.Response | None:
        try:
            return session.get(f"{normalized_base_url}{path}", timeout=20, allow_redirects=allow_redirects)
        except Exception as exc:
            _record(path, passed=False, status_code=0, detail=str(exc))
            return None

    def _auth_headers(token: str = "") -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    anonymous_me = _try_request("/api/auth/me", allow_redirects=False)
    if anonymous_me is not None:
        _record(
            "/api/auth/me",
            passed=anonymous_me.status_code == 401,
            status_code=anonymous_me.status_code,
            detail="anonymous 401" if anonymous_me.status_code == 401 else anonymous_me.text[:200],
        )

    health = _try_request("/api/health", allow_redirects=True)
    if health is not None:
        health_ok = health.status_code == 200
        try:
            health_payload = health.json() if health_ok else {}
        except Exception:
            health_payload = {}
        _record(
            "/api/health",
            passed=health_ok and health_payload.get("status") == "ok",
            status_code=health.status_code,
            detail=str(health_payload or health.text[:200]),
        )

    provider_center = _try_request("/provider-center", allow_redirects=True)
    if provider_center is not None:
        provider_detail = provider_center.text[:200]
        _record(
            "/provider-center",
            passed=provider_center.status_code == 200
            and "not part of the current product scope" in provider_center.text.lower(),
            status_code=provider_center.status_code,
            detail=provider_detail,
        )

    for path in ("/app", "/app/research", "/app/knowledge", "/app/quality", "/app/data-lab-agent"):
        response = _try_request(path, allow_redirects=False)
        if response is None:
            continue
        location = response.headers.get("location", "")
        built_spa_assets = "/app/assets/" in response.text and "/src/main.tsx" not in response.text
        if expect_authenticated:
            passed = response.status_code == 200 and built_spa_assets
            detail = "built_spa_assets" if passed else response.text[:200]
        else:
            passed = (response.status_code == 200 and built_spa_assets) or (response.status_code == 307 and location == "/")
            if response.status_code == 200 and "/src/main.tsx" in response.text:
                detail = "SPA shell still references /src/main.tsx"
            else:
                detail = location or ("built_spa_assets" if built_spa_assets else response.text[:200])
        _record(
            path,
            passed=passed,
            status_code=response.status_code,
            detail=detail,
        )

    auth_payload: dict[str, object] = {"enabled": bool(deep), "registered": False}
    if deep:
        token = ""
        email = auth_email.strip()
        password = auth_password.strip()
        if register:
            email = email or f"deploy-smoke-{int(time.time())}-{secrets.token_hex(3)}@example.invalid"
            password = password or f"SmokePass-{secrets.token_urlsafe(12)}!A1"
            try:
                register_response = session.post(
                    f"{normalized_base_url}/api/auth/register",
                    timeout=20,
                    headers={"Origin": normalized_base_url},
                    json={"full_name": "Deploy Smoke", "email": email, "password": password},
                )
                token = session.cookies.get("erp_session_token", "")
                auth_payload["registered"] = register_response.status_code == 200
                _record(
                    "/api/auth/register",
                    passed=register_response.status_code == 200 and bool(token),
                    status_code=register_response.status_code,
                    detail="registered" if register_response.status_code == 200 else register_response.text[:200],
                )
            except Exception as exc:
                _record("/api/auth/register", passed=False, status_code=0, detail=str(exc))
        else:
            if not email or not password:
                _record(
                    "/api/auth/login",
                    passed=False,
                    status_code=0,
                    detail="--deep requires --auth-email and --auth-password unless --register is used.",
                )
            else:
                try:
                    login_response = session.post(
                        f"{normalized_base_url}/api/auth/login",
                        timeout=20,
                        headers={"Origin": normalized_base_url},
                        json={"email": email, "password": password},
                    )
                    token = session.cookies.get("erp_session_token", "")
                    _record(
                        "/api/auth/login",
                        passed=login_response.status_code == 200 and bool(token),
                        status_code=login_response.status_code,
                        detail="logged_in" if login_response.status_code == 200 else login_response.text[:200],
                    )
                except Exception as exc:
                    _record("/api/auth/login", passed=False, status_code=0, detail=str(exc))

        auth_payload["email"] = email
        auth_payload["has_session"] = bool(token)
        workspace_id = ""
        if token:
            me_response = _try_request("/api/auth/me", allow_redirects=False)
            if me_response is not None:
                try:
                    me_payload = me_response.json()
                except Exception:
                    me_payload = {}
                _record(
                    "/api/auth/me#authenticated",
                    passed=me_response.status_code == 200 and bool((me_payload.get("user") or {}).get("email")),
                    status_code=me_response.status_code,
                    detail=str((me_payload.get("user") or {}).get("email") or me_response.text[:200]),
                )
            try:
                workspace_response = session.post(
                    f"{normalized_base_url}/api/workspaces",
                    timeout=20,
                    headers=_auth_headers(token),
                    json={
                        "name": f"Deploy Smoke {int(time.time())}",
                        "description": "Automated deploy smoke workspace.",
                        "research_domain": "economics",
                    },
                )
                workspace_payload = workspace_response.json() if workspace_response.status_code == 200 else {}
                workspace_id = str((workspace_payload.get("workspace") or {}).get("id") or "")
                _record(
                    "/api/workspaces",
                    passed=workspace_response.status_code == 200 and bool(workspace_id),
                    status_code=workspace_response.status_code,
                    detail=workspace_id or workspace_response.text[:200],
                )
            except Exception as exc:
                _record("/api/workspaces", passed=False, status_code=0, detail=str(exc))

        if token and workspace_id:
            try:
                upload_response = session.post(
                    f"{normalized_base_url}/api/workspaces/{workspace_id}/assets/upload",
                    timeout=30,
                    headers=_auth_headers(token),
                    data={"description": "deploy smoke csv", "source_url": ""},
                    files={"file": ("deploy_smoke.csv", b"x,y\n1,2\n", "text/csv")},
                )
                upload_payload = upload_response.json() if upload_response.status_code == 200 else {}
                asset_id = str((upload_payload.get("asset") or {}).get("id") or "")
                _record(
                    f"/api/workspaces/{workspace_id}/assets/upload",
                    passed=upload_response.status_code == 200 and bool(asset_id),
                    status_code=upload_response.status_code,
                    detail=asset_id or upload_response.text[:200],
                )
            except Exception as exc:
                _record(f"/api/workspaces/{workspace_id}/assets/upload", passed=False, status_code=0, detail=str(exc))

            quality_response = _try_request(f"/api/workspaces/{workspace_id}/quality/scorecard", allow_redirects=False)
            if quality_response is not None:
                try:
                    quality_payload = quality_response.json() if quality_response.status_code == 200 else {}
                except Exception:
                    quality_payload = {}
                engineering_gate = quality_payload.get("engineering_gate") if isinstance(quality_payload, dict) else {}
                gate_source = str((engineering_gate or {}).get("source") or "")
                _record(
                    f"/api/workspaces/{workspace_id}/quality/scorecard",
                    passed=quality_response.status_code == 200 and gate_source.startswith(("artifact:", "snapshot", "fresh")),
                    status_code=quality_response.status_code,
                    detail=gate_source or quality_response.text[:200],
                )

    return {
        "base_url": normalized_base_url,
        "expect_authenticated": expect_authenticated,
        "deep": auth_payload,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host for the web server."),
    port: int = typer.Option(8000, help="Port for the web server."),
    reload: bool = typer.Option(False, help="Enable auto-reload during development."),
) -> None:
    """Serve the production-oriented web application."""
    uvicorn.run(
        "research_agent.webapp:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
