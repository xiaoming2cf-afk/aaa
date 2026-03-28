from __future__ import annotations

import requests
import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel

from .config import get_settings
from .db import init_database, session_scope
from .platform_core import list_workspaces, register_user, serialize_workspace, serialize_user
from .platform_research import ensure_public_daily_briefing, run_due_schedule_jobs, serialize_public_briefing


app = typer.Typer(help="Economic research platform CLI.")
console = Console()


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
        f"Model default: {settings.model}",
    ]
    if settings.uses_supabase_asset_storage:
        checks.append(f"Supabase storage config: {'ok' if settings.has_supabase_storage_config else 'missing'}")
    try:
        response = requests.get(
            "https://api.openalex.org/works",
            params={"search": "monetary policy", "per-page": 1},
            timeout=15,
        )
        checks.append(f"OpenAlex: ok ({response.status_code})")
    except Exception as exc:  # pragma: no cover
        checks.append(f"OpenAlex: failed ({exc})")
    try:
        response = requests.get(
            "https://api.worldbank.org/v2/country/US/indicator/FP.CPI.TOTL.ZG",
            params={"format": "json", "per_page": 1},
            timeout=15,
        )
        checks.append(f"World Bank API: ok ({response.status_code})")
    except Exception as exc:  # pragma: no cover
        checks.append(f"World Bank API: failed ({exc})")

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
