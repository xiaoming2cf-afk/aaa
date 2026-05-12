from __future__ import annotations

from dataclasses import dataclass, field

from .errors import DataLabError


@dataclass(frozen=True)
class ModelSpec:
    family: str
    model_type: str
    label: str
    required_roles: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProcessingSpec:
    family: str
    label: str
    workflow_group: str = ""


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec("econometrics_baseline", "ols", "OLS", ("dependent", "independents")),
    ModelSpec("econometrics_baseline", "did", "Difference-in-Differences", ("dependent", "treatment", "post")),
    ModelSpec("econometrics_baseline", "rdd", "Regression Discontinuity", ("dependent", "running")),
    ModelSpec("econometrics_baseline", "iv_2sls", "IV-2SLS", ("dependent", "endogenous", "instruments")),
    ModelSpec("time_series_finance", "arima", "ARIMA", ("series",)),
    ModelSpec("time_series_finance", "var", "VAR", ("series",)),
    ModelSpec("asset_pricing", "capm", "CAPM", ("dependent", "market")),
    ModelSpec("portfolio_allocation", "mean_variance", "Mean-Variance Portfolio", ("series",)),
)

SUPPORTED_MODEL_TYPES: frozenset[str] = frozenset(
    {
        "ols",
        "ppml",
        "logit",
        "probit",
        "did",
        "event_study",
        "rdd",
        "fixed_effects",
        "gravity",
        "iv_2sls",
        "panel_iv",
        "arima",
        "arch",
        "garch",
        "var",
        "svar_irf",
        "virf",
        "dy_connectedness",
        "bk_connectedness",
        "historical_var",
        "parametric_var",
        "ewma_volatility",
        "black_scholes",
        "binomial_option",
        "taylor_rule",
        "rbc_dsge",
        "mean_variance",
        "minimum_variance",
        "risk_parity",
        "capm",
        "fama_french_3",
        "altman_z",
        "dupont",
    }
)

PROCESSING_SPECS: tuple[ProcessingSpec, ...] = (
    ProcessingSpec("sample_preparation", "Sample Preparation", "sample_preparation"),
    ProcessingSpec("cleaning_transforms", "Cleaning and Transforms", "cleaning_transforms"),
    ProcessingSpec("time_series_features", "Time-Series Features", "time_series_features"),
    ProcessingSpec("visualization", "Visualization", "visualization"),
)

SUPPORTED_PROCESSING_GROUPS: frozenset[str] = frozenset(spec.workflow_group for spec in PROCESSING_SPECS)
SUPPORTED_WORKFLOW_TYPES: frozenset[str] = frozenset(
    {"data_processing", "processing", "model", "optimization", "agent_session"}
)


def normalize_workflow_type(workflow_type: str) -> str:
    normalized = str(workflow_type or "").strip()
    if not normalized:
        raise DataLabError("Workflow type is required.")
    if normalized not in SUPPORTED_WORKFLOW_TYPES:
        raise DataLabError(f"Unsupported workflow type: {normalized}.")
    return normalized


def normalize_processing_group(workflow_group: str) -> str:
    normalized = str(workflow_group or "sample_preparation").strip() or "sample_preparation"
    if normalized not in SUPPORTED_PROCESSING_GROUPS:
        raise DataLabError(f"Unsupported preparation workflow group: {normalized}.")
    return normalized


def normalize_model_type(model_type: str) -> str:
    normalized = str(model_type or "ols").strip().lower() or "ols"
    if normalized not in SUPPORTED_MODEL_TYPES:
        raise DataLabError(f"Unsupported model type: {normalized}.")
    return normalized


def is_supported_model_type(model_type: str) -> bool:
    return str(model_type or "").strip().lower() in SUPPORTED_MODEL_TYPES
