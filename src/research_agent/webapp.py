from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .asset_storage import is_remote_asset_reference, load_asset_bytes
from .config import get_settings
from .db import init_database, session_scope
from .entities import DataAsset
from .platform_core import (
    clean_dataset_asset,
    create_integration,
    create_knowledge_record,
    create_workspace,
    delete_integration,
    get_current_user,
    get_workspace_for_user,
    list_assets,
    list_integrations,
    list_knowledge_records,
    list_workspaces,
    login_user,
    register_user,
    resolve_integration,
    run_ols_analysis,
    save_upload_asset,
    search_assets,
    search_knowledge_records,
    serialize_asset,
    serialize_integration,
    serialize_knowledge_record,
    serialize_user,
    serialize_workspace,
    test_integration,
)
from .platform_research import (
    build_named_public_summary,
    build_public_briefing_summary,
    create_schedule_job,
    ensure_public_daily_briefing,
    generate_economic_briefing,
    get_latest_public_briefing,
    get_public_briefing_by_slug,
    import_openalex_works,
    list_briefings,
    list_literature_entries,
    list_public_briefings,
    list_schedule_jobs,
    run_due_schedule_jobs,
    search_openalex,
    serialize_briefing,
    serialize_literature_entry,
    serialize_public_briefing,
    serialize_public_briefing_detail,
    serialize_schedule,
)


WEB_DIR = Path(__file__).with_name("web")


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    research_domain: str = "economics"


class IntegrationCreateRequest(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    category: str = Field(default="llm", min_length=2, max_length=50)
    kind: str = Field(min_length=2, max_length=50)
    api_key: str = Field(min_length=2, max_length=400)
    base_url: str = ""
    model: str = ""
    is_default: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=2)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenAlexImportRequest(BaseModel):
    works: list[dict[str, Any]] = Field(default_factory=list)


class BriefingCreateRequest(BaseModel):
    query_text: str = ""
    title: str = ""
    integration_id: str | None = None


class ScheduleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    job_type: str = Field(default="economic_briefing", min_length=2, max_length=80)
    timezone_name: str = Field(default="Asia/Shanghai", min_length=2, max_length=80)
    local_time: str = Field(default="08:00", min_length=4, max_length=8)
    integration_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class OlsAnalysisRequest(BaseModel):
    asset_id: str
    dependent: str
    independents: list[str] = Field(default_factory=list)


def _token_from_headers(authorization: str | None, x_session_token: str | None) -> str:
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return (x_session_token or "").strip()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, requests.HTTPError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def create_app() -> FastAPI:
    settings = get_settings()
    init_database()
    app = FastAPI(title=settings.app_name)
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/briefings/{slug}")
    def public_briefing_page(slug: str) -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/summaries/{window}")
    def public_summary_page(window: str) -> FileResponse:
        if window not in {"weekly", "monthly"}:
            raise HTTPException(status_code=404, detail="Public summary page not found.")
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(WEB_DIR / "favicon.svg", media_type="image/svg+xml")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app_name": settings.app_name,
            "env": settings.app_env,
            "database_backend": settings.database_url.split(":", 1)[0],
            "asset_storage_backend": settings.asset_storage_backend,
            "features": [
                "auth",
                "workspaces",
                "multi_provider_llm",
                "private_knowledge_base",
                "data_assets",
                "openalex_library",
                "economic_briefings",
                "scheduled_jobs",
                "public_daily_briefings",
                "public_macro_summary",
            ],
        }

    @app.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return {
            "app_name": settings.app_name,
            "public_base_url": settings.public_base_url,
            "default_timezone": "Asia/Shanghai",
            "asset_storage_backend": settings.asset_storage_backend,
            "supported_llm_kinds": ["openai", "openai_compatible", "gemini", "anthropic"],
            "supported_data_kinds": ["fred"],
            "public_digest_enabled": settings.public_digest_enabled,
            "public_digest_timezone": settings.public_digest_timezone,
            "public_digest_local_time": settings.public_digest_local_time,
        }

    @app.get("/api/public/briefings")
    def public_briefings(limit: int = 10) -> dict[str, Any]:
        try:
            with session_scope() as db:
                ensure_public_daily_briefing(db, settings)
                return {
                    "items": [
                        serialize_public_briefing(item, public_base_url=settings.public_base_url)
                        for item in list_public_briefings(db, limit=limit)
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/briefings/latest")
    def public_briefing_latest() -> dict[str, Any]:
        try:
            with session_scope() as db:
                briefing = ensure_public_daily_briefing(db, settings) or get_latest_public_briefing(db)
                return {
                    "briefing": serialize_public_briefing_detail(db, briefing, public_base_url=settings.public_base_url)
                    if briefing
                    else None
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/briefings/{slug}")
    def public_briefing_detail(slug: str) -> dict[str, Any]:
        try:
            with session_scope() as db:
                briefing = get_public_briefing_by_slug(db, slug=slug)
                if not briefing:
                    raise FileNotFoundError("Public briefing not found.")
                return {"briefing": serialize_public_briefing_detail(db, briefing, public_base_url=settings.public_base_url)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/summary")
    def public_summary(days: int = 7) -> dict[str, Any]:
        try:
            with session_scope() as db:
                ensure_public_daily_briefing(db, settings)
                return build_public_briefing_summary(db, days=days, public_base_url=settings.public_base_url)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/summaries/{window}")
    def public_summary_detail(window: str) -> dict[str, Any]:
        try:
            with session_scope() as db:
                ensure_public_daily_briefing(db, settings)
                return build_named_public_summary(db, window=window, public_base_url=settings.public_base_url)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/register")
    def register(request: RegisterRequest) -> dict[str, Any]:
        try:
            with session_scope() as db:
                user = register_user(db, email=request.email, password=request.password, full_name=request.full_name)
                user, token = login_user(db, settings, email=request.email, password=request.password)
                return {
                    "user": serialize_user(user),
                    "session_token": token,
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/login")
    def login(request: LoginRequest) -> dict[str, Any]:
        try:
            with session_scope() as db:
                user, token = login_user(db, settings, email=request.email, password=request.password)
                return {
                    "user": serialize_user(user),
                    "session_token": token,
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/auth/me")
    def me(
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return {
                    "user": serialize_user(user),
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces")
    def workspaces(
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return {"items": [serialize_workspace(item) for item in list_workspaces(db, user=user)]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces")
    def add_workspace(
        request: WorkspaceCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = create_workspace(
                    db,
                    user=user,
                    name=request.name,
                    description=request.description,
                    research_domain=request.research_domain,
                )
                return {"workspace": serialize_workspace(workspace)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/integrations")
    def integrations(
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return {"items": [serialize_integration(item) for item in list_integrations(db, user=user)]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/integrations")
    def add_integration(
        request: IntegrationCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                integration = create_integration(
                    db,
                    settings,
                    user=user,
                    label=request.label,
                    category=request.category,
                    kind=request.kind,
                    api_key=request.api_key,
                    base_url=request.base_url,
                    model=request.model,
                    is_default=request.is_default,
                    config=request.config,
                )
                return {"integration": serialize_integration(integration)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/integrations/{integration_id}/test")
    def verify_integration(
        integration_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return test_integration(db, settings, user=user, integration_id=integration_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/integrations/{integration_id}")
    def remove_integration(
        integration_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                delete_integration(db, user=user, integration_id=integration_id)
                return {"status": "deleted"}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge")
    def knowledge(
        workspace_id: str,
        q: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = search_knowledge_records(db, user=user, workspace=workspace, query=q) if q.strip() else list_knowledge_records(db, user=user, workspace=workspace)
                return {"items": [serialize_knowledge_record(item) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge")
    def add_knowledge(
        workspace_id: str,
        request: KnowledgeCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = create_knowledge_record(
                    db,
                    user=user,
                    workspace=workspace,
                    title=request.title,
                    content=request.content,
                    tags=request.tags,
                    metadata=request.metadata,
                )
                return {"record": serialize_knowledge_record(record)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/assets")
    def assets(
        workspace_id: str,
        q: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = search_assets(db, user=user, workspace=workspace, query=q) if q.strip() else list_assets(db, user=user, workspace=workspace)
                return {"items": [serialize_asset(item) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/assets/upload")
    async def upload_asset(
        workspace_id: str,
        file: UploadFile = File(...),
        description: str = Form(default=""),
        source_url: str = Form(default=""),
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            payload = await file.read()
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                asset = save_upload_asset(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    filename=file.filename or "upload.bin",
                    content=payload,
                    content_type=file.content_type or "application/octet-stream",
                    description=description,
                    source_url=source_url,
                )
                return {"asset": serialize_asset(asset)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/assets/{asset_id}/download")
    def download_asset(
        asset_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                asset = db.get(DataAsset, asset_id)
                if not asset or asset.owner_user_id != user.id:
                    raise FileNotFoundError("Asset not found.")
                original_name = asset.metadata_json.get("original_filename") or Path(asset.title).name
                if not is_remote_asset_reference(asset.file_path):
                    return FileResponse(asset.file_path, filename=original_name, media_type=asset.content_type)
                payload = load_asset_bytes(settings, asset.file_path)
                return Response(
                    content=payload,
                    media_type=asset.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{original_name}"'},
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/assets/{asset_id}/clean")
    def clean_asset(
        workspace_id: str,
        asset_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return clean_dataset_asset(settings, db, user=user, workspace=workspace, asset_id=asset_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/ols")
    def ols_analysis(
        workspace_id: str,
        request: OlsAnalysisRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return run_ols_analysis(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_id=request.asset_id,
                    dependent=request.dependent,
                    independents=request.independents,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/openalex/search")
    def openalex_search(
        q: str,
        max_results: int = 10,
        open_access_only: bool = False,
    ) -> dict[str, Any]:
        try:
            return {
                "items": search_openalex(
                    query=q,
                    max_results=max_results,
                    open_access_only=open_access_only,
                )
            }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/literature")
    def literature(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {"items": [serialize_literature_entry(item) for item in list_literature_entries(db, user=user, workspace=workspace)]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/literature/import")
    def import_literature(
        workspace_id: str,
        request: OpenAlexImportRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                items = import_openalex_works(db, user=user, workspace=workspace, works=request.works)
                return {"items": [serialize_literature_entry(item) for item in items]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/briefings")
    def briefings(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {"items": [serialize_briefing(item) for item in list_briefings(db, user=user, workspace=workspace)]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/briefings/generate")
    def create_briefing(
        workspace_id: str,
        request: BriefingCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                if request.integration_id:
                    resolve_integration(db, user=user, integration_id=request.integration_id)
                briefing = generate_economic_briefing(
                    db,
                    settings,
                    user=user,
                    workspace=workspace,
                    integration_id=request.integration_id,
                    query_text=request.query_text,
                    title=request.title,
                )
                return {"briefing": serialize_briefing(briefing)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/schedules")
    def schedules(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {"items": [serialize_schedule(item) for item in list_schedule_jobs(db, user=user, workspace=workspace)]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/schedules")
    def add_schedule(
        workspace_id: str,
        request: ScheduleCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                if request.integration_id:
                    resolve_integration(db, user=user, integration_id=request.integration_id)
                schedule = create_schedule_job(
                    db,
                    user=user,
                    workspace=workspace,
                    name=request.name,
                    job_type=request.job_type,
                    timezone_name=request.timezone_name,
                    local_time_value=request.local_time,
                    integration_id=request.integration_id,
                    config=request.config,
                )
                return {"schedule": serialize_schedule(schedule)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/internal/run-due-jobs")
    def run_jobs(x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret")) -> dict[str, Any]:
        try:
            if (x_cron_secret or "").strip() != settings.get_cron_secret():
                raise PermissionError("Invalid cron secret.")
            with session_scope() as db:
                public_briefing = ensure_public_daily_briefing(db, settings)
                return {
                    "public_briefing": serialize_public_briefing(
                        public_briefing, public_base_url=settings.public_base_url
                    )
                    if public_briefing
                    else None,
                    "items": run_due_schedule_jobs(db, settings),
                }
        except Exception as exc:
            _raise_http_error(exc)

    return app
