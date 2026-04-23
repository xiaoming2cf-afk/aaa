from __future__ import annotations

from contextvars import ContextVar
import hashlib
import inspect
import json
import logging
import hmac
from pathlib import Path
import re
from typing import Any
import unicodedata
from urllib.parse import quote, unquote

import requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .agent_diagnostics import (
    build_agent_eval_candidate,
    build_agent_eval_dataset_preview,
    get_owned_agent_run,
    list_agent_runs,
    serialize_agent_run,
    serialize_agent_run_detail,
)
from .asset_storage import is_remote_asset_reference, load_asset_bytes, resolve_local_asset_path
from .audit import audit_event
from .auth_support import (
    clear_login_failures_for_email,
    consume_password_reset_token,
    consume_rate_limit,
    issue_password_reset_token,
    purge_expired_sessions,
    purge_stale_login_attempts,
    rate_limit_key,
)
from .config import get_settings
from .data_lab_catalog import (
    get_data_lab_catalog,
    get_model_family,
    get_model_method,
    get_model_teaching_guide,
    get_processing_family,
)
from .data_lab_agent import (
    create_agent_session,
    export_agent_notebook,
    generate_agent_report,
    get_agent_llm_config,
    get_agent_session,
    send_agent_message,
    test_agent_llm_config,
    update_agent_llm_config,
)
from .db import init_database, session_scope
from .entities import DataAsset, KnowledgeRecord, User
from .notifications import send_password_reset_email
from .platform_core import (
    archive_knowledge_record,
    add_item_to_knowledge_case,
    build_model_result_detail,
    build_processing_result_detail,
    build_knowledge_case_detail,
    create_data_lab_run,
    create_plot_asset,
    create_knowledge_case,
    create_workspace_digest_record,
    create_workspace_memory,
    clean_dataset_asset,
    create_integration,
    create_knowledge_record,
    create_workspace,
    delete_workspace_memory,
    delete_knowledge_case,
    delete_knowledge_record,
    delete_integration,
    finalize_data_lab_run_failure,
    finalize_data_lab_run_success,
    get_owned_knowledge_case,
    get_current_user,
    get_current_user_optional,
    get_owned_knowledge_record,
    get_workspace_for_user,
    list_data_lab_runs,
    find_related_knowledge_records,
    is_knowledge_record_archived,
    logout_user_session,
    list_assets,
    list_lab_templates,
    list_knowledge_cases,
    list_integrations,
    list_knowledge_records,
    list_knowledge_case_items,
    list_workspace_memories,
    list_workspaces,
    login_user,
    prepare_dataset_asset,
    profile_dataset_asset,
    register_user,
    remove_item_from_knowledge_case,
    resolve_integration,
    run_model_analysis,
    run_ols_analysis,
    save_upload_asset,
    search_assets,
    search_knowledge_records,
    serialize_asset,
    serialize_data_lab_run,
    serialize_knowledge_case,
    serialize_integration,
    serialize_knowledge_record,
    serialize_workspace_memory,
    serialize_user,
    serialize_workspace,
    suggest_beginner_variable_plan,
    test_integration,
    restore_knowledge_record,
    update_knowledge_case,
    update_knowledge_record,
    create_lab_template,
    serialize_lab_template,
    get_owned_lab_template,
)
from .quality_center import (
    DeliveryGateError,
    build_delivery_scorecard,
    ensure_delivery_allowed,
    load_engineering_gate_report,
    list_run_quality_snapshots,
    review_agent_run_delivery,
    review_knowledge_record_delivery,
)
from .request_meta import request_ip as resolve_request_ip, validate_same_origin_request
from .runtime_models import (
    KnowledgePublishRequest,
    ResearchRunPublishRequest,
    ResearchRunRequest,
    ResearchRunRetryRequest,
    TeamCreateRequest,
    TeamLibraryCloneRequest,
    WorkspaceTeamAttachRequest,
)
from .service import retry_workspace_research_run, run_agent_worker_iteration, start_workspace_research_run
from .team_library import (
    attach_workspace_to_team,
    clone_team_library_record_to_workspace,
    create_team,
    get_team_library_record_for_user,
    list_team_library_records,
    list_teams_for_user,
    publish_workspace_source_to_team_library,
    serialize_team_library_record,
    serialize_team,
)
from .utils import truncate_text

_RUN_MODEL_ANALYSIS_PARAMETER_NAMES = {
    name
    for name in inspect.signature(run_model_analysis).parameters
    if name not in {"settings", "db", "user", "workspace"}
}
from .platform_research import (
    build_named_public_summary,
    build_public_briefing_summary,
    create_literature_followup_note,
    create_schedule_job,
    delete_schedule_job,
    detach_knowledge_record_references,
    ensure_public_daily_briefing,
    generate_economic_briefing,
    get_owned_schedule_job,
    get_or_build_latest_public_briefing,
    get_latest_public_briefing,
    get_public_briefing_by_slug,
    import_briefing_knowledge_record,
    import_literature_knowledge_record,
    import_literature_knowledge_records,
    import_literature_pdf_asset,
    import_literature_pdf_assets,
    import_openalex_works,
    list_briefings,
    list_job_runs,
    list_literature_entries,
    list_public_briefings,
    list_schedule_jobs,
    moderate_public_briefing_item,
    recent_schedule_runs,
    run_due_schedule_jobs,
    run_schedule_job_now,
    schedule_run_counts,
    search_openalex,
    serialize_briefing,
    serialize_job_run,
    serialize_literature_entry,
    serialize_public_briefing,
    serialize_public_briefing_detail,
    serialize_schedule,
    update_schedule_job,
)
from .security import AccountLockedError, RateLimitError, generate_csrf_token


logger = logging.getLogger(__name__)


WEB_DIR = Path(__file__).with_name("web")
SPA_ROOT_DIR = Path(__file__).resolve().parents[2] / "frontend-spa"
SPA_DIST_DIR = SPA_ROOT_DIR / "dist"
PUBLIC_WEB_FILE = WEB_DIR / "public.html"
DATA_LAB_WEB_FILE = WEB_DIR / "data_lab.html"
DATA_LAB_PREPARATION_WEB_FILE = WEB_DIR / "data_lab_preparation.html"
DATA_LAB_MODEL_WEB_FILE = WEB_DIR / "data_lab_model.html"
DATA_LAB_RESULTS_WEB_FILE = WEB_DIR / "data_lab_results.html"
DATA_LAB_HISTORY_WEB_FILE = WEB_DIR / "data_lab_history.html"
WORKSPACE_WEB_FILE = WEB_DIR / "workspace.html"
RESEARCH_AGENT_WEB_FILE = WEB_DIR / "research_agent.html"
PROVIDER_CENTER_WEB_FILE = WEB_DIR / "provider_center.html"
PAPER_LIBRARY_WEB_FILE = WEB_DIR / "paper_library.html"
KNOWLEDGE_BASE_WEB_FILE = WEB_DIR / "knowledge_base.html"
SCHEDULES_WEB_FILE = WEB_DIR / "schedules.html"
DATA_LAB_DETAIL_WEB_FILE = WEB_DIR / "data_lab_detail.html"
DATA_LAB_METHOD_WEB_FILE = WEB_DIR / "data_lab_method.html"
DATA_LAB_TEACHING_WEB_FILE = WEB_DIR / "data_lab_teaching.html"
DATA_LAB_RESULT_WEB_FILE = WEB_DIR / "data_lab_result.html"
OPTIMIZATION_LAB_WEB_FILE = WEB_DIR / "optimization_lab.html"
OPTIMIZATION_LAB_RESULT_WEB_FILE = WEB_DIR / "optimization_lab_result.html"
SESSION_COOKIE_NAME = "erp_session_token"
CSRF_COOKIE_NAME = "erp_csrf_token"
_REQUEST_SESSION_TOKEN: ContextVar[str] = ContextVar("erp_request_session_token", default="")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_AUTH_SAME_ORIGIN_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
}
_MODEL_RUN_MAX_STRING_LENGTH = 240
_MODEL_RUN_MAX_LIST_ITEMS = 128
_MODEL_RUN_MAX_VARIANT_SPEC_KEYS = 64
_MODEL_RUN_MAX_VARIANT_SPEC_BYTES = 12_000
_DOWNLOAD_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_DOWNLOAD_ASCII_FALLBACK = re.compile(r"[^A-Za-z0-9._ -]+")
_DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https:; font-src 'self' data: https://fonts.gstatic.com; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
_BASE_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LAB_RATE_LIMIT_WINDOW_MINUTES = 15
_BRIEFING_GENERATE_LIMIT = 6
_MODEL_RUN_LIMIT = 20
_OPTIMIZATION_RUN_LIMIT = 6
_SCHEDULE_RUN_NOW_LIMIT = 8


def _optimization_api():
    from .optimization_lab import (
        build_optimization_result_detail,
        get_optimization_catalog,
        list_optimization_results,
        run_optimization_suite,
        serialize_optimization_result_list,
    )

    return {
        "build_result_detail": build_optimization_result_detail,
        "get_catalog": get_optimization_catalog,
        "list_results": list_optimization_results,
        "run_suite": run_optimization_suite,
        "serialize_result_list": serialize_optimization_result_list,
    }


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=240)
    password: str = Field(min_length=12, max_length=200)


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    research_domain: str = "economics"


class IntegrationCreateRequest(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    category: str = Field(default="llm", min_length=2, max_length=50)
    kind: str = Field(min_length=2, max_length=50)
    api_key: str = Field(default="", max_length=400)
    base_url: str = ""
    model: str = ""
    is_default: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=2)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    content: str | None = Field(default=None, min_length=2)
    tags: list[str] | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)


class WorkspaceMemoryCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=2, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCaseCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    description: str | None = None
    tags: list[str] | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)


class KnowledgeCaseItemCreateRequest(BaseModel):
    item_type: str = Field(min_length=2, max_length=60)
    ref_id: str = Field(min_length=2, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeArchiveRequest(BaseModel):
    reason: str = Field(default="", max_length=280)


class OpenAlexImportRequest(BaseModel):
    works: list[dict[str, Any]] = Field(default_factory=list)


class LiteratureBatchRequest(BaseModel):
    entry_ids: list[str] = Field(default_factory=list)


class LiteratureDerivedNoteRequest(BaseModel):
    mode: str = Field(min_length=2, max_length=60)


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


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone_name: str | None = Field(default=None, min_length=2, max_length=80)
    local_time: str | None = Field(default=None, min_length=4, max_length=8)
    integration_id: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class OlsAnalysisRequest(BaseModel):
    asset_id: str
    dependent: str
    independents: list[str] = Field(default_factory=list)
    robust_covariance: bool = True


class DatasetPrepareRequest(BaseModel):
    asset_id: str
    workflow_group: str = Field(default="sample_preparation")
    template_id: str = ""
    variant_label: str = ""
    variant_spec: dict[str, Any] = Field(default_factory=dict)
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
    model_config = ConfigDict(extra="ignore")

    asset_id: str
    model_family: str = ""
    model_type: str = Field(default="ols")
    template_id: str = ""
    variant_label: str = ""
    variant_spec: dict[str, Any] = Field(default_factory=dict)
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
    cutoff: float = 0.0
    bandwidth: float = 0.0
    kink_point: float = 0.0
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
    feature_columns: list[str] = Field(default_factory=list)
    factor_columns: list[str] = Field(default_factory=list)
    secondary_dependent: str = ""
    glm_family: str = ""
    gee_family: str = ""
    gee_group_column: str = ""
    count_family: str = ""
    inflation_regressors: list[str] = Field(default_factory=list)
    quantile: float = 0.5
    varmax_order: list[int] = Field(default_factory=lambda: [1, 1])
    coint_rank: int = 1
    vecm_diff_lags: int = 1
    markov_regimes: int = 2
    seasonal: str = ""
    seasonal_periods: int = 12
    distribution: str = ""
    garch_o: int = 0
    forecast_simulations: int = 500
    harx_lags: list[int] = Field(default_factory=lambda: [1, 5, 22])
    unit_root_lags: int | None = None
    trend: str = ""
    portfolio_objective: str = ""
    cvar_beta: float = 0.95
    cdar_beta: float = 0.95
    split_ratio: float = 0.7
    n_estimators: int = 120
    learning_rate: float = 0.05
    num_leaves: int = 31
    iterations: int = 180
    depth: int = 6
    treated_unit: str = ""
    control_units: list[str] = Field(default_factory=list)
    treatment_time: float | int | str | None = None
    treatment_time_column: str = ""
    treatment_index: int = 0
    intervention_at: float | int | str | None = None
    draws: int = 150
    tune: int = 150
    chains: int = 2

    @model_validator(mode="after")
    def _validate_payload_bounds(self) -> "ModelRunRequest":
        for field_name, value in self.__dict__.items():
            if isinstance(value, str) and len(value) > _MODEL_RUN_MAX_STRING_LENGTH:
                raise ValueError(f"{field_name} is too long.")
            if isinstance(value, list):
                if len(value) > _MODEL_RUN_MAX_LIST_ITEMS:
                    raise ValueError(f"{field_name} has too many items.")
                for item in value:
                    if isinstance(item, str) and len(item) > _MODEL_RUN_MAX_STRING_LENGTH:
                        raise ValueError(f"{field_name} contains an item that is too long.")
            if field_name == "variant_spec":
                if len(value) > _MODEL_RUN_MAX_VARIANT_SPEC_KEYS:
                    raise ValueError("variant_spec contains too many keys.")
                encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if len(encoded) > _MODEL_RUN_MAX_VARIANT_SPEC_BYTES:
                    raise ValueError("variant_spec is too large.")
        return self


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


class DataLabAgentSessionCreateRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    title: str = Field(default="Data Lab Agent Session", max_length=200)
    language: str = Field(default="Chinese", max_length=40)


class DataLabAgentMessageRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    user_code: str = Field(default="", max_length=12000)
    intervention_note: str = Field(default="", max_length=1600)
    execution_mode: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def _validate_content(self) -> "DataLabAgentMessageRequest":
        if not self.message.strip() and not self.user_code.strip():
            raise ValueError("Provide message or user_code.")
        return self


class DataLabAgentLLMConfigRequest(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=600)
    clear_api_key: bool = False
    coder_model: str = Field(default="", max_length=120)
    reviewer_model: str = Field(default="", max_length=120)
    report_model: str = Field(default="", max_length=120)
    label: str = Field(default="", max_length=120)


class OptimizationRunRequest(BaseModel):
    suite_label: str = Field(default="Optimization Suite", min_length=2, max_length=200)
    template_id: str = ""
    variant_label: str = ""
    variant_spec: dict[str, Any] = Field(default_factory=dict)
    optimizer_names: list[str] = Field(default_factory=list)
    function_names: list[str] = Field(default_factory=list)
    dimension: int = 30
    epoch: int = 50
    pop_size: int = 30
    runs: int = 5
    workers: int = 0
    seed_base: int = 20260331


class LabTemplateCreateRequest(BaseModel):
    template_scope: str = Field(min_length=2, max_length=40)
    workflow_type: str = Field(min_length=2, max_length=40)
    family: str = ""
    method: str = ""
    name: str = Field(min_length=2, max_length=240)
    description: str = ""
    specification: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class PublicBriefingModerationRequest(BaseModel):
    action: str = Field(min_length=2, max_length=20)
    url: str = ""
    title: str = ""


def _token_from_headers(authorization: str | None, x_session_token: str | None) -> str:
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    header_token = (x_session_token or "").strip()
    if header_token:
        return header_token
    return (_REQUEST_SESSION_TOKEN.get("") or "").strip()


def _resolve_session_token(
    request: Request,
    authorization: str | None,
    x_session_token: str | None,
) -> str:
    token = _token_from_headers(authorization, x_session_token)
    if token:
        return token
    return (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()


def _session_cookie_secure(settings) -> bool:
    return settings.public_base_url.strip().lower().startswith("https://")


def _request_ip(request: Request) -> str:
    settings = get_settings()
    return resolve_request_ip(request, settings)


def _request_uses_header_auth(request: Request) -> bool:
    authorization = request.headers.get("authorization", "").strip()
    request_token = request.headers.get("x-session-token", "").strip()
    return bool(authorization.lower().startswith("bearer ") or request_token)


def _csrf_cookie_secure(settings) -> bool:
    return _session_cookie_secure(settings)


def _set_csrf_cookie(response: Response, settings, token: str) -> None:
    max_age = max(3600, int(settings.session_ttl_hours) * 3600)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        samesite="lax",
        secure=_csrf_cookie_secure(settings),
        max_age=max_age,
        path="/",
    )


def _clear_csrf_cookie(response: Response, settings) -> None:
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        samesite="lax",
        secure=_csrf_cookie_secure(settings),
    )


def _validate_csrf_request(request: Request, settings) -> None:
    cookie_token = (request.cookies.get(CSRF_COOKIE_NAME) or "").strip()
    header_token = (request.headers.get("x-csrf-token") or "").strip()
    if not cookie_token or not header_token or cookie_token != header_token:
        raise PermissionError("Missing or invalid CSRF token.")
    validate_same_origin_request(request, settings, require_header=False)


def _require_same_origin_auth_post(request: Request, settings) -> None:
    if request.url.path in _AUTH_SAME_ORIGIN_PATHS and request.method.upper() not in _SAFE_METHODS:
        validate_same_origin_request(request, settings, require_header=True)


def _email_audit_digest(settings, email: str) -> str:
    normalized = str(email or "").strip().lower()
    if not normalized:
        return ""
    return hmac.new(
        settings.app_secret.encode("utf-8"),
        f"login-email:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _set_session_cookie(response: Response, settings, token: str) -> None:
    max_age = max(3600, int(settings.session_ttl_hours) * 3600)
    secure = _session_cookie_secure(settings)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=max_age,
        path="/",
    )


def _clear_session_cookie(response: Response, settings) -> None:
    secure = _session_cookie_secure(settings)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def _normalize_download_filename(filename: str, *, fallback: str = "download") -> str:
    candidate = unquote(Path(filename or "").name)
    normalized = unicodedata.normalize("NFKC", candidate)
    normalized = _DOWNLOAD_CONTROL_CHARS.sub(" ", normalized)
    normalized = normalized.replace("\\", " ").replace("/", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized:
        return fallback
    if len(normalized) <= 180:
        return normalized
    suffix = Path(normalized).suffix
    max_base_length = max(1, 180 - len(suffix))
    truncated = f"{Path(normalized).stem[:max_base_length].rstrip(' .')}{suffix}"
    return truncated or fallback


def _ascii_download_filename(filename: str, *, fallback: str = "download") -> str:
    normalized = _normalize_download_filename(filename, fallback=fallback)
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(normalized).suffix)[:24]
    ascii_base = unicodedata.normalize("NFKD", Path(normalized).stem).encode("ascii", "ignore").decode("ascii")
    ascii_base = _DOWNLOAD_ASCII_FALLBACK.sub("_", ascii_base)
    ascii_base = re.sub(r"[\s_-]{2,}", "_", ascii_base).strip("._ -")
    if not ascii_base:
        ascii_base = fallback
    max_base_length = max(1, 120 - len(suffix))
    ascii_base = ascii_base[:max_base_length].rstrip("._ -") or fallback
    return f"{ascii_base}{suffix}"


def _build_attachment_content_disposition(filename: str) -> str:
    normalized = _normalize_download_filename(filename)
    ascii_fallback = _ascii_download_filename(normalized)
    encoded = quote(normalized, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _content_security_policy_for_request(request: Request, settings) -> str:
    if settings.is_development_env and (
        request.url.path in {"/docs", "/redoc", "/docs/oauth2-redirect"} or request.url.path.startswith("/docs/")
    ):
        return _DOCS_CSP
    return _DEFAULT_CSP


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, DeliveryGateError):
        raise HTTPException(status_code=409, detail=exc.to_http_detail()) from exc
    if isinstance(exc, RateLimitError):
        raise HTTPException(status_code=429, detail=str(exc) or "Too many requests.") from exc
    if isinstance(exc, AccountLockedError):
        raise HTTPException(status_code=423, detail=str(exc) or "Account is temporarily locked.") from exc
    if isinstance(exc, requests.HTTPError):
        logger.warning("Upstream provider request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream provider request failed.") from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Requested resource was not found.") from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=401, detail=str(exc) or "Unauthorized request.") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("Unexpected request failure", exc_info=exc)
    raise HTTPException(status_code=500, detail="Internal server error.") from exc


def _is_trusted_local_request(request: Request) -> bool:
    host = (request.url.hostname or "").strip().lower()
    return host in {"", "localhost", "127.0.0.1", "::1", "testserver"}


def _merge_spec_dicts(base: dict[str, Any] | None, overlay: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_spec_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_template_execution(
    request_model: BaseModel,
    *,
    db,
    user,
    workspace,
    template_scope: str,
    workflow_type: str,
    family: str = "",
    method: str = "",
) -> dict[str, Any]:
    payload = request_model.model_dump(exclude_unset=True)
    template_id = str(payload.pop("template_id", "") or "").strip()
    variant_label = str(payload.pop("variant_label", "") or "").strip()
    raw_variant_spec = payload.pop("variant_spec", {}) or {}
    variant_spec = dict(raw_variant_spec) if isinstance(raw_variant_spec, dict) else {}
    template = None
    template_spec: dict[str, Any] = {}
    if template_id:
        template = get_owned_lab_template(db, user=user, template_id=template_id)
        if template.workspace_id != workspace.id:
            raise PermissionError("Lab template does not belong to the selected workspace.")
        if template.template_scope != template_scope:
            raise ValueError(f"Template scope mismatch: expected {template_scope}.")
        if template.workflow_type != workflow_type:
            raise ValueError(f"Template workflow mismatch: expected {workflow_type}.")
        if family and template.family and template.family != family:
            raise ValueError(f"Template family mismatch: expected {family}.")
        if method and template.method and template.method != method:
            raise ValueError(f"Template method mismatch: expected {method}.")
        template_spec = dict(template.specification_json or {}) if isinstance(template.specification_json, dict) else {}
    explicit_fields = {
        key: getattr(request_model, key)
        for key in request_model.model_fields_set
        if key not in {"template_id", "variant_label", "variant_spec"}
    }
    effective_payload = _merge_spec_dicts(payload, template_spec)
    effective_payload = _merge_spec_dicts(effective_payload, variant_spec)
    effective_payload = _merge_spec_dicts(effective_payload, explicit_fields)
    return {
        "payload": effective_payload,
        "template_id": template.id if template else "",
        "template_name": template.name if template else "",
        "template_scope": template_scope,
        "workflow_type": workflow_type,
        "family": family or str(effective_payload.get("workflow_group") or effective_payload.get("model_family") or "").strip(),
        "method": method or str(effective_payload.get("model_type") or "").strip(),
        "variant_label": variant_label,
        "variant_spec": variant_spec,
        "effective_specification": effective_payload,
    }


def _require_feature_access(
    db,
    request: Request,
    authorization: str | None,
    x_session_token: str | None,
):
    token = _resolve_session_token(request, authorization, x_session_token)
    return get_current_user(db, token)


def _current_user_from_request(
    db,
    request: Request,
    authorization: str | None,
    x_session_token: str | None,
):
    token = _resolve_session_token(request, authorization, x_session_token)
    return get_current_user_optional(db, token)


def _private_page_or_home(
    request: Request,
    file_path: Path,
    authorization: str | None,
    x_session_token: str | None,
) -> Response:
    with session_scope() as db:
        user = _current_user_from_request(db, request, authorization, x_session_token)
    if not user:
        return RedirectResponse(url="/", status_code=307)
    return FileResponse(file_path)


def _private_spa_or_home(
    request: Request,
    *,
    subpath: str,
    authorization: str | None,
    x_session_token: str | None,
) -> Response:
    with session_scope() as db:
        user = _current_user_from_request(db, request, authorization, x_session_token)
    if not user:
        return RedirectResponse(url="/", status_code=307)
    normalized = str(subpath or "").strip().lstrip("/")
    candidate = (SPA_DIST_DIR / normalized).resolve() if normalized else SPA_DIST_DIR / "index.html"
    dist_root = SPA_DIST_DIR.resolve()
    if normalized and candidate.exists() and dist_root in candidate.parents:
        return FileResponse(candidate)
    if (SPA_DIST_DIR / "index.html").exists():
        return FileResponse(SPA_DIST_DIR / "index.html")
    if get_settings().is_development_env and (SPA_ROOT_DIR / "index.html").exists():
        return FileResponse(SPA_ROOT_DIR / "index.html")
    raise HTTPException(status_code=503, detail="SPA assets are not built yet.")


def _audit_workspace_action(
    db,
    *,
    request: Request | None,
    action: str,
    user,
    workspace=None,
    resource_type: str = "",
    resource_id: str = "",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
):
    audit_event(
        db,
        request=request,
        action=action,
        user=user,
        workspace=workspace,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        metadata=metadata,
    )


def _serialize_agent_run_payload(
    run,
    *,
    settings,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
) -> dict[str, Any]:
    delivery_review, _ = review_agent_run_delivery(
        run,
        settings=settings,
        refresh_engineering=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    return serialize_agent_run(run, delivery_review=delivery_review)


def _serialize_agent_run_detail_payload(
    run,
    *,
    settings,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
) -> dict[str, Any]:
    delivery_review, _ = review_agent_run_delivery(
        run,
        settings=settings,
        refresh_engineering=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    return serialize_agent_run_detail(run, delivery_review=delivery_review)


def _serialize_knowledge_record_payload(
    db,
    record: KnowledgeRecord,
    *,
    settings,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
    include_content: bool = True,
) -> dict[str, Any]:
    delivery_review, _ = review_knowledge_record_delivery(
        db,
        record,
        settings=settings,
        refresh_engineering=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    payload = serialize_knowledge_record(record, include_content=include_content)
    payload["delivery_review"] = delivery_review
    payload["publish_allowed"] = bool(delivery_review.get("publish_allowed"))
    payload["blocking_reasons"] = list(delivery_review.get("blocking_reasons") or [])
    return payload


def _consume_workspace_rate_limit(
    db,
    *,
    bucket_type: str,
    user,
    workspace,
    limit: int,
    window_minutes: int = _LAB_RATE_LIMIT_WINDOW_MINUTES,
) -> None:
    consume_rate_limit(
        db,
        bucket_type=bucket_type,
        bucket_key=rate_limit_key([user.id, workspace.id]),
        limit=limit,
        window_minutes=window_minutes,
    )


def _schedule_payloads(db, *, user, workspace, jobs: list[Any]) -> list[dict[str, Any]]:
    counts = schedule_run_counts(db, jobs=jobs)
    recent_runs = recent_schedule_runs(db, jobs=jobs, per_job_limit=3)
    payloads: list[dict[str, Any]] = []
    for job in jobs:
        job_runs = recent_runs.get(job.id, [])
        payloads.append(
            serialize_schedule(
                job,
                latest_run=job_runs[0] if job_runs else None,
                recent_runs=job_runs,
                run_count=counts.get(job.id, 0),
            )
        )
    return payloads


def _history_item_sort_value(item: dict[str, Any]) -> str:
    return str(item.get("updated_at") or item.get("created_at") or "")


def _merge_data_lab_history_items(
    run_items: list[dict[str, Any]],
    legacy_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen_refs: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in run_items:
        ref_id = str(item.get("ref_id") or "").strip()
        if ref_id:
            seen_refs.add(ref_id)
        merged.append(item)
    for item in legacy_items:
        item_id = str(item.get("id") or "").strip()
        if item_id and item_id in seen_refs:
            continue
        merged.append(item)
    merged.sort(key=_history_item_sort_value, reverse=True)
    return merged


def _processing_run_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    asset = result.get("asset", {}) if isinstance(result.get("asset"), dict) else {}
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    return {
        "title": asset.get("title") or result.get("processing_family") or "Processing result",
        "summary": summary,
        "processing_family": result.get("processing_family", ""),
        "result_detail_path": result.get("detail_path") or result.get("result_detail_path") or "",
        "detail_path": result.get("detail_path") or result.get("result_detail_path") or "",
        "result_asset_id": asset.get("id") or "",
    }


def _model_run_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    summary = (
        result.get("equation")
        or (result.get("narrative") or [""])[0]
        or result.get("model_family")
        or result.get("model_type")
        or "Model result"
    )
    return {
        "title": result.get("model_label") or result.get("model_type") or "Model result",
        "summary": truncate_text(str(summary or ""), 400),
        "model_family": result.get("model_family", ""),
        "model_type": result.get("model_type", ""),
        "result_detail_path": result.get("detail_path") or result.get("result_detail_path") or "",
        "detail_path": result.get("detail_path") or result.get("result_detail_path") or "",
        "result_record_id": result.get("result_record_id") or result.get("record_id") or "",
    }


def _optimization_run_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    record = result.get("record", {}) if isinstance(result.get("record"), dict) else {}
    details = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
    summary = details.get("summary", {}) if isinstance(details.get("summary"), dict) else {}
    return {
        "title": details.get("suite_label") or record.get("title") or "Optimization Suite",
        "summary": summary,
        "suite_label": details.get("suite_label") or record.get("title") or "Optimization Suite",
        "result_detail_path": details.get("detail_path") or details.get("result_detail_path") or "",
        "detail_path": details.get("detail_path") or details.get("result_detail_path") or "",
        "result_record_id": details.get("result_record_id") or record.get("id") or "",
    }


def _data_lab_history_payload(db, *, user, workspace, limit: int = 12) -> dict[str, Any]:
    run_rows = list_data_lab_runs(db, user=user, workspace=workspace, limit=max(12, limit * 3))
    run_items = [serialize_data_lab_run(db, user=user, run=row) for row in run_rows]
    processing_runs = [item for item in run_items if item.get("workflow_type") == "processing"]
    model_runs = [item for item in run_items if item.get("workflow_type") == "model"]
    optimization_runs = [item for item in run_items if item.get("workflow_type") == "optimization"]
    agent_session_runs = [item for item in run_items if item.get("workflow_type") == "agent_session"]

    assets = list_assets(db, user=user, workspace=workspace)
    legacy_processing_items = [
        serialize_asset(item)
        for item in assets
        if isinstance(item.metadata_json, dict)
        and (
            isinstance(item.metadata_json.get("processing_result"), dict)
            or item.metadata_json.get("analysis_kind") == "plot"
        )
    ]
    legacy_processing_items.sort(key=_history_item_sort_value, reverse=True)

    knowledge_rows = list_knowledge_records(db, user=user, workspace=workspace)
    legacy_model_items = []
    for row in knowledge_rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        if metadata.get("workflow_type") == "model" or metadata.get("model_type"):
            legacy_model_items.append(serialize_knowledge_record(row, include_content=False))
    legacy_model_items.sort(key=_history_item_sort_value, reverse=True)

    optimization_api = _optimization_api()
    legacy_optimization_items = optimization_api["serialize_result_list"](
        optimization_api["list_results"](db, user=user, workspace=workspace, limit=limit)
    )
    legacy_optimization_items.sort(key=_history_item_sort_value, reverse=True)

    processing_items = _merge_data_lab_history_items(processing_runs, legacy_processing_items)
    model_items = _merge_data_lab_history_items(model_runs, legacy_model_items)
    optimization_items = _merge_data_lab_history_items(optimization_runs, legacy_optimization_items)

    return {
        "processing": processing_items[:limit],
        "models": model_items[:limit],
        "optimization": optimization_items[:limit],
        "agent_sessions": agent_session_runs[:limit],
    }


async def _read_upload_payload(file: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {max_bytes} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)


def create_app() -> FastAPI:
    settings = get_settings()
    init_database()
    with session_scope() as db:
        purge_expired_sessions(db)
        purge_stale_login_attempts(db)
    docs_enabled = settings.is_development_env
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Session-Token", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def bind_request_session_token(request: Request, call_next):
        token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
        reset_token = _REQUEST_SESSION_TOKEN.set(token)
        try:
            response = await call_next(request)
        finally:
            _REQUEST_SESSION_TOKEN.reset(reset_token)
        return response

    @app.middleware("http")
    async def enforce_csrf(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method.upper() not in _SAFE_METHODS:
            try:
                _require_same_origin_auth_post(request, settings)
            except PermissionError as exc:
                return JSONResponse(status_code=403, content={"detail": str(exc) or "Same-origin validation failed."})
            if request.cookies.get(SESSION_COOKIE_NAME) and not _request_uses_header_auth(request):
                session_token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
                with session_scope() as db:
                    has_valid_cookie_session = bool(get_current_user_optional(db, session_token))
                if has_valid_cookie_session:
                    try:
                        _validate_csrf_request(request, settings)
                    except PermissionError as exc:
                        return JSONResponse(status_code=403, content={"detail": str(exc) or "CSRF validation failed."})
        return await call_next(request)

    @app.middleware("http")
    async def apply_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", _content_security_policy_for_request(request, settings))
        for header, value in _BASE_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.head("/")
    def index_head() -> Response:
        return Response(status_code=200)

    @app.get("/workspace")
    def workspace_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, WORKSPACE_WEB_FILE, authorization, x_session_token)

    @app.get("/research-agent")
    def research_agent_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, RESEARCH_AGENT_WEB_FILE, authorization, x_session_token)

    @app.get("/provider-center")
    def provider_center_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        try:
            _resolve_session_token(request, authorization, x_session_token)
        except Exception:
            return RedirectResponse(url="/", status_code=307)
        return HTMLResponse(
            """
            <!doctype html>
            <html lang="zh-CN">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Provider Center Unavailable</title>
                <style>
                  body { font-family: system-ui, sans-serif; margin: 0; background: #f6f3ee; color: #1c1a17; }
                  main { max-width: 760px; margin: 6rem auto; padding: 2rem; }
                  .card { background: #fffdf8; border: 1px solid #d7cbb7; border-radius: 18px; padding: 2rem; box-shadow: 0 20px 60px rgba(40, 26, 10, 0.08); }
                  .eyebrow { text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; color: #7a5c32; margin: 0 0 0.75rem; }
                  h1 { margin: 0 0 1rem; font-size: 2rem; }
                  p { line-height: 1.7; margin: 0 0 1rem; }
                  a { color: #7a3d00; }
                </style>
              </head>
              <body>
                <main>
                  <section class="card">
                    <p class="eyebrow">Disabled Surface</p>
                    <h1>Provider Center is not part of the current product scope</h1>
                    <p>
                      This build keeps research runs, review gates, publishing, knowledge capture, and team library workflows,
                      but it does not expose runtime model provider management.
                    </p>
                    <p>
                      Return to the <a href="/workspace">workspace</a>, <a href="/research-agent">research</a>,
                      or the <a href="/app/quality">quality dashboard</a>.
                    </p>
                  </section>
                </main>
              </body>
            </html>
            """
        )

    @app.get("/paper-library")
    def paper_library_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PAPER_LIBRARY_WEB_FILE, authorization, x_session_token)

    @app.get("/knowledge-base")
    def knowledge_base_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, KNOWLEDGE_BASE_WEB_FILE, authorization, x_session_token)

    @app.get("/schedules")
    def schedules_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, SCHEDULES_WEB_FILE, authorization, x_session_token)

    @app.get("/app")
    def spa_root_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_spa_or_home(request, subpath="", authorization=authorization, x_session_token=x_session_token)

    @app.get("/app/{full_path:path}")
    def spa_fallback_page(
        full_path: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_spa_or_home(
            request,
            subpath=full_path,
            authorization=authorization,
            x_session_token=x_session_token,
        )

    @app.get("/public-monitor")
    def public_monitor_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/public-monitor/{view_slug}")
    def public_monitor_view_page(
        view_slug: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab")
    def data_lab_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/preparation")
    def data_lab_preparation_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_PREPARATION_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/model")
    def data_lab_model_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_MODEL_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/results")
    def data_lab_results_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_RESULTS_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/history")
    def data_lab_history_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_HISTORY_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/optimization")
    def data_lab_optimization_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, OPTIMIZATION_LAB_WEB_FILE, authorization, x_session_token)

    @app.get("/optimization-lab")
    def optimization_lab_page() -> RedirectResponse:
        return RedirectResponse(url="/data-lab/optimization", status_code=307)

    @app.get("/optimization-lab/results/{record_id}")
    def optimization_lab_result_page(record_id: str) -> RedirectResponse:
        return RedirectResponse(url=f"/data-lab/results/optimization/{record_id}", status_code=307)

    @app.get("/data-lab/processing/{family}")
    def data_lab_processing_family_page(
        family: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        if not get_processing_family(family):
            raise HTTPException(status_code=404, detail="Data processing family not found.")
        return _private_page_or_home(request, DATA_LAB_DETAIL_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/models/{family}")
    def data_lab_model_family_page(
        family: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        if not get_model_family(family):
            raise HTTPException(status_code=404, detail="Model family not found.")
        return _private_page_or_home(request, DATA_LAB_DETAIL_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/models/{family}/{method}")
    def data_lab_model_method_page(
        family: str,
        method: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        if not get_model_method(family, method):
            raise HTTPException(status_code=404, detail="Model method not found.")
        return _private_page_or_home(request, DATA_LAB_METHOD_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/learn/models/{family}/{method}")
    def data_lab_model_teaching_page(
        family: str,
        method: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        if not get_model_teaching_guide(family, method):
            raise HTTPException(status_code=404, detail="Model teaching guide not found.")
        return _private_page_or_home(request, DATA_LAB_TEACHING_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/results/processing/{asset_id}")
    def data_lab_processing_result_page(
        asset_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_RESULT_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/results/models/{record_id}")
    def data_lab_model_result_page(
        record_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, DATA_LAB_RESULT_WEB_FILE, authorization, x_session_token)

    @app.get("/data-lab/results/optimization/{record_id}")
    def data_lab_optimization_result_page(
        record_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, OPTIMIZATION_LAB_RESULT_WEB_FILE, authorization, x_session_token)

    @app.get("/macro-desk")
    def public_macro_desk_page(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/macro-desk/{view_slug}")
    def public_macro_desk_view_page(
        view_slug: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/briefings/{slug}")
    def public_briefing_page(
        slug: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/summaries/{window}")
    def public_summary_page(
        window: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        if window not in {"weekly", "monthly"}:
            raise HTTPException(status_code=404, detail="Public summary page not found.")
        return _private_page_or_home(request, PUBLIC_WEB_FILE, authorization, x_session_token)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(WEB_DIR / "favicon.svg", media_type="image/svg+xml")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.head("/api/health")
    def health_head() -> Response:
        return Response(status_code=200)

    @app.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return {
            "app_name": settings.app_name,
            "public_digest_enabled": settings.public_digest_enabled,
        }

    @app.get("/api/providers")
    def providers(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _resolve_session_token(request, authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                audit_event(
                    db,
                    request=request,
                    action="provider.catalog.compat_read",
                    user=user,
                    resource_type="provider_catalog",
                    summary="Read provider scope notice through the compatibility endpoint.",
                )
                return {
                    "available": False,
                    "message": "Runtime provider management is not available in the current product scope.",
                    "providers": {"llm": [], "data_source": []},
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/catalog")
    def data_lab_catalog(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                return get_data_lab_catalog()
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/optimization/catalog")
    def optimization_catalog(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                return _optimization_api()["get_catalog"]()
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/processing/{family}")
    def data_lab_processing_family_detail(
        family: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                detail = get_processing_family(family)
                if not detail:
                    raise HTTPException(status_code=404, detail="Data processing family not found.")
                return {"family": detail}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/models/{family}")
    def data_lab_model_family_detail(
        family: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                detail = get_model_family(family)
                if not detail:
                    raise HTTPException(status_code=404, detail="Model family not found.")
                return {"family": detail}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/models/{family}/{method}")
    def data_lab_model_method_detail(
        family: str,
        method: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                detail = get_model_method(family, method)
                if not detail:
                    raise HTTPException(status_code=404, detail="Model method not found.")
                return {"method": detail}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/data-lab/learn/models/{family}/{method}")
    def data_lab_model_teaching_detail(
        family: str,
        method: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
                guide = get_model_teaching_guide(family, method)
                if not guide:
                    raise HTTPException(status_code=404, detail="Model teaching guide not found.")
                return {"guide": guide}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/briefings")
    def public_briefings(
        limit: int = 10,
        request: Request = None,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                get_or_build_latest_public_briefing(db, settings)
                return {
                    "items": [
                        serialize_public_briefing(item, public_base_url=settings.public_base_url)
                        for item in list_public_briefings(db, limit=limit)
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/briefings/latest")
    def public_briefing_latest(
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                briefing = get_or_build_latest_public_briefing(db, settings)
                return {
                    "briefing": serialize_public_briefing_detail(db, briefing, public_base_url=settings.public_base_url)
                    if briefing
                    else None
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/briefings/{slug}")
    def public_briefing_detail(
        slug: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                briefing = get_public_briefing_by_slug(db, slug=slug)
                if not briefing:
                    raise FileNotFoundError("Public briefing not found.")
                return {"briefing": serialize_public_briefing_detail(db, briefing, public_base_url=settings.public_base_url)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/public/briefings/{slug}/moderation")
    def public_briefing_moderation(
        slug: str,
        request: PublicBriefingModerationRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                briefing = get_public_briefing_by_slug(db, slug=slug)
                if not briefing:
                    raise FileNotFoundError("Public briefing not found.")
                moderated = moderate_public_briefing_item(
                    db,
                    settings,
                    briefing,
                    action=request.action,
                    item_url=request.url,
                    item_title=request.title,
                    actor_email=user.email,
                )
                return {
                    "briefing": serialize_public_briefing_detail(
                        db,
                        moderated,
                        public_base_url=settings.public_base_url,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/summary")
    def public_summary(
        days: int = 7,
        request: Request = None,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                get_or_build_latest_public_briefing(db, settings)
                return build_public_briefing_summary(db, days=days, public_base_url=settings.public_base_url)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/public/summaries/{window}")
    def public_summary_detail(
        window: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                get_or_build_latest_public_briefing(db, settings)
                return build_named_public_summary(db, window=window, public_base_url=settings.public_base_url)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/register")
    def register(request: RegisterRequest, response: Response, raw_request: Request) -> dict[str, Any]:
        try:
            with session_scope() as db:
                consume_rate_limit(
                    db,
                    bucket_type="auth.register.ip",
                    bucket_key=rate_limit_key([_request_ip(raw_request)]),
                    limit=3,
                    window_minutes=60,
                )
                user = register_user(db, email=request.email, password=request.password, full_name=request.full_name)
                user, token = login_user(
                    db,
                    settings,
                    email=request.email,
                    password=request.password,
                    ip_address=_request_ip(raw_request),
                )
                _set_session_cookie(response, settings, token)
                _set_csrf_cookie(response, settings, generate_csrf_token())
                audit_event(
                    db,
                    request=raw_request,
                    action="auth.register",
                    user=user,
                    resource_type="user",
                    resource_id=user.id,
                    summary="Created a new account.",
                )
                return {
                    "user": serialize_user(user),
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/login")
    def login(request: LoginRequest, response: Response, raw_request: Request) -> Any:
        try:
            with session_scope() as db:
                normalized_email = request.email.strip().lower()
                consume_rate_limit(
                    db,
                    bucket_type="auth.login.ip",
                    bucket_key=rate_limit_key([_request_ip(raw_request)]),
                    limit=20,
                    window_minutes=60,
                )
                try:
                    user, token = login_user(
                        db,
                        settings,
                        email=normalized_email,
                        password=request.password,
                        ip_address=_request_ip(raw_request),
                    )
                except (PermissionError, AccountLockedError, RateLimitError, ValueError) as exc:
                    audit_event(
                        db,
                        request=raw_request,
                        action="auth.login.failed",
                        status="denied",
                        resource_type="session",
                        summary="Failed sign-in attempt.",
                        metadata={"email_hmac": _email_audit_digest(settings, normalized_email)},
                    )
                    if isinstance(exc, AccountLockedError):
                        status_code = 423
                    elif isinstance(exc, RateLimitError):
                        status_code = 429
                    elif isinstance(exc, ValueError):
                        status_code = 400
                    else:
                        status_code = 401
                    return JSONResponse(status_code=status_code, content={"detail": str(exc)})
                _set_session_cookie(response, settings, token)
                _set_csrf_cookie(response, settings, generate_csrf_token())
                audit_event(
                    db,
                    request=raw_request,
                    action="auth.login",
                    user=user,
                    resource_type="session",
                    summary="Signed in successfully.",
                )
                return {
                    "user": serialize_user(user),
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/auth/me")
    def me(
        response: Response,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _resolve_session_token(request, authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                _set_csrf_cookie(response, settings, generate_csrf_token())
                return {
                    "user": serialize_user(user),
                    "workspaces": [serialize_workspace(item) for item in list_workspaces(db, user=user)],
                }
        except PermissionError:
            error_response = JSONResponse(status_code=401, content={"detail": "Authentication required."})
            _clear_session_cookie(error_response, settings)
            _clear_csrf_cookie(error_response, settings)
            return error_response
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/logout")
    def logout(
        request: Request,
        response: Response,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _resolve_session_token(request, authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user_optional(db, token)
                logout_user_session(db, token=token)
                if user:
                    audit_event(
                        db,
                        request=request,
                        action="auth.logout",
                        user=user,
                        resource_type="session",
                        summary="Signed out.",
                    )
            _clear_session_cookie(response, settings)
            _clear_csrf_cookie(response, settings)
            return {"status": "ok"}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/password-reset/request")
    def password_reset_request(payload: PasswordResetRequest, request: Request) -> dict[str, Any]:
        try:
            with session_scope() as db:
                consume_rate_limit(
                    db,
                    bucket_type="auth.password_reset.ip",
                    bucket_key=rate_limit_key([_request_ip(request)]),
                    limit=5,
                    window_minutes=60,
                )
                user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
                if user and user.is_active:
                    raw_token = issue_password_reset_token(
                        db,
                        user=user,
                        ttl_minutes=settings.password_reset_ttl_minutes,
                    )
                    reset_url = f"{settings.public_base_url.rstrip('/') or str(request.base_url).rstrip('/')}/#reset_token={raw_token}"
                    send_password_reset_email(
                        settings,
                        recipient=user.email,
                        reset_url=reset_url,
                        ttl_minutes=settings.password_reset_ttl_minutes,
                    )
                    audit_event(
                        db,
                        request=request,
                        action="auth.password_reset.request",
                        user=user,
                        resource_type="password_reset",
                        summary="Issued password reset email.",
                    )
            return {"status": "ok"}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/auth/password-reset/confirm")
    def password_reset_confirm(payload: PasswordResetConfirmRequest, request: Request) -> dict[str, Any]:
        try:
            with session_scope() as db:
                user = consume_password_reset_token(db, raw_token=payload.token)
                from .security import hash_password, validate_password_strength

                validate_password_strength(payload.password, email=user.email)
                user.password_hash = hash_password(payload.password)
                clear_login_failures_for_email(db, email=user.email, user=user)
                audit_event(
                    db,
                    request=request,
                    action="auth.password_reset.confirm",
                    user=user,
                    resource_type="password_reset",
                    summary="Password reset confirmed.",
                )
                return {"status": "ok"}
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
        raw_request: Request,
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
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="workspace.create",
                    user=user,
                    workspace=workspace,
                    resource_type="workspace",
                    resource_id=workspace.id,
                    summary="Created workspace.",
                )
                return {"workspace": serialize_workspace(workspace)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/memories")
    def workspace_memories(
        workspace_id: str,
        limit: int = 12,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {
                    "items": [
                        serialize_workspace_memory(item)
                        for item in list_workspace_memories(db, user=user, workspace=workspace, limit=max(1, min(limit, 12)))
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/memories")
    def add_workspace_memory(
        workspace_id: str,
        request: WorkspaceMemoryCreateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                memory = create_workspace_memory(
                    db,
                    user=user,
                    workspace=workspace,
                    title=request.title,
                    content=request.content,
                    metadata=request.metadata,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="workspace.memory.create",
                    user=user,
                    workspace=workspace,
                    resource_type="workspace_memory",
                    resource_id=memory.id,
                    summary="Saved a workspace memory chunk.",
                )
                return {"memory": serialize_workspace_memory(memory)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/workspaces/{workspace_id}/memories/{memory_id}")
    def remove_workspace_memory(
        workspace_id: str,
        memory_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                delete_workspace_memory(db, user=user, workspace=workspace, memory_id=memory_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="workspace.memory.delete",
                    user=user,
                    workspace=workspace,
                    resource_type="workspace_memory",
                    resource_id=memory_id,
                    summary="Deleted a workspace memory chunk.",
                )
                return {"status": "ok"}
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
        raw_request: Request,
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
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="provider.connection.create",
                    user=user,
                    resource_type="integration",
                    resource_id=integration.id,
                    summary=f"Saved provider connection {integration.label}.",
                    metadata={"kind": integration.kind, "category": integration.category},
                )
                return {"integration": serialize_integration(integration)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/integrations/{integration_id}/test")
    def verify_integration(
        integration_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                payload = test_integration(db, settings, user=user, integration_id=integration_id)
                _audit_workspace_action(
                    db,
                    request=request,
                    action="provider.connection.test",
                    user=user,
                    resource_type="integration",
                    resource_id=integration_id,
                    summary="Tested provider connection.",
                    metadata={"status": payload.get("status", "ok")},
                )
                return payload
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/integrations/{integration_id}")
    def remove_integration(
        integration_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                delete_integration(db, user=user, integration_id=integration_id)
                _audit_workspace_action(
                    db,
                    request=request,
                    action="provider.connection.delete",
                    user=user,
                    resource_type="integration",
                    resource_id=integration_id,
                    summary="Deleted provider connection.",
                )
                return {"status": "deleted"}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge")
    def knowledge(
        workspace_id: str,
        q: str = "",
        view: str = "full",
        status: str = "active",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                normalized_status = status.strip().lower() or "active"
                include_archived = normalized_status in {"all", "archived"}
                rows = (
                    search_knowledge_records(db, user=user, workspace=workspace, query=q, include_archived=include_archived)
                    if q.strip()
                    else list_knowledge_records(db, user=user, workspace=workspace, include_archived=include_archived)
                )
                if normalized_status == "archived":
                    rows = [item for item in rows if is_knowledge_record_archived(item)]
                include_content = view.strip().lower() != "summary"
                return {
                    "items": [
                        _serialize_knowledge_record_payload(
                            db,
                            item,
                            settings=settings,
                            auto_refresh_if_missing=True,
                            include_content=include_content,
                        )
                        for item in rows
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge/{record_id}")
    def knowledge_detail(
        workspace_id: str,
        record_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        record,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge/{record_id}/related")
    def related_knowledge(
        workspace_id: str,
        record_id: str,
        limit: int = 5,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {
                    "items": find_related_knowledge_records(
                        db,
                        user=user,
                        workspace=workspace,
                        record_id=record_id,
                        limit=limit,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge-cases")
    def knowledge_cases(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                items = []
                for case in list_knowledge_cases(db, user=user, workspace=workspace):
                    case_items = list_knowledge_case_items(db, user=user, case=case)
                    items.append(
                        serialize_knowledge_case(
                            case,
                            item_count=len(case_items),
                            latest_item_at=case_items[0].created_at.isoformat() if case_items else "",
                            item_types=sorted({entry.item_type for entry in case_items}),
                        )
                    )
                return {"items": items}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/knowledge-cases/{case_id}")
    def knowledge_case_detail(
        workspace_id: str,
        case_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return build_knowledge_case_detail(db, user=user, workspace=workspace, case_id=case_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge-cases")
    def add_knowledge_case(
        workspace_id: str,
        request: KnowledgeCaseCreateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                case = create_knowledge_case(
                    db,
                    user=user,
                    workspace=workspace,
                    title=request.title,
                    description=request.description,
                    tags=request.tags,
                    metadata=request.metadata,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.case.create",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_case",
                    resource_id=case.id,
                    summary="Created a knowledge case.",
                )
                return {"case": serialize_knowledge_case(case)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.patch("/api/workspaces/{workspace_id}/knowledge-cases/{case_id}")
    def patch_knowledge_case(
        workspace_id: str,
        case_id: str,
        request: KnowledgeCaseUpdateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                case = get_owned_knowledge_case(db, user=user, case_id=case_id)
                if case.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge case not found.")
                updated = update_knowledge_case(
                    db,
                    user=user,
                    case_id=case_id,
                    title=request.title,
                    description=request.description,
                    tags=request.tags,
                    metadata=request.metadata,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.case.update",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_case",
                    resource_id=updated.id,
                    summary="Updated a knowledge case.",
                )
                return {"case": serialize_knowledge_case(updated)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/workspaces/{workspace_id}/knowledge-cases/{case_id}")
    def remove_knowledge_case(
        workspace_id: str,
        case_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                case = get_owned_knowledge_case(db, user=user, case_id=case_id)
                if case.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge case not found.")
                delete_knowledge_case(db, user=user, case_id=case_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.case.delete",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_case",
                    resource_id=case_id,
                    summary="Deleted a knowledge case.",
                )
                return {"status": "deleted"}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge-cases/{case_id}/items")
    def add_knowledge_case_item(
        workspace_id: str,
        case_id: str,
        request: KnowledgeCaseItemCreateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                item, created = add_item_to_knowledge_case(
                    db,
                    user=user,
                    workspace=workspace,
                    case_id=case_id,
                    item_type=request.item_type,
                    ref_id=request.ref_id,
                    metadata=request.metadata,
                )
                detail = build_knowledge_case_detail(db, user=user, workspace=workspace, case_id=case_id)
                payload = next((entry for entry in detail["items"] if entry["id"] == item.id), None)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.case.item.add",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_case_item",
                    resource_id=item.id,
                    summary="Added an item to a knowledge case.",
                    metadata={"item_type": request.item_type, "created": created},
                )
                return {"item": payload, "created": created, "case": detail["case"]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/workspaces/{workspace_id}/knowledge-cases/{case_id}/items/{item_id}")
    def remove_knowledge_case_item(
        workspace_id: str,
        case_id: str,
        item_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                remove_item_from_knowledge_case(db, user=user, workspace=workspace, case_id=case_id, item_id=item_id)
                detail = build_knowledge_case_detail(db, user=user, workspace=workspace, case_id=case_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.case.item.remove",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_case_item",
                    resource_id=item_id,
                    summary="Removed an item from a knowledge case.",
                )
                return {"status": "deleted", "case": detail["case"], "items": detail["items"]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge")
    def add_knowledge(
        workspace_id: str,
        request: KnowledgeCreateRequest,
        raw_request: Request,
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
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.record.create",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=record.id,
                    summary="Created a knowledge record.",
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        record,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge/digest")
    def create_workspace_digest(
        workspace_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = create_workspace_digest_record(db, user=user, workspace=workspace)
                _audit_workspace_action(
                    db,
                    request=request,
                    action="knowledge.digest.create",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=record.id,
                    summary="Created a workspace digest record.",
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        record,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.patch("/api/workspaces/{workspace_id}/knowledge/{record_id}")
    def update_workspace_knowledge(
        workspace_id: str,
        record_id: str,
        request: KnowledgeUpdateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                updated = update_knowledge_record(
                    db,
                    user=user,
                    record_id=record_id,
                    title=request.title,
                    content=request.content,
                    tags=request.tags,
                    metadata=request.metadata,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.record.update",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=updated.id,
                    summary="Updated a knowledge record.",
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        updated,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge/{record_id}/archive")
    def archive_workspace_knowledge(
        workspace_id: str,
        record_id: str,
        request: KnowledgeArchiveRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                archived = archive_knowledge_record(db, user=user, record_id=record_id, reason=request.reason)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.record.archive",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=archived.id,
                    summary="Archived a knowledge record.",
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        archived,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge/{record_id}/restore")
    def restore_workspace_knowledge(
        workspace_id: str,
        record_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                restored = restore_knowledge_record(db, user=user, record_id=record_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.record.restore",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=restored.id,
                    summary="Restored a knowledge record.",
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        restored,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/workspaces/{workspace_id}/knowledge/{record_id}")
    def delete_workspace_knowledge(
        workspace_id: str,
        record_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                detached = detach_knowledge_record_references(db, user=user, workspace=workspace, record_id=record_id)
                delete_knowledge_record(db, user=user, record_id=record_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="knowledge.record.delete",
                    user=user,
                    workspace=workspace,
                    resource_type="knowledge_record",
                    resource_id=record_id,
                    summary="Deleted a knowledge record.",
                    metadata={"detached_references": detached},
                )
                return {"status": "deleted", "detached_references": detached}
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
        request: Request,
        file: UploadFile = File(...),
        description: str = Form(default=""),
        source_url: str = Form(default=""),
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            payload = await _read_upload_payload(file, max_bytes=MAX_UPLOAD_BYTES)
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
                _audit_workspace_action(
                    db,
                    request=request,
                    action="asset.upload",
                    user=user,
                    workspace=workspace,
                    resource_type="asset",
                    resource_id=asset.id,
                    summary="Uploaded an asset.",
                    metadata={"kind": asset.kind},
                )
                return {"asset": serialize_asset(asset)}
        except Exception as exc:
            _raise_http_error(exc)
        finally:
            await file.close()

    @app.get("/api/assets/{asset_id}/download")
    def download_asset(
        asset_id: str,
        request: Request,
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
                metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
                original_name = metadata.get("original_filename") or Path(asset.title or "").name or f"asset-{asset.id}"
                content_disposition = _build_attachment_content_disposition(original_name)
                _audit_workspace_action(
                    db,
                    request=request,
                    action="asset.download",
                    user=user,
                    workspace=None,
                    resource_type="asset",
                    resource_id=asset.id,
                    summary="Downloaded an asset.",
                    metadata={"kind": asset.kind},
                )
                if not is_remote_asset_reference(asset.file_path):
                    local_path = resolve_local_asset_path(settings, asset.file_path)
                    return FileResponse(
                        local_path,
                        media_type=asset.content_type or "application/octet-stream",
                        headers={
                            "Content-Disposition": content_disposition,
                            "X-Content-Type-Options": "nosniff",
                        },
                    )
                payload = load_asset_bytes(settings, asset.file_path)
                return Response(
                    content=payload,
                    media_type=asset.content_type or "application/octet-stream",
                    headers={
                        "Content-Disposition": content_disposition,
                        "X-Content-Type-Options": "nosniff",
                    },
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

    @app.get("/api/workspaces/{workspace_id}/data-lab/agent/llm-config")
    def get_data_lab_agent_llm_config(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return get_agent_llm_config(settings, db, user=user, workspace=workspace)
        except Exception as exc:
            _raise_http_error(exc)

    @app.put("/api/workspaces/{workspace_id}/data-lab/agent/llm-config")
    def update_data_lab_agent_llm_config(
        workspace_id: str,
        request: DataLabAgentLLMConfigRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = update_agent_llm_config(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    enabled=request.enabled,
                    base_url=request.base_url,
                    api_key=request.api_key,
                    clear_api_key=request.clear_api_key,
                    coder_model=request.coder_model,
                    reviewer_model=request.reviewer_model,
                    report_model=request.report_model,
                    label=request.label,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.llm_config.update",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_agent_llm_config",
                    resource_id=workspace.id,
                    summary="Updated Data Lab Agent scoped LLM config.",
                    metadata={"enabled": request.enabled, "base_url_configured": bool(request.base_url.strip())},
                )
                return result
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/data-lab/agent/llm-config/test")
    def test_data_lab_agent_llm_config(
        workspace_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = test_agent_llm_config(settings, db, user=user, workspace=workspace)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.llm_config.test",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_agent_llm_config",
                    resource_id=workspace.id,
                    summary="Tested Data Lab Agent scoped LLM config.",
                    metadata={"status": result.get("status")},
                )
                return result
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/data-lab/agent/sessions")
    def create_data_lab_agent_session(
        workspace_id: str,
        request: DataLabAgentSessionCreateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = create_agent_session(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_ids=request.asset_ids,
                    title=request.title,
                    language=request.language,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.session.create",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_run",
                    resource_id=str(result.get("session", {}).get("run_id") or ""),
                    summary="Created a Data Lab Agent session.",
                    metadata={"asset_count": len(request.asset_ids)},
                )
                return result
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}")
    def get_data_lab_agent_session(
        workspace_id: str,
        run_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return get_agent_session(db, user=user, workspace=workspace, run_id=run_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/messages")
    def send_data_lab_agent_session_message(
        workspace_id: str,
        run_id: str,
        request: DataLabAgentMessageRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = send_agent_message(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    run_id=run_id,
                    message=request.message,
                    user_code=request.user_code,
                    intervention_note=request.intervention_note,
                    execution_mode=request.execution_mode,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.message",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_run",
                    resource_id=run_id,
                    summary="Ran a Data Lab Agent message.",
                    metadata={"status": str(result.get("message", {}).get("status") or "")},
                )
                return result
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/report")
    def generate_data_lab_agent_session_report(
        workspace_id: str,
        run_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = generate_agent_report(settings, db, user=user, workspace=workspace, run_id=run_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.report",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_run",
                    resource_id=run_id,
                    summary="Generated a Data Lab Agent report.",
                )
                return result
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/data-lab/agent/sessions/{run_id}/notebook")
    def export_data_lab_agent_session_notebook(
        workspace_id: str,
        run_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> Response:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                notebook_path = export_agent_notebook(settings, db, user=user, workspace=workspace, run_id=run_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="data_lab.agent.notebook",
                    user=user,
                    workspace=workspace,
                    resource_type="data_lab_run",
                    resource_id=run_id,
                    summary="Exported a Data Lab Agent notebook.",
                )
                return FileResponse(
                    notebook_path,
                    media_type="application/x-ipynb+json",
                    headers={
                        "Content-Disposition": _build_attachment_content_disposition(notebook_path.name),
                        "X-Content-Type-Options": "nosniff",
                    },
                )
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

    @app.get("/api/optimization/results/{record_id}")
    def optimization_result(
        record_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return _optimization_api()["build_result_detail"](db, user=user, record_id=record_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/optimization/results")
    def workspace_optimization_results(
        workspace_id: str,
        limit: int = 20,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                optimization_api = _optimization_api()
                return {
                    "items": optimization_api["serialize_result_list"](
                        optimization_api["list_results"](db, user=user, workspace=workspace, limit=limit)
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/analysis/prepare")
    def prepare_analysis_sample(
        workspace_id: str,
        request: DatasetPrepareRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        token = _token_from_headers(authorization, x_session_token)
        run_id = ""
        resolved: dict[str, Any] | None = None
        request_payload = request.model_dump(exclude_unset=True)
        try:
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                resolved = _resolve_template_execution(
                    request,
                    db=db,
                    user=user,
                    workspace=workspace,
                    template_scope="workspace",
                    workflow_type="data_processing",
                    family=request.workflow_group or "sample_preparation",
                )
                payload = resolved["payload"]
                run = create_data_lab_run(
                    db,
                    user=user,
                    workspace=workspace,
                    workflow_type="processing",
                    family=str(payload.get("workflow_group") or request.workflow_group or "sample_preparation"),
                    method=str(payload.get("workflow_group") or request.workflow_group or "sample_preparation"),
                    title="Dataset preparation",
                    source_asset_id=str(payload.get("asset_id", request.asset_id) or ""),
                    request_payload=request_payload,
                )
                run_id = run.id

            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                payload = (resolved or {}).get("payload", {})
                result = prepare_dataset_asset(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    asset_id=payload.get("asset_id", request.asset_id),
                    workflow_group=payload.get("workflow_group", request.workflow_group),
                    include_columns=payload.get("include_columns", request.include_columns),
                    required_columns=payload.get("required_columns", request.required_columns),
                    numeric_columns=payload.get("numeric_columns", request.numeric_columns),
                    binary_columns=payload.get("binary_columns", request.binary_columns),
                    date_columns=payload.get("date_columns", request.date_columns),
                    impute_columns=payload.get("impute_columns", request.impute_columns),
                    impute_method=payload.get("impute_method", request.impute_method),
                    winsorize_columns=payload.get("winsorize_columns", request.winsorize_columns),
                    winsor_lower_quantile=payload.get("winsor_lower_quantile", request.winsor_lower_quantile),
                    winsor_upper_quantile=payload.get("winsor_upper_quantile", request.winsor_upper_quantile),
                    log_transform_columns=payload.get("log_transform_columns", request.log_transform_columns),
                    standardize_columns=payload.get("standardize_columns", request.standardize_columns),
                    minmax_scale_columns=payload.get("minmax_scale_columns", request.minmax_scale_columns),
                    outlier_columns=payload.get("outlier_columns", request.outlier_columns),
                    outlier_method=payload.get("outlier_method", request.outlier_method),
                    outlier_threshold=payload.get("outlier_threshold", request.outlier_threshold),
                    sort_column=payload.get("sort_column", request.sort_column),
                    time_group_column=payload.get("time_group_column", request.time_group_column),
                    difference_columns=payload.get("difference_columns", request.difference_columns),
                    return_columns=payload.get("return_columns", request.return_columns),
                    return_method=payload.get("return_method", request.return_method),
                    lag_columns=payload.get("lag_columns", request.lag_columns),
                    lag_periods=payload.get("lag_periods", request.lag_periods),
                    lead_columns=payload.get("lead_columns", request.lead_columns),
                    lead_periods=payload.get("lead_periods", request.lead_periods),
                    rolling_mean_columns=payload.get("rolling_mean_columns", request.rolling_mean_columns),
                    rolling_volatility_columns=payload.get("rolling_volatility_columns", request.rolling_volatility_columns),
                    rolling_window=payload.get("rolling_window", request.rolling_window),
                    drop_duplicates=payload.get("drop_duplicates", request.drop_duplicates),
                    drop_missing_required=payload.get("drop_missing_required", request.drop_missing_required),
                    template_id=resolved["template_id"],
                    template_name=resolved["template_name"],
                    variant_label=resolved["variant_label"],
                    variant_spec=resolved["variant_spec"],
                    effective_specification=resolved["effective_specification"],
                )
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_success(
                        db,
                        user=user,
                        run_id=run_id,
                        title=result.get("asset", {}).get("title") or "Dataset preparation",
                        summary=(
                            f"Rows after prepare: {((result.get('summary') or {}).get('rows_after_prepare'))}"
                            if isinstance(result.get("summary"), dict) and (result.get("summary") or {}).get("rows_after_prepare") is not None
                            else "Processing result is ready for review."
                        ),
                        detail_path=result.get("detail_path") or result.get("result_detail_path") or "",
                        result_asset_id=str((result.get("asset") or {}).get("id") or ""),
                        output_payload=_processing_run_output_payload(result),
                    )
            return result
        except Exception as exc:
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_failure(
                        db,
                        user=user,
                        run_id=run_id,
                        error=exc,
                        title="Dataset preparation",
                        output_payload={
                            "processing_family": str(((resolved or {}).get("payload") or {}).get("workflow_group") or request.workflow_group or "sample_preparation"),
                        },
                    )
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
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        token = _token_from_headers(authorization, x_session_token)
        run_id = ""
        payload: dict[str, Any] = {}
        resolved: dict[str, Any] | None = None
        try:
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                _consume_workspace_rate_limit(
                    db,
                    bucket_type="lab.model.run",
                    user=user,
                    workspace=workspace,
                    limit=_MODEL_RUN_LIMIT,
                )
                resolved = _resolve_template_execution(
                    request,
                    db=db,
                    user=user,
                    workspace=workspace,
                    template_scope="workspace",
                    workflow_type="model",
                    family=request.model_family or "",
                    method=request.model_type or "",
                )
                request_payload = request.model_dump()
                payload = {**request_payload, **resolved["payload"]}
                def _pick_defined(*values: Any) -> Any:
                    for value in values:
                        if value is None:
                            continue
                        if isinstance(value, str) and not value.strip():
                            continue
                        return value
                    return None

                payload["cutoff"] = _pick_defined(
                    resolved["payload"].get("kink_point"),
                    resolved["payload"].get("cutoff"),
                    resolved["payload"].get("rdd_cutoff"),
                    request_payload.get("kink_point") if request_payload.get("kink_point") not in {0, 0.0} else None,
                    request_payload.get("cutoff") if request_payload.get("cutoff") not in {0, 0.0} else None,
                    request_payload.get("rdd_cutoff") if request_payload.get("rdd_cutoff") not in {0, 0.0} else None,
                    request.kink_point if request.kink_point not in {0, 0.0} else None,
                    request.cutoff if request.cutoff not in {0, 0.0} else None,
                    request.rdd_cutoff if request.rdd_cutoff not in {0, 0.0} else None,
                    0.0,
                )
                payload["bandwidth"] = _pick_defined(
                    resolved["payload"].get("bandwidth"),
                    resolved["payload"].get("rdd_bandwidth"),
                    request_payload.get("bandwidth") if request_payload.get("bandwidth") not in {0, 0.0} else None,
                    request_payload.get("rdd_bandwidth") if request_payload.get("rdd_bandwidth") not in {0, 0.0} else None,
                    request.bandwidth if request.bandwidth not in {0, 0.0} else None,
                    request.rdd_bandwidth if request.rdd_bandwidth not in {0, 0.0} else None,
                    0.0,
                )
                payload["polynomial_order"] = _pick_defined(
                    resolved["payload"].get("polynomial_order"),
                    resolved["payload"].get("rdd_polynomial_order"),
                    request_payload.get("polynomial_order"),
                    request_payload.get("rdd_polynomial_order"),
                    request.rdd_polynomial_order,
                    1,
                )
                model_kwargs = {
                    name: payload[name]
                    for name in _RUN_MODEL_ANALYSIS_PARAMETER_NAMES
                    if name in payload
                }
                model_kwargs.update(
                    template_id=resolved["template_id"],
                    template_name=resolved["template_name"],
                    variant_label=resolved["variant_label"],
                    variant_spec=resolved["variant_spec"],
                    effective_specification=resolved["effective_specification"],
                )
                run = create_data_lab_run(
                    db,
                    user=user,
                    workspace=workspace,
                    workflow_type="model",
                    family=str(payload.get("model_family") or request.model_family or ""),
                    method=str(payload.get("model_type") or request.model_type or ""),
                    title=str(payload.get("model_type") or request.model_type or "Model run"),
                    source_asset_id=str(payload.get("asset_id") or request.asset_id or ""),
                    request_payload=request_payload,
                )
                run_id = run.id

            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                model_kwargs = {
                    name: payload[name]
                    for name in _RUN_MODEL_ANALYSIS_PARAMETER_NAMES
                    if name in payload
                }
                model_kwargs.update(
                    template_id=resolved["template_id"],
                    template_name=resolved["template_name"],
                    variant_label=resolved["variant_label"],
                    variant_spec=resolved["variant_spec"],
                    effective_specification=resolved["effective_specification"],
                )
                result = run_model_analysis(
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    **model_kwargs,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="lab.model.run",
                    user=user,
                    workspace=workspace,
                    resource_type="analysis_result",
                    resource_id=str(result.get("result_record", {}).get("id") or result.get("record_id") or ""),
                    summary="Ran a model analysis.",
                    metadata={"model_family": payload.get("model_family"), "model_type": payload.get("model_type")},
                )
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_success(
                        db,
                        user=user,
                        run_id=run_id,
                        title=result.get("model_label") or result.get("model_type") or "Model run",
                        summary=str(
                            result.get("equation")
                            or (result.get("narrative") or ["Model result is ready for review."])[0]
                            or "Model result is ready for review."
                        ),
                        detail_path=result.get("detail_path") or result.get("result_detail_path") or "",
                        result_record_id=str(result.get("result_record_id") or result.get("record_id") or ""),
                        output_payload=_model_run_output_payload(result),
                    )
            return result
        except Exception as exc:
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_failure(
                        db,
                        user=user,
                        run_id=run_id,
                        error=exc,
                        title=str(payload.get("model_type") or request.model_type or "Model run"),
                        output_payload={
                            "model_family": str(payload.get("model_family") or request.model_family or ""),
                            "model_type": str(payload.get("model_type") or request.model_type or ""),
                        },
                    )
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

    @app.post("/api/workspaces/{workspace_id}/optimization/run")
    def run_optimization(
        workspace_id: str,
        request: OptimizationRunRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        token = _token_from_headers(authorization, x_session_token)
        run_id = ""
        payload: dict[str, Any] = {}
        resolved: dict[str, Any] | None = None
        try:
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                _consume_workspace_rate_limit(
                    db,
                    bucket_type="lab.optimization.run",
                    user=user,
                    workspace=workspace,
                    limit=_OPTIMIZATION_RUN_LIMIT,
                )
                resolved = _resolve_template_execution(
                    request,
                    db=db,
                    user=user,
                    workspace=workspace,
                    template_scope="workspace",
                    workflow_type="optimization",
                    family="optimization",
                    method="suite",
                )
                payload = resolved["payload"]
                run = create_data_lab_run(
                    db,
                    user=user,
                    workspace=workspace,
                    workflow_type="optimization",
                    family="optimization",
                    method="suite",
                    title=str(payload.get("suite_label") or request.suite_label or "Optimization Suite"),
                    request_payload=request.model_dump(exclude_unset=True),
                )
                run_id = run.id

            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                result = _optimization_api()["run_suite"](
                    settings,
                    db,
                    user=user,
                    workspace=workspace,
                    suite_label=payload.get("suite_label", request.suite_label),
                    optimizer_names=payload.get("optimizer_names", request.optimizer_names),
                    function_names=payload.get("function_names", request.function_names),
                    dimension=payload.get("dimension", request.dimension),
                    epoch=payload.get("epoch", request.epoch),
                    pop_size=payload.get("pop_size", request.pop_size),
                    runs=payload.get("runs", request.runs),
                    workers=payload.get("workers", request.workers),
                    seed_base=payload.get("seed_base", request.seed_base),
                    template_id=resolved["template_id"],
                    template_name=resolved["template_name"],
                    variant_label=resolved["variant_label"],
                    variant_spec=resolved["variant_spec"],
                    effective_specification=resolved["effective_specification"],
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="lab.optimization.run",
                    user=user,
                    workspace=workspace,
                    resource_type="optimization_result",
                    resource_id=str(result.get("result", {}).get("id") or result.get("result_id") or ""),
                    summary="Ran an optimization suite.",
                    metadata={"suite_label": payload.get("suite_label", request.suite_label)},
                )
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_success(
                        db,
                        user=user,
                        run_id=run_id,
                        title=str((result.get("result") or {}).get("suite_label") or payload.get("suite_label") or request.suite_label),
                        summary=str(
                            (((result.get("result") or {}).get("summary") or {}).get("headline"))
                            or "Optimization result is ready for review."
                        ),
                        detail_path=str((result.get("result") or {}).get("detail_path") or (result.get("result") or {}).get("result_detail_path") or ""),
                        result_record_id=str((result.get("result") or {}).get("result_record_id") or (result.get("record") or {}).get("id") or ""),
                        output_payload=_optimization_run_output_payload(result),
                    )
            return result
        except Exception as exc:
            if run_id:
                with session_scope() as db:
                    user = get_current_user(db, token)
                    finalize_data_lab_run_failure(
                        db,
                        user=user,
                        run_id=run_id,
                        error=exc,
                        title=str(payload.get("suite_label") or request.suite_label or "Optimization Suite"),
                        output_payload={"suite_label": str(payload.get("suite_label") or request.suite_label or "Optimization Suite")},
                    )
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/lab-templates")
    def workspace_lab_templates(
        workspace_id: str,
        template_scope: str = "workspace",
        workflow_type: str = "",
        family: str = "",
        method: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = list_lab_templates(
                    db,
                    user=user,
                    workspace=workspace,
                    template_scope=template_scope,
                    workflow_type=workflow_type,
                    family=family,
                    method=method,
                )
                return {"items": [serialize_lab_template(item) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/lab-templates")
    def add_workspace_lab_template(
        workspace_id: str,
        request: LabTemplateCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                template = create_lab_template(
                    db,
                    user=user,
                    workspace=workspace,
                    template_scope=request.template_scope,
                    workflow_type=request.workflow_type,
                    family=request.family,
                    method=request.method,
                    name=request.name,
                    description=request.description,
                    specification=request.specification,
                    metadata=request.metadata,
                    is_default=request.is_default,
                )
                return {"template": serialize_lab_template(template)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/openalex/search")
    def openalex_search(
        q: str,
        max_results: int = 10,
        open_access_only: bool = False,
        request: Request = None,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            with session_scope() as db:
                _require_feature_access(db, request, authorization, x_session_token)
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

    @app.post("/api/workspaces/{workspace_id}/literature/{literature_entry_id}/import-pdf")
    def import_literature_pdf(
        workspace_id: str,
        literature_entry_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return import_literature_pdf_asset(
                    db,
                    settings,
                    user=user,
                    workspace=workspace,
                    literature_entry_id=literature_entry_id,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/literature/import-pdfs")
    def import_literature_pdfs(
        workspace_id: str,
        request: LiteratureBatchRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return import_literature_pdf_assets(
                    db,
                    settings,
                    user=user,
                    workspace=workspace,
                    literature_entry_ids=request.entry_ids,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/literature/{literature_entry_id}/import-knowledge")
    def import_literature_knowledge(
        workspace_id: str,
        literature_entry_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return import_literature_knowledge_record(
                    db,
                    user=user,
                    workspace=workspace,
                    literature_entry_id=literature_entry_id,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/literature/import-knowledge")
    def import_literature_knowledge_batch(
        workspace_id: str,
        request: LiteratureBatchRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return import_literature_knowledge_records(
                    db,
                    user=user,
                    workspace=workspace,
                    literature_entry_ids=request.entry_ids,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/literature/{literature_entry_id}/derive-note")
    def derive_literature_note(
        workspace_id: str,
        literature_entry_id: str,
        request: LiteratureDerivedNoteRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return create_literature_followup_note(
                    db,
                    user=user,
                    workspace=workspace,
                    literature_entry_id=literature_entry_id,
                    mode=request.mode,
                )
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

    @app.post("/api/workspaces/{workspace_id}/briefings/{briefing_id}/import-knowledge")
    def import_briefing_knowledge(
        workspace_id: str,
        briefing_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return import_briefing_knowledge_record(db, user=user, workspace=workspace, briefing_id=briefing_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/briefings/generate")
    def create_briefing(
        workspace_id: str,
        request: BriefingCreateRequest,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                _consume_workspace_rate_limit(
                    db,
                    bucket_type="workspace.briefing.generate",
                    user=user,
                    workspace=workspace,
                    limit=_BRIEFING_GENERATE_LIMIT,
                )
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
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="briefing.generate",
                    user=user,
                    workspace=workspace,
                    resource_type="briefing",
                    resource_id=briefing.id,
                    summary="Generated a private briefing.",
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
                jobs = list_schedule_jobs(db, user=user, workspace=workspace)
                return {"items": _schedule_payloads(db, user=user, workspace=workspace, jobs=jobs)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/schedules")
    def add_schedule(
        workspace_id: str,
        request: ScheduleCreateRequest,
        raw_request: Request,
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
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="schedule.create",
                    user=user,
                    workspace=workspace,
                    resource_type="schedule",
                    resource_id=schedule.id,
                    summary="Created a recurring schedule.",
                    metadata={"job_type": schedule.job_type},
                )
                return {"schedule": serialize_schedule(schedule)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.patch("/api/workspaces/{workspace_id}/schedules/{schedule_id}")
    def patch_schedule(
        workspace_id: str,
        schedule_id: str,
        request: ScheduleUpdateRequest,
        raw_request: Request,
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
                schedule = update_schedule_job(
                    db,
                    user=user,
                    workspace=workspace,
                    schedule_id=schedule_id,
                    name=request.name,
                    timezone_name=request.timezone_name,
                    local_time_value=request.local_time,
                    integration_id=request.integration_id,
                    enabled=request.enabled,
                    config=request.config,
                )
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="schedule.update",
                    user=user,
                    workspace=workspace,
                    resource_type="schedule",
                    resource_id=schedule.id,
                    summary="Updated a recurring schedule.",
                    metadata={"enabled": schedule.enabled},
                )
                jobs = [schedule]
                payload = _schedule_payloads(db, user=user, workspace=workspace, jobs=jobs)[0]
                return {"schedule": payload}
        except Exception as exc:
            _raise_http_error(exc)

    @app.delete("/api/workspaces/{workspace_id}/schedules/{schedule_id}")
    def remove_schedule(
        workspace_id: str,
        schedule_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                schedule = get_owned_schedule_job(db, user=user, workspace=workspace, schedule_id=schedule_id)
                summary = schedule.name
                delete_schedule_job(db, user=user, workspace=workspace, schedule_id=schedule_id)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="schedule.delete",
                    user=user,
                    workspace=workspace,
                    resource_type="schedule",
                    resource_id=schedule_id,
                    summary=f"Deleted recurring schedule: {summary}",
                )
                return {"deleted": True, "schedule_id": schedule_id}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/schedules/{schedule_id}/run-now")
    def run_schedule_now(
        workspace_id: str,
        schedule_id: str,
        raw_request: Request,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                _consume_workspace_rate_limit(
                    db,
                    bucket_type="workspace.schedule.run_now",
                    user=user,
                    workspace=workspace,
                    limit=_SCHEDULE_RUN_NOW_LIMIT,
                )
                run = run_schedule_job_now(db, settings, user=user, workspace=workspace, schedule_id=schedule_id)
                schedule = get_owned_schedule_job(db, user=user, workspace=workspace, schedule_id=schedule_id)
                payload = serialize_job_run(run, job=schedule)
                _audit_workspace_action(
                    db,
                    request=raw_request,
                    action="schedule.run_now",
                    user=user,
                    workspace=workspace,
                    resource_type="schedule",
                    resource_id=schedule.id,
                    summary="Executed a schedule immediately.",
                    metadata={"run_status": payload.get("status", "")},
                )
                schedule_payload = _schedule_payloads(db, user=user, workspace=workspace, jobs=[schedule])[0]
                return {"run": payload, "schedule": schedule_payload}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/schedules/{schedule_id}/runs")
    def schedule_runs(
        workspace_id: str,
        schedule_id: str,
        limit: int = 20,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                schedule = get_owned_schedule_job(db, user=user, workspace=workspace, schedule_id=schedule_id)
                rows = list_job_runs(db, user=user, workspace=workspace, schedule_id=schedule_id, limit=limit)
                return {"items": [serialize_job_run(item, job=schedule) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/job-runs")
    def workspace_job_runs(
        workspace_id: str,
        limit: int = 40,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                jobs = {item.id: item for item in list_schedule_jobs(db, user=user, workspace=workspace)}
                rows = list_job_runs(db, user=user, workspace=workspace, limit=limit)
                return {"items": [serialize_job_run(item, job=jobs.get(item.job_id)) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/teams")
    def teams_list(
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                return {"items": list_teams_for_user(db, user=user)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/teams")
    def create_team_endpoint(
        request: TeamCreateRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                team = create_team(db, user=user, name=request.name, description=request.description)
                return {"team": serialize_team(team, role="owner")}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/team")
    def attach_workspace_team_endpoint(
        workspace_id: str,
        request: WorkspaceTeamAttachRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                updated = attach_workspace_to_team(db, user=user, workspace=workspace, team_id=request.team_id)
                return {"workspace": serialize_workspace(updated)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/quality/scorecard")
    def workspace_quality_scorecard(
        workspace_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return build_delivery_scorecard(
                    db,
                    user=user,
                    workspace=workspace,
                    settings=settings,
                    auto_refresh_if_missing=True,
                )
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/quality/runs")
    def workspace_quality_runs(
        workspace_id: str,
        limit: int = 20,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return {
                    "items": list_run_quality_snapshots(
                        db,
                        user=user,
                        workspace=workspace,
                        limit=limit,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/teams/{team_id}/library")
    def team_library_list(
        team_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                rows = list_team_library_records(db, user=user, team_id=team_id)
                return {"items": [serialize_team_library_record(item) for item in rows]}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/teams/{team_id}/library/{record_id}")
    def team_library_detail(
        team_id: str,
        record_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                record = get_team_library_record_for_user(db, user=user, team_id=team_id, record_id=record_id)
                payload = serialize_team_library_record(record)
                payload["content"] = record.content or ""
                return {"record": payload}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/teams/{team_id}/library/{record_id}/clone")
    def team_library_clone(
        team_id: str,
        record_id: str,
        request: TeamLibraryCloneRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=request.workspace_id)
                record = get_team_library_record_for_user(db, user=user, team_id=team_id, record_id=record_id)
                cloned = clone_team_library_record_to_workspace(
                    db,
                    user=user,
                    target_workspace=workspace,
                    record=record,
                    title_override=request.title,
                    include_source_metadata=request.include_source_metadata,
                )
                return {
                    "record": _serialize_knowledge_record_payload(
                        db,
                        cloned,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/agent-runs")
    def workspace_agent_runs(
        workspace_id: str,
        limit: int = 20,
        status: str = "",
        current_stage: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = list_agent_runs(
                    db,
                    user=user,
                    workspace=workspace,
                    limit=limit,
                    status=status,
                    current_stage=current_stage,
                )
                return {
                    "items": [
                        _serialize_agent_run_payload(
                            item,
                            settings=settings,
                            auto_refresh_if_missing=True,
                        )
                        for item in rows
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/research/runs")
    def workspace_research_runs(
        workspace_id: str,
        limit: int = 20,
        status: str = "",
        current_stage: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = list_agent_runs(
                    db,
                    user=user,
                    workspace=workspace,
                    limit=limit,
                    status=status,
                    current_stage=current_stage,
                )
                return {
                    "items": [
                        _serialize_agent_run_payload(
                            item,
                            settings=settings,
                            auto_refresh_if_missing=True,
                        )
                        for item in rows
                    ]
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/agent-runs/eval-candidates")
    def workspace_agent_run_eval_candidates(
        workspace_id: str,
        limit: int = 20,
        status: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = list_agent_runs(db, user=user, workspace=workspace, limit=limit, status=status)
                return build_agent_eval_dataset_preview(rows)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/research/runs/eval-candidates")
    def workspace_research_run_eval_candidates(
        workspace_id: str,
        limit: int = 20,
        status: str = "",
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                rows = list_agent_runs(db, user=user, workspace=workspace, limit=limit, status=status)
                return build_agent_eval_dataset_preview(rows)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/agent-runs/{run_id}")
    def workspace_agent_run_detail(
        workspace_id: str,
        run_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                run = get_owned_agent_run(db, user=user, workspace=workspace, run_id=run_id)
                return {
                    "run": _serialize_agent_run_detail_payload(
                        run,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    )
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/research/runs/{run_id}")
    def workspace_research_run_detail(
        workspace_id: str,
        run_id: str,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                run = get_owned_agent_run(db, user=user, workspace=workspace, run_id=run_id)
                eval_candidate = (
                    build_agent_eval_candidate(run)
                    if (run.status or "").strip().lower() in {"saved", "blocked", "failed"}
                    else None
                )
                return {
                    "run": _serialize_agent_run_detail_payload(
                        run,
                        settings=settings,
                        auto_refresh_if_missing=True,
                    ),
                    "eval_candidate": eval_candidate,
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/research/runs")
    def create_workspace_research_run(
        workspace_id: str,
        request: ResearchRunRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                payload = start_workspace_research_run(
                    settings=settings,
                    db=db,
                    user=user,
                    workspace=workspace,
                    request=request,
                )
                _audit_workspace_action(
                    db,
                    request=None,
                    action="workspace.research.run",
                    user=user,
                    workspace=workspace,
                    resource_type="agent_run",
                    resource_id=payload["run"]["id"],
                    summary="Queued a research agent run.",
                    metadata={
                        "status": payload["run"]["status"],
                        "queue_status": payload["run"].get("queue_status", ""),
                        "attachment_count": payload["run"].get("attachment_count", 0),
                    },
                )
                return payload
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/research/runs/{run_id}/retry")
    def retry_workspace_research(
        workspace_id: str,
        run_id: str,
        request: ResearchRunRetryRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                run = get_owned_agent_run(db, user=user, workspace=workspace, run_id=run_id)
                payload = retry_workspace_research_run(
                    settings=settings,
                    db=db,
                    user=user,
                    workspace=workspace,
                    run=run,
                    request=request,
                )
                _audit_workspace_action(
                    db,
                    request=None,
                    action="workspace.research.retry",
                    user=user,
                    workspace=workspace,
                    resource_type="agent_run",
                    resource_id=payload["run"]["id"],
                    summary="Re-queued a research agent run.",
                    metadata={
                        "status": payload["run"]["status"],
                        "queue_status": payload["run"].get("queue_status", ""),
                    },
                )
                return payload
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/research/runs/{run_id}/publish")
    def publish_workspace_research_run(
        workspace_id: str,
        run_id: str,
        request: ResearchRunPublishRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                run = get_owned_agent_run(db, user=user, workspace=workspace, run_id=run_id)
                delivery_review, engineering_gate = review_agent_run_delivery(
                    run,
                    settings=settings,
                    auto_refresh_if_missing=True,
                )
                ensure_delivery_allowed(delivery_review, engineering_gate=engineering_gate, action="publish")
                record = publish_workspace_source_to_team_library(
                    db,
                    user=user,
                    workspace=workspace,
                    team_id=request.team_id,
                    source_type="agent_run",
                    source_ref_id=run_id,
                    title_override=request.title,
                    summary_override=request.summary,
                )
                return {
                    "record": serialize_team_library_record(record),
                    "delivery_review": delivery_review,
                    "engineering_gate": engineering_gate,
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/workspaces/{workspace_id}/knowledge/{record_id}/publish")
    def publish_workspace_knowledge_record(
        workspace_id: str,
        record_id: str,
        request: KnowledgePublishRequest,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                record = get_owned_knowledge_record(db, user=user, record_id=record_id)
                if record.workspace_id != workspace.id:
                    raise FileNotFoundError("Knowledge record not found.")
                delivery_review, engineering_gate = review_knowledge_record_delivery(
                    db,
                    record,
                    settings=settings,
                    auto_refresh_if_missing=True,
                )
                ensure_delivery_allowed(delivery_review, engineering_gate=engineering_gate, action="publish")
                record = publish_workspace_source_to_team_library(
                    db,
                    user=user,
                    workspace=workspace,
                    team_id=request.team_id,
                    source_type="knowledge_record",
                    source_ref_id=record_id,
                    title_override=request.title,
                    summary_override=request.summary,
                )
                return {
                    "record": serialize_team_library_record(record),
                    "delivery_review": delivery_review,
                    "engineering_gate": engineering_gate,
                }
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/api/workspaces/{workspace_id}/data-lab/history")
    def data_lab_history(
        workspace_id: str,
        limit: int = 12,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    ) -> dict[str, Any]:
        try:
            token = _token_from_headers(authorization, x_session_token)
            with session_scope() as db:
                user = get_current_user(db, token)
                workspace = get_workspace_for_user(db, user=user, workspace_id=workspace_id)
                return _data_lab_history_payload(db, user=user, workspace=workspace, limit=max(3, min(limit, 30)))
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/api/internal/run-due-jobs", include_in_schema=False)
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

    @app.post("/api/internal/run-agent-worker", include_in_schema=False)
    def run_agent_worker(
        x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
        worker_id: str = "api-worker",
    ) -> dict[str, Any]:
        try:
            if (x_cron_secret or "").strip() != settings.get_cron_secret():
                raise PermissionError("Invalid cron secret.")
            with session_scope() as db:
                result = run_agent_worker_iteration(settings=settings, db=db, worker_id=worker_id)
                return {"result": result}
        except Exception as exc:
            _raise_http_error(exc)

    return app
