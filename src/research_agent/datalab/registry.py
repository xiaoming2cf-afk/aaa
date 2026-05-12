from __future__ import annotations

from dataclasses import dataclass, field


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

PROCESSING_SPECS: tuple[ProcessingSpec, ...] = (
    ProcessingSpec("sample_preparation", "Sample Preparation", "sample_preparation"),
    ProcessingSpec("cleaning_transforms", "Cleaning and Transforms", "cleaning_transforms"),
    ProcessingSpec("time_series_features", "Time-Series Features", "time_series_features"),
    ProcessingSpec("visualization", "Visualization", "visualization"),
)
