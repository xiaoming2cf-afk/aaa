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
from .data_lab_catalog import get_data_lab_catalog, get_model_family, get_processing_family
from .db import init_database, session_scope
from .entities import DataAsset
from .platform_core import (
    build_model_result_detail,
    build_processing_result_detail,
    create_plot_asset,
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
    prepare_dataset_asset,
    profile_dataset_asset,
    register_user,
    resolve_integration,
    run_model_analysis,
    run_ols_analysis,
    save_upload_asset,
    search_assets,
    search_knowledge_records,
    serialize_asset,
    serialize_integration,
    serialize_knowledge_record,
    serialize_user,
    serialize_workspace,
    suggest_beginner_variable_plan,
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
PUBLIC_WEB_FILE = WEB_DIR / "public.html"
DATA_LAB_WEB_FILE = WEB_DIR / "data_lab.html"
DATA_LAB_DETAIL_WEB_FILE = WEB_DIR / "data_lab_detail.html"
DATA_LAB_RESULT_WEB_FILE = WEB_DIR / "data_lab_result.html"


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
    robust_covariance: bool = True


class DatasetPrepareRequest(BaseModel):
    asset_id: str
    workflow_group: str = Field(default="sample_preparation")
    include_columns: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    binary_columns: list[str] = Field(default_factory=list)
    date_columns: list[str] = Field(default_factory=list)
    impute_columns: list[str] = Field(default_factory=list)
    impute_method: str = Field(default="none")
    winsorize_columns: list[str] = Field(default_factory=list)
    winsor_lower_quantile: float = 0.01
    winsor_upper_quantile: float = 0.99
    log_transform_columns: list[str] = Field(default_factory=list)
    standardize_columns: list[str] = Field(default_factory=list)
    minmax_scale_columns: list[str] = Field(default_factory=list)
    outlier_columns: list[str] = Field(default_factory=list)
    outlier_method: str = Field(default="none")
    outlier_threshold: float = 1.5
    sort_column: str = ""
    time_group_column: str = ""
    difference_columns: list[str] = Field(default_factory=list)
    return_columns: list[str] = Field(default_factory=list)
    return_method: str = Field(default="simple")
    lag_columns: list[str] = Field(default_factory=list)
    lag_periods: int = 1
    lead_columns: list[str] = Field(default_factory=list)
    lead_periods: int = 1
    rolling_mean_columns: list[str] = Field(default_factory=list)
    rolling_volatility_columns: list[str] = Field(default_factory=list)
    rolling_window: int = 5
    drop_duplicates: bool = True
    drop_missing_required: bool = True


class ModelRunRequest(BaseModel):
    asset_id: str
    model_family: str = ""
    model_type: str = Field(default="ols")
    dependent: str = ""
    independents: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    series_columns: list[str] = Field(default_factory=list)
    treatment_column: str = ""
    post_column: str = ""
    event_time_column: str = ""
    lead_window: int = 4
    lag_window: int = 4
    omitted_period: int = -1
    origin_mass_column: str = ""
    destination_mass_column: str = ""
    distance_column: str = ""
    running_column: str = ""
    rdd_cutoff: float = 0.0
    rdd_bandwidth: float = 0.0
    rdd_polynomial_order: int = 1
    treat_above_cutoff: bool = True
    entity_column: str = ""
    time_column: str = ""
    include_time_effects: bool = False
    endogenous_column: str = ""
    instrument_columns: list[str] = Field(default_factory=list)
    market_column: str = ""
    risk_free_column: str = ""
    smb_column: str = ""
    hml_column: str = ""
    spot_column: str = ""
    strike_column: str = ""
    maturity_column: str = ""
    rate_column: str = ""
    volatility_column: str = ""
    working_capital_column: str = ""
    retained_earnings_column: str = ""
    ebit_column: str = ""
    market_equity_column: str = ""
    total_assets_column: str = ""
    total_liabilities_column: str = ""
    sales_column: str = ""
    net_income_column: str = ""
    revenue_column: str = ""
    equity_column: str = ""
    inflation_gap_column: str = ""
    output_gap_column: str = ""
    arima_p: int = 1
    arima_d: int = 0
    arima_q: int = 0
    garch_p: int = 1
    garch_q: int = 1
    forecast_steps: int = 5
    var_lags: int = 1
    irf_horizon: int = 12
    impulse_column: str = ""
    response_column: str = ""
    virf_shock_size: float = 1.0
    bk_short_horizon: int = 5
    bk_medium_horizon: int = 20
    confidence_level: float = 0.95
    holding_period_days: int = 1
    ewma_lambda: float = 0.94
    option_type: str = "call"
    option_steps: int = 50
    risk_aversion: float = 3.0
    long_only: bool = True
    dsge_alpha: float = 0.33
    dsge_beta: float = 0.99
    dsge_delta: float = 0.025
    dsge_productivity: float = 1.0
    dsge_labor: float = 0.33
    dsge_shock_persistence: float = 0.9
    dsge_shock_size: float = 0.01
    dsge_impulse_horizon: int = 12
    robust_covariance: bool = True


class PlotCreateRequest(BaseModel):
    asset_id: str
    chart_type: str = Field(default="line")
    x_column: str = ""
    y_columns: list[str] = Field(default_factory=list)
    group_column: str = ""
    title: str = ""
    max_points: int = 400


class VariableGuideRequest(BaseModel):
    asset_id: str
    prompt: str = Field(min_length=8, max_length=4000)


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

    @app.get("/public-monitor")
    def public_monitor_page() -> FileResponse:
        return FileResponse(PUBLIC_WEB_FILE)

    @app.get("/data-lab")
    def data_lab_page() -> FileResponse:
        return FileResponse(DATA_LAB_WEB_FILE)

    @app.get("/data-lab/processing/{family}")
    def data_lab_processing_family_page(family: str) -> FileResponse:
        if not get_processing_family(family):
            raise HTTPException(status_code=404, detail="Data processing family not found.")
        return FileResponse(DATA_LAB_DETAIL_WEB_FILE)

    @app.get("/data-lab/models/{family}")
    def data_lab_model_family_page(family: str) -> FileResponse:
        if not get_model_family(family):
            raise HTTPException(status_code=404, detail="Model family not found.")
        return FileResponse(DATA_LAB_DETAIL_WEB_FILE)

    @app.get("/data-lab/results/processing/{asset_id}")
    def data_lab_processing_result_page(asset_id: str) -> FileResponse:
        return FileResponse(DATA_LAB_RESULT_WEB_FILE)

    @app.get("/data-lab/results/models/{record_id}")
    def data_lab_model_result_page(record_id: str) -> FileResponse:
        return FileResponse(DATA_LAB_RESULT_WEB_FILE)

    @app.get("/macro-desk")
    def public_macro_desk_page() -> FileResponse:
        return FileResponse(PUBLIC_WEB_FILE)

    @app.get("/briefings/{slug}")
    def public_briefing_page(slug: str) -> FileResponse:
        return FileResponse(PUBLIC_WEB_FILE)

    @app.get("/summaries/{window}")
    def public_summary_page(window: str) -> FileResponse:
        if window not in {"weekly", "monthly"}:
            raise HTTPException(status_code=404, detail="Public summary page not found.")
        return FileResponse(PUBLIC_WEB_FILE)

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

    @app.get("/api/data-lab/catalog")
    def data_lab_catalog() -> dict[str, Any]:
        return get_data_lab_catalog()

    @app.get("/api/data-lab/processing/{family}")
    def data_lab_processing_family_detail(family: str) -> dict[str, Any]:
        detail = get_processing_family(family)
        if not detail:
            raise HTTPException(status_code=404, detail="Data processing family not found.")
        return {"family": detail}

    @app.get("/api/data-lab/models/{family}")
    def data_lab_model_family_detail(family: str) -> dict[str, Any]:
        detail = get_model_family(family)
        if not detail:
            raise HTTPException(status_code=404, detail="Model family not found.")
        return {"family": detail}

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

    @app.get("/api/workspaces/{workspace_id}/assets/{asset_id}/profile")
    def asset_profile(
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
                return profile_dataset_asset(settings, db, user=user, workspace=workspace, asset_id=asset_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/results/processing/{asset_id}")
    def data_lab_processing_result(
        asset_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return {"result": build_processing_result_detail(settings, db, user=user, asset_id=asset_id)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/results/models/{record_id}")
    def data_lab_model_result(
        record_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return build_model_result_detail(db, user=user, record_id=record_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/prepare")
    def prepare_analysis_sample(
        workspace_id: str,
        request: DatasetPrepareRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return prepare_dataset_asset(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_id=request.asset_id,
                    workflow_group=request.workflow_group,
                    include_columns=request.include_columns,
                    required_columns=request.required_columns,
                    numeric_columns=request.numeric_columns,
                    binary_columns=request.binary_columns,
                    date_columns=request.date_columns,
                    impute_columns=request.impute_columns,
                    impute_method=request.impute_method,
                    winsorize_columns=request.winsorize_columns,
                    winsor_lower_quantile=request.winsor_lower_quantile,
                    winsor_upper_quantile=request.winsor_upper_quantile,
                    log_transform_columns=request.log_transform_columns,
                    standardize_columns=request.standardize_columns,
                    minmax_scale_columns=request.minmax_scale_columns,
                    outlier_columns=request.outlier_columns,
                    outlier_method=request.outlier_method,
                    outlier_threshold=request.outlier_threshold,
                    sort_column=request.sort_column,
                    time_group_column=request.time_group_column,
                    difference_columns=request.difference_columns,
                    return_columns=request.return_columns,
                    return_method=request.return_method,
                    lag_columns=request.lag_columns,
                    lag_periods=request.lag_periods,
                    lead_columns=request.lead_columns,
                    lead_periods=request.lead_periods,
                    rolling_mean_columns=request.rolling_mean_columns,
                    rolling_volatility_columns=request.rolling_volatility_columns,
                    rolling_window=request.rolling_window,
                    drop_duplicates=request.drop_duplicates,
                    drop_missing_required=request.drop_missing_required,
                )
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
                    robust_covariance=request.robust_covariance,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/variable-guide")
    def variable_guide(
        workspace_id: str,
        request: VariableGuideRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return suggest_beginner_variable_plan(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_id=request.asset_id,
                    prompt_text=request.prompt,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/models")
    def run_model(
        workspace_id: str,
        request: ModelRunRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return run_model_analysis(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    model_type=request.model_type,
                    asset_id=request.asset_id,
                    dependent=request.dependent,
                    independents=request.independents,
                    controls=request.controls,
                    series_columns=request.series_columns,
                    treatment_column=request.treatment_column,
                    post_column=request.post_column,
                    event_time_column=request.event_time_column,
                    lead_window=request.lead_window,
                    lag_window=request.lag_window,
                    omitted_period=request.omitted_period,
                    origin_mass_column=request.origin_mass_column,
                    destination_mass_column=request.destination_mass_column,
                    distance_column=request.distance_column,
                    running_column=request.running_column,
                    cutoff=request.rdd_cutoff,
                    bandwidth=request.rdd_bandwidth,
                    polynomial_order=request.rdd_polynomial_order,
                    treat_above_cutoff=request.treat_above_cutoff,
                    entity_column=request.entity_column,
                    time_column=request.time_column,
                    include_time_effects=request.include_time_effects,
                    endogenous_column=request.endogenous_column,
                    instrument_columns=request.instrument_columns,
                    market_column=request.market_column,
                    risk_free_column=request.risk_free_column,
                    smb_column=request.smb_column,
                    hml_column=request.hml_column,
                    spot_column=request.spot_column,
                    strike_column=request.strike_column,
                    maturity_column=request.maturity_column,
                    rate_column=request.rate_column,
                    volatility_column=request.volatility_column,
                    working_capital_column=request.working_capital_column,
                    retained_earnings_column=request.retained_earnings_column,
                    ebit_column=request.ebit_column,
                    market_equity_column=request.market_equity_column,
                    total_assets_column=request.total_assets_column,
                    total_liabilities_column=request.total_liabilities_column,
                    sales_column=request.sales_column,
                    net_income_column=request.net_income_column,
                    revenue_column=request.revenue_column,
                    equity_column=request.equity_column,
                    inflation_gap_column=request.inflation_gap_column,
                    output_gap_column=request.output_gap_column,
                    arima_p=request.arima_p,
                    arima_d=request.arima_d,
                    arima_q=request.arima_q,
                    garch_p=request.garch_p,
                    garch_q=request.garch_q,
                    forecast_steps=request.forecast_steps,
                    var_lags=request.var_lags,
                    irf_horizon=request.irf_horizon,
                    impulse_column=request.impulse_column,
                    response_column=request.response_column,
                    virf_shock_size=request.virf_shock_size,
                    bk_short_horizon=request.bk_short_horizon,
                    bk_medium_horizon=request.bk_medium_horizon,
                    confidence_level=request.confidence_level,
                    holding_period_days=request.holding_period_days,
                    ewma_lambda=request.ewma_lambda,
                    option_type=request.option_type,
                    option_steps=request.option_steps,
                    risk_aversion=request.risk_aversion,
                    long_only=request.long_only,
                    dsge_alpha=request.dsge_alpha,
                    dsge_beta=request.dsge_beta,
                    dsge_delta=request.dsge_delta,
                    dsge_productivity=request.dsge_productivity,
                    dsge_labor=request.dsge_labor,
                    dsge_shock_persistence=request.dsge_shock_persistence,
                    dsge_shock_size=request.dsge_shock_size,
                    dsge_impulse_horizon=request.dsge_impulse_horizon,
                    robust_covariance=request.robust_covariance,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/plot")
    def create_plot(
        workspace_id: str,
        request: PlotCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return create_plot_asset(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_id=request.asset_id,
                    chart_type=request.chart_type,
                    x_column=request.x_column,
                    y_columns=request.y_columns,
                    group_column=request.group_column,
                    title=request.title,
                    max_points=request.max_points,
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
