from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset
import statsmodels.api as sm
import statsmodels.formula.api as smf
from arch import arch_model
from arch.unitroot import ADF, KPSS, PhillipsPerron, ZivotAndrews, engle_granger
from arch.unitroot.cointegration import DynamicOLS, FullyModifiedOLS
from linearmodels import (
    AbsorbingLS,
    BetweenOLS,
    FamaMacBeth,
    FirstDifferenceOLS,
    IV2SLS as LMIV2SLS,
    IVGMM,
    IVLIML,
    PanelOLS,
    PooledOLS,
    RandomEffects,
)
from linearmodels.asset_pricing import LinearFactorModelGMM, TradedFactorModel
from linearmodels.system import IV3SLS, IVSystemGMM, SUR
from pypfopt import black_litterman, expected_returns, risk_models
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
from pypfopt.efficient_frontier import EfficientCDaR, EfficientCVaR, EfficientFrontier, EfficientSemivariance
from pypfopt.hierarchical_portfolio import HRPOpt
from sklearn.linear_model import LogisticRegression
from statsmodels.discrete.count_model import ZeroInflatedNegativeBinomialP, ZeroInflatedPoisson
from statsmodels.genmod.generalized_estimating_equations import GEE
from statsmodels.genmod.families import Gaussian, NegativeBinomial, Poisson
from statsmodels.regression.mixed_linear_model import MixedLM
from statsmodels.tsa.api import ExponentialSmoothing, VARMAX
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from statsmodels.tsa.statespace.structural import UnobservedComponents
from statsmodels.tsa.vector_ar.vecm import VECM


def _pc():
    import research_agent.platform_core as pc

    return pc


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


def _ensure_columns(frame: pd.DataFrame, required: list[str]) -> None:
    missing = [column for column in required if column and column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")


def _clean_columns(columns: list[str] | tuple[str, ...] | None) -> list[str]:
    cleaned: list[str] = []
    for column in columns or []:
        name = str(column).strip() if column is not None else ""
        if name and name not in cleaned:
            cleaned.append(name)
    return cleaned


def _serialize_rows(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    pc = _pc()
    return pc._frame_records(frame, limit=limit)


def _align_result_vector(values: Any, names: list[str]) -> pd.Series | None:
    if values is None:
        return None
    if isinstance(values, pd.Series):
        if [str(item) for item in values.index] == names:
            return values.reindex(names)
        if len(values) == len(names):
            return pd.Series(values.to_list(), index=names)
        return values
    try:
        series = pd.Series(values)
    except Exception:
        return None
    if len(series) == len(names):
        return pd.Series(series.to_list(), index=names)
    return series


def _candidate_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    figure: Any,
    filename_slug: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    pc = _pc()
    return pc._save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def _load_asset_frame(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    asset_id: str,
) -> tuple[Any, pd.DataFrame]:
    pc = _pc()
    asset = pc._analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = pc._load_analysis_frame(settings, asset, drop_duplicates=False)
    return asset, frame.copy()


def _timeseries_frame(
    frame: pd.DataFrame,
    *,
    value_columns: list[str],
    time_column: str = "",
) -> pd.DataFrame:
    pc = _pc()
    value_columns = _clean_columns(value_columns)
    required = [*value_columns, *([str(time_column).strip()] if time_column else [])]
    _ensure_columns(frame, required)
    sample = frame[required].copy()
    for column in value_columns:
        sample[column] = pc._coerce_numeric_series(sample[column])
    if time_column:
        sample = pc._sort_sample_by_time(sample, time_column)
        parsed = pd.to_datetime(sample[time_column], errors="coerce")
        if parsed.notna().sum():
            sample = sample.set_index(parsed)
            sample = sample.drop(columns=[time_column])
    sample = sample.dropna().copy()
    if len(sample) < 24:
        raise ValueError("Not enough complete observations for time-series estimation.")
    return sample


def _infer_time_offset(index: pd.Index) -> Any | None:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return None
    if index.freq is not None:
        return index.freq
    inferred = pd.infer_freq(index)
    if inferred:
        return to_offset(inferred)
    deltas = index.to_series().diff().dropna()
    if deltas.empty:
        return None
    median_delta = deltas.median()
    if pd.isna(median_delta) or median_delta <= pd.Timedelta(0):
        return None
    return median_delta


def _forecast_frame_with_time_index(
    forecast_values: Any,
    *,
    columns: list[str],
    source_index: pd.Index,
    label: str = "forecast_date",
) -> pd.DataFrame:
    forecast_frame = pd.DataFrame(forecast_values, columns=columns)
    offset = _infer_time_offset(source_index)
    if isinstance(source_index, pd.DatetimeIndex) and offset is not None and len(source_index):
        start = source_index[-1] + offset
        if isinstance(offset, pd.Timedelta):
            forecast_index = pd.DatetimeIndex([start + idx * offset for idx in range(len(forecast_frame))], name=label)
        else:
            forecast_index = pd.date_range(start=start, periods=len(forecast_frame), freq=offset, name=label)
        forecast_frame.index = forecast_index
    else:
        forecast_frame.index = pd.RangeIndex(start=1, stop=len(forecast_frame) + 1, name=label)
    return forecast_frame


def _panel_frame(
    frame: pd.DataFrame,
    *,
    dependent: str,
    regressors: list[str],
    entity_column: str,
    time_column: str,
    extra_columns: list[str] | None = None,
) -> pd.DataFrame:
    pc = _pc()
    regressors = _clean_columns(regressors)
    extra_columns = _clean_columns(extra_columns)
    required = [str(dependent).strip(), str(entity_column).strip(), str(time_column).strip(), *regressors, *extra_columns]
    _ensure_columns(frame, required)
    sample = frame[required].copy()
    sample = pc._sort_sample_by_time(sample, time_column)
    for column in [dependent, *regressors, *((extra_columns or []))]:
        if column in sample.columns:
            sample[column] = pc._coerce_numeric_series(sample[column])
    parsed_time = pd.to_datetime(sample[time_column], errors="coerce")
    if parsed_time.notna().all():
        sample[time_column] = parsed_time
    else:
        numeric_time = pd.to_numeric(sample[time_column], errors="coerce")
        if numeric_time.notna().all():
            sample[time_column] = numeric_time
        else:
            sample[time_column] = pd.Series(pd.factorize(sample[time_column].astype(str))[0] + 1, index=sample.index)
    sample = sample.dropna().copy()
    if len(sample) < 12:
        raise ValueError("Not enough complete observations for panel estimation.")
    sample[entity_column] = sample[entity_column].astype(str)
    sample = sample.set_index([entity_column, time_column]).sort_index()
    return sample


def _regression_payload(
    *,
    model_type: str,
    model_label: str,
    engine: str,
    asset: Any,
    dependent: str,
    regressors: list[str],
    sample: pd.DataFrame,
    result: Any,
    narrative_lines: list[str],
    tables: dict[str, Any] | None = None,
    figures: list[dict[str, Any]] | None = None,
    robustness_tables: dict[str, Any] | None = None,
    audit_trail: dict[str, Any] | None = None,
    extra_specification: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pc = _pc()
    raw_params = getattr(result, "params", None)
    if hasattr(raw_params, "index"):
        param_names = [str(item) for item in raw_params.index]
        aligned_params = pd.Series(raw_params).reindex(param_names)
    else:
        values = list(raw_params) if raw_params is not None else []
        param_names = [f"param_{index + 1}" for index in range(len(values))]
        aligned_params = pd.Series(values, index=param_names) if values else None
    aligned_bse = _align_result_vector(getattr(result, "bse", getattr(result, "std_errors", None)), param_names)
    aligned_tvalues = _align_result_vector(getattr(result, "tvalues", getattr(result, "tstats", None)), param_names)
    aligned_pvalues = _align_result_vector(getattr(result, "pvalues", None), param_names)

    @dataclass
    class _ResultProxy:
        params: Any
        bse: Any
        tvalues: Any
        pvalues: Any
        nobs: Any
        rsquared: Any = None
        rsquared_adj: Any = None
        prsquared: Any = None
        aic: Any = None
        bic: Any = None
        llf: Any = None
        cov_type: str = "nonrobust"

    proxy = _ResultProxy(
        params=aligned_params,
        bse=aligned_bse,
        tvalues=aligned_tvalues,
        pvalues=aligned_pvalues,
        nobs=getattr(result, "nobs", len(sample)),
        rsquared=getattr(result, "rsquared", None),
        rsquared_adj=getattr(result, "rsquared_adj", None),
        prsquared=getattr(result, "prsquared", None),
        aic=getattr(result, "aic", None),
        bic=getattr(result, "bic", None),
        llf=getattr(result, "llf", None),
        cov_type=str(getattr(result, "cov_type", "nonrobust")),
    )
    payload = pc._model_result_payload(
        model_type=model_type,
        model_label=model_label,
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=proxy,
        narrative_lines=narrative_lines,
        extra={
            "engine": engine,
            "primary_tables": list((tables or {}).keys()),
            "robustness_tables": list((robustness_tables or {}).keys()),
            "tables": {**(tables or {}), **(robustness_tables or {})},
            "figures": figures or [],
            "metrics": metrics or {},
            "specification": {"engine": engine, **(extra_specification or {})},
            "audit_trail": {"engine": engine, **(audit_trail or {})},
        },
    )
    payload["engine"] = engine
    payload["paper_output_contract"] = {
        "primary_tables": list((tables or {}).keys()),
        "robustness_tables": list((robustness_tables or {}).keys()),
        "figure_count": len(figures or []),
    }
    return payload


def _nonregression_payload(
    *,
    model_type: str,
    model_label: str,
    engine: str,
    asset: Any,
    sample: pd.DataFrame | None,
    narrative_lines: list[str],
    tables: dict[str, Any],
    figures: list[dict[str, Any]] | None = None,
    specification: dict[str, Any] | None = None,
    audit_trail: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pc = _pc()
    payload = pc._nonregression_result_payload(
        model_type=model_type,
        model_label=model_label,
        asset=asset,
        sample=sample,
        narrative_lines=narrative_lines,
        specification={"engine": engine, **(specification or {})},
        audit_trail={"engine": engine, **(audit_trail or {})},
        metrics=metrics or {},
        tables=tables,
        extra=extra or {},
    )
    payload["engine"] = engine
    payload["figures"] = figures or []
    payload["primary_tables"] = list((tables or {}).keys())
    payload["paper_output_contract"] = {
        "primary_tables": list((tables or {}).keys()),
        "figure_count": len(figures or []),
    }
    return payload


def _run_basic_panel_model(
    *,
    settings: Any,
    db: Any,
    kwargs: dict[str, Any],
    model_type: str,
    model_label: str,
    fitter: Callable[[pd.Series, pd.DataFrame], Any],
    add_constant: bool = True,
) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])])
    entity_column = kwargs["entity_column"]
    time_column = kwargs["time_column"]
    sample = _panel_frame(frame, dependent=dependent, regressors=regressors, entity_column=entity_column, time_column=time_column)
    exog = sm.add_constant(sample[regressors], has_constant="add") if add_constant else sample[regressors].copy()
    fitted = fitter(sample[dependent], exog)
    fitted_values = getattr(fitted, "fitted_values", None)
    if isinstance(fitted_values, pd.DataFrame):
        fitted_series = fitted_values.iloc[:, 0]
    elif isinstance(fitted_values, pd.Series):
        fitted_series = fitted_values
    else:
        fitted_series = pd.Series(np.asarray(exog @ np.asarray(getattr(fitted, "params", np.zeros(exog.shape[1])))).reshape(-1), index=sample.index)
    residuals = sample[dependent] - fitted_series
    tables: dict[str, Any] = {
        "fit_summary_table": [
            {
                "metric": "nobs",
                "value": _safe_float(getattr(fitted, "nobs", len(sample))),
            },
            {
                "metric": "rsquared",
                "value": _safe_float(getattr(fitted, "rsquared", None)),
            },
            {
                "metric": "rsquared_within",
                "value": _safe_float(getattr(fitted, "rsquared_within", None)),
            },
            {
                "metric": "loglik",
                "value": _safe_float(getattr(fitted, "loglik", None)),
            },
        ],
        "sample_audit_table": [
            {
                "entities": int(sample.index.get_level_values(0).nunique()),
                "periods": int(sample.index.get_level_values(1).nunique()),
                "observations": int(len(sample)),
                "dependent_mean": _safe_float(sample[dependent].mean()),
                "dependent_std": _safe_float(sample[dependent].std(ddof=0)),
            }
        ],
    }
    variance_decomposition = getattr(fitted, "variance_decomposition", None)
    if isinstance(variance_decomposition, pd.Series):
        tables["variance_decomposition"] = _series_to_table(variance_decomposition, value_name="value")
    all_params = getattr(fitted, "all_params", None)
    if isinstance(all_params, pd.DataFrame):
        tables["period_parameter_summary"] = _serialize_rows(all_params.reset_index())
    figure, axis = _ts_figure(f"{model_label} Residual Diagnostic")
    axis.hist(residuals.dropna(), bins=24, color="#2457d6", alpha=0.85, edgecolor="white")
    axis.set_xlabel("Residual")
    axis.set_ylabel("Frequency")
    figure.tight_layout()
    diagnostic_figure = _candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=figure,
        filename_slug=f"{model_type}_residual_diagnostic",
        title=f"{model_label} residual diagnostic",
        summary="Histogram of model residuals for manual diagnostics.",
    )
    return _regression_payload(
        model_type=model_type,
        model_label=model_label,
        engine="linearmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample.reset_index(),
        result=fitted,
        narrative_lines=[
            f"{model_label} estimated with linearmodels on {asset.title}.",
            f"Dependent variable: {dependent}.",
            f"Observations used: {int(getattr(fitted, 'nobs', len(sample)))}.",
        ],
        tables=tables,
        figures=[diagnostic_figure],
        extra_specification={"entity_column": entity_column, "time_column": time_column},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing panel identifiers or regressors are dropped."]},
    )


def _candidate_fixed_effects_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]
    entity_column = kwargs["entity_column"]
    time_column = kwargs["time_column"]
    include_time_effects = bool(kwargs.get("include_time_effects", False))
    if not regressors:
        raise ValueError("Fixed effects estimation requires at least one regressor.")
    sample = _panel_frame(frame, dependent=dependent, regressors=regressors, entity_column=entity_column, time_column=time_column)
    fitted = PanelOLS(
        sample[dependent],
        sample[regressors],
        entity_effects=True,
        time_effects=include_time_effects,
        drop_absorbed=True,
        check_rank=False,
    ).fit(cov_type="robust")
    return _regression_payload(
        model_type="fixed_effects",
        model_label="Fixed Effects Panel Regression",
        engine="linearmodels",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample.reset_index(),
        result=fitted,
        narrative_lines=[
            f"Panel fixed-effects model estimated with linearmodels on {asset.title}.",
            f"Entity effects included for {entity_column}.",
            f"Time effects included: {'yes' if include_time_effects else 'no'}.",
        ],
        extra_specification={"entity_column": entity_column, "time_column": time_column, "include_time_effects": include_time_effects},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent, regressor, entity, or time values are dropped."]},
        metrics={"rsquared_within": _safe_float(getattr(fitted, "rsquared_within", None))},
    )


def _candidate_panel_iv_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    exogenous = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])])
    endogenous = kwargs["endogenous_column"]
    instruments = kwargs.get("instrument_columns") or []
    entity_column = kwargs["entity_column"]
    time_column = kwargs["time_column"]
    sample = _panel_frame(
        frame,
        dependent=dependent,
        regressors=exogenous + [endogenous, *instruments],
        entity_column=entity_column,
        time_column=time_column,
    )
    y = sample[dependent]
    exog = sm.add_constant(sample[exogenous], has_constant="add")
    fitted = LMIV2SLS(y, exog, sample[[endogenous]], sample[instruments]).fit(cov_type="robust")
    tables: dict[str, Any] = {}
    try:
        if hasattr(fitted, "first_stage") and hasattr(fitted.first_stage, "diagnostics"):
            tables["first_stage_diagnostics"] = _serialize_rows(fitted.first_stage.diagnostics.reset_index())
    except Exception:
        pass
    return _regression_payload(
        model_type="panel_iv",
        model_label="Panel IV (linearmodels)",
        engine="linearmodels",
        asset=asset,
        dependent=dependent,
        regressors=[*list(exog.columns), endogenous],
        sample=sample.reset_index(),
        result=fitted,
        narrative_lines=[
            f"Panel IV estimated with linearmodels on {asset.title}.",
            f"Endogenous regressor: {endogenous}.",
            f"Instruments: {', '.join(instruments)}.",
        ],
        tables=tables,
        extra_specification={"entity_column": entity_column, "time_column": time_column, "endogenous_column": endogenous, "instrument_columns": instruments},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent, exogenous, endogenous, or instrument values are dropped."]},
    )


def run_traded_factor_model_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    factor_columns = list(_spec_option(kwargs, "factor_columns", [kwargs.get("market_column") or "market_return", kwargs.get("smb_column") or "smb", kwargs.get("hml_column") or "hml"]))
    series_columns = list(_spec_option(kwargs, "series_columns", [kwargs.get("dependent") or "asset_return"]))
    sample = _timeseries_frame(frame, value_columns=[*series_columns, *factor_columns], time_column=kwargs.get("time_column", "date"))
    result = TradedFactorModel(sample[series_columns], sample[factor_columns]).fit()
    return _nonregression_payload(
        model_type="traded_factor_model",
        model_label="Traded Factor Model",
        engine="linearmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Traded factor model estimated with linearmodels asset pricing."],
        tables={
            "risk_premia_table": _series_to_table(result.risk_premia, value_name="risk_premium"),
            "alpha_table": _series_to_table(result.alphas, value_name="alpha"),
            "beta_table": _serialize_rows(result.betas.reset_index().rename(columns={"index": "portfolio"})),
            "tstat_table": _series_to_table(result.tstats, value_name="t_stat"),
        },
        figures=[],
        specification={"series_columns": series_columns, "factor_columns": factor_columns},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing factor or portfolio observations are dropped."]},
    )


def run_linear_factor_gmm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    factor_columns = list(_spec_option(kwargs, "factor_columns", [kwargs.get("market_column") or "market_return", kwargs.get("smb_column") or "smb", kwargs.get("hml_column") or "hml"]))
    series_columns = list(_spec_option(kwargs, "series_columns", [kwargs.get("dependent") or "asset_return"]))
    sample = _timeseries_frame(frame, value_columns=[*series_columns, *factor_columns], time_column=kwargs.get("time_column", "date"))
    result = LinearFactorModelGMM(sample[series_columns], sample[factor_columns]).fit()
    j_stat = getattr(result, "j_statistic", None)
    return _nonregression_payload(
        model_type="linear_factor_gmm",
        model_label="Linear Factor Model GMM",
        engine="linearmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["GMM-based linear factor model estimated with linearmodels asset pricing."],
        tables={
            "risk_premia_table": _series_to_table(result.risk_premia, value_name="risk_premium"),
            "alpha_table": _series_to_table(result.alphas, value_name="alpha"),
            "beta_table": _serialize_rows(result.betas.reset_index().rename(columns={"index": "portfolio"})),
            "j_stat_table": [{"stat": _safe_float(getattr(j_stat, "stat", None)), "pvalue": _safe_float(getattr(j_stat, "pval", None))}],
        },
        figures=[],
        specification={"series_columns": series_columns, "factor_columns": factor_columns},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing factor or portfolio observations are dropped."]},
    )


def _spec_option(kwargs: dict[str, Any], key: str, default: Any = None) -> Any:
    specification = kwargs.get("effective_specification") or {}
    if isinstance(specification, dict) and key in specification:
        value = specification[key]
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        return value
    variant = kwargs.get("variant_spec") or {}
    if isinstance(variant, dict) and key in variant:
        value = variant[key]
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        return value
    value = kwargs.get(key, default)
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


def _flat_frame(
    frame: pd.DataFrame,
    *,
    numeric_columns: list[str],
    keep_columns: list[str] | None = None,
) -> pd.DataFrame:
    keep_columns = _clean_columns(keep_columns)
    numeric_columns = _clean_columns(numeric_columns)
    required = [*keep_columns, *numeric_columns]
    _ensure_columns(frame, required)
    sample = frame[required].copy()
    for column in numeric_columns:
        sample[column] = _pc()._coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if len(sample) < 12:
        raise ValueError("Not enough complete observations for estimation.")
    return sample


def _series_to_table(series: Any, *, value_name: str = "value") -> list[dict[str, Any]]:
    if series is None:
        return []
    if hasattr(series, "reset_index"):
        try:
            frame = series.reset_index()
            if len(frame.columns) == 2:
                frame.columns = ["term", value_name]
            return _serialize_rows(frame)
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    try:
        iterator = series.items()
    except Exception:
        iterator = []
    for key, value in iterator:
        rows.append({"term": str(key), value_name: _safe_float(value)})
    return rows


def _equation_table(params: Any, *, prefix: str = "equation") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if params is None:
        return rows
    if isinstance(params, pd.Series) and isinstance(params.index, pd.MultiIndex):
        for (equation, term), value in params.items():
            rows.append({"equation": str(equation), "term": str(term), "coefficient": _safe_float(value)})
        return rows
    if isinstance(params, pd.DataFrame):
        for equation in params.columns:
            for term, value in params[equation].items():
                rows.append({"equation": str(equation), "term": str(term), "coefficient": _safe_float(value)})
        return rows
    rows = _series_to_table(params, value_name="coefficient")
    for row in rows:
        term = str(row.get("term", ""))
        equation = prefix
        if "." in term:
            equation, term = term.split(".", 1)
        elif "_" in term:
            maybe_equation, maybe_term = term.split("_", 1)
            if maybe_equation.startswith("eq"):
                equation, term = maybe_equation, maybe_term
        row["equation"] = equation
        row["term"] = term
    return rows


def _as_series(values: Any, index: pd.Index | None = None, name: str = "value") -> pd.Series:
    if isinstance(values, pd.DataFrame):
        if values.shape[1] == 0:
            return pd.Series(dtype=float, name=name)
        series = values.iloc[:, 0]
    elif isinstance(values, pd.Series):
        series = values
    else:
        array = np.asarray(values).reshape(-1)
        series = pd.Series(array)
    if index is not None and len(series) == len(index):
        series = pd.Series(series.to_numpy(), index=index, name=name)
    if series.name is None:
        series.name = name
    return pd.to_numeric(series, errors="coerce")


def _fitted_actual_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    actual: Any,
    fitted: Any,
    filename_slug: str,
    title: str,
    summary: str,
    xlabel: str = "Actual",
    ylabel: str = "Fitted",
) -> dict[str, Any]:
    actual_series = _as_series(actual, name="actual")
    fitted_series = _as_series(fitted, index=actual_series.index, name="fitted")
    diagnostic = pd.concat([actual_series.rename("actual"), fitted_series.rename("fitted")], axis=1).dropna()
    figure, axis = _ts_figure(title)
    axis.scatter(diagnostic["actual"], diagnostic["fitted"], alpha=0.75, color="#2457d6", edgecolors="white", linewidths=0.5)
    if not diagnostic.empty:
        line_min = float(min(diagnostic["actual"].min(), diagnostic["fitted"].min()))
        line_max = float(max(diagnostic["actual"].max(), diagnostic["fitted"].max()))
        axis.plot([line_min, line_max], [line_min, line_max], color="#111111", linestyle="--", linewidth=1.0)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    figure.tight_layout()
    return _candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def _count_fit_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    actual: Any,
    fitted: Any,
    filename_slug: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    actual_series = _as_series(actual, name="actual")
    fitted_series = _as_series(fitted, index=actual_series.index, name="fitted")
    diagnostic = pd.concat([actual_series.rename("actual"), fitted_series.rename("fitted")], axis=1).dropna()
    figure, axis = _ts_figure(title)
    axis.scatter(diagnostic["actual"], diagnostic["fitted"], alpha=0.7, color="#c95f35", edgecolors="white", linewidths=0.5)
    axis.set_xlabel("Observed count")
    axis.set_ylabel("Fitted count")
    figure.tight_layout()
    return _candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def _residual_correlation_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    residuals: pd.DataFrame,
    filename_slug: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    corr = residuals.corr()
    figure, axis = _ts_figure(title)
    matrix = corr.to_numpy(dtype=float)
    image = axis.imshow(matrix, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
    axis.set_xticks(range(len(corr.columns)))
    axis.set_yticks(range(len(corr.index)))
    axis.set_xticklabels([str(col) for col in corr.columns], rotation=30, ha="right")
    axis.set_yticklabels([str(idx) for idx in corr.index])
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(column, row, f"{matrix[row, column]:.2f}", ha="center", va="center", color="#111111", fontsize=8)
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    return _candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def _multi_series_line_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    frame: pd.DataFrame,
    filename_slug: str,
    title: str,
    summary: str,
    xlabel: str = "Observation",
    ylabel: str = "Value",
) -> dict[str, Any]:
    figure, axis = _ts_figure(title)
    clean = frame.dropna(how="all")
    clean.plot(ax=axis)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    figure.tight_layout()
    return _candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def run_random_effects_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_basic_panel_model(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="random_effects",
        model_label="Random Effects",
        fitter=lambda y, exog: RandomEffects(y, exog).fit(cov_type="robust"),
    )


def run_first_difference_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_basic_panel_model(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="first_difference",
        model_label="First-Difference Panel Regression",
        fitter=lambda y, exog: FirstDifferenceOLS(y, exog).fit(cov_type="robust"),
        add_constant=False,
    )


def run_between_ols_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_basic_panel_model(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="between_ols",
        model_label="Between Estimator",
        fitter=lambda y, exog: BetweenOLS(y, exog).fit(cov_type="robust"),
    )


def run_pooled_ols_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_basic_panel_model(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="pooled_ols",
        model_label="Pooled OLS",
        fitter=lambda y, exog: PooledOLS(y, exog).fit(cov_type="robust"),
    )


def run_fama_macbeth_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_basic_panel_model(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="fama_macbeth",
        model_label="Fama-MacBeth",
        fitter=lambda y, exog: FamaMacBeth(y, exog).fit(cov_type="robust"),
    )


def _run_iv_family(
    constructor: Callable[..., Any],
    *,
    model_type: str,
    model_label: str,
    settings: Any,
    db: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    exogenous = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]
    endogenous = kwargs["endogenous_column"]
    instruments = kwargs.get("instrument_columns") or []
    sample = _flat_frame(frame, numeric_columns=[dependent, *exogenous, endogenous, *instruments])
    y = sample[dependent]
    exog = sm.add_constant(sample[exogenous], has_constant="add")
    fitted = constructor(y, exog, sample[[endogenous]], sample[instruments]).fit(cov_type="robust")
    tables: dict[str, Any] = {}
    robustness_tables: dict[str, Any] = {}
    try:
        if hasattr(fitted, "first_stage") and hasattr(fitted.first_stage, "diagnostics"):
            tables["first_stage_diagnostics"] = _serialize_rows(fitted.first_stage.diagnostics.reset_index())
    except Exception:
        pass
    if model_type == "iv_liml":
        tables.setdefault("weak_instrument_diagnostics", []).append(
            {
                "kappa": _safe_float(getattr(fitted, "kappa", None)),
                "nobs": _safe_float(getattr(fitted, "nobs", None)),
                "rsquared": _safe_float(getattr(fitted, "rsquared", None)),
            }
        )
        try:
            comparison = LMIV2SLS(y, exog, sample[[endogenous]], sample[instruments]).fit(cov_type="robust")
            robustness_tables["liml_vs_2sls"] = _serialize_rows(
                pd.DataFrame(
                    {
                        "term": list(fitted.params.index),
                        "liml": np.asarray(fitted.params),
                        "iv_2sls": np.asarray(comparison.params.reindex(fitted.params.index)),
                    }
                )
            )
        except Exception:
            pass
    if model_type == "iv_gmm":
        j_stat = getattr(fitted, "j_stat", None)
        tables["over_identification_diagnostics"] = [
            {
                "j_stat": _safe_float(getattr(j_stat, "stat", None) if j_stat is not None else None),
                "pvalue": _safe_float(getattr(j_stat, "pval", None) if j_stat is not None else None),
                "nobs": _safe_float(getattr(fitted, "nobs", None)),
            }
        ]
        robustness_tables["weighting_matrix_summary"] = [
            {
                "weight_type": str(getattr(fitted, "weight_type", "robust")),
                "cov_type": str(getattr(fitted, "cov_type", "robust")),
                "iterations": _safe_float(getattr(fitted, "iterations", None)),
            }
        ]
    first_stage_model = sm.OLS(sample[endogenous], pd.concat([exog, sample[instruments]], axis=1)).fit()
    first_stage_figure = _fitted_actual_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        actual=sample[endogenous],
        fitted=first_stage_model.fittedvalues,
        filename_slug=f"{model_type}_first_stage_fit",
        title=f"{model_label} First-stage Fit",
        summary="Observed endogenous regressor versus first-stage fitted values.",
        xlabel=f"Observed {endogenous}",
        ylabel="First-stage fitted",
    )
    return _regression_payload(
        model_type=model_type,
        model_label=model_label,
        engine="linearmodels",
        asset=asset,
        dependent=dependent,
        regressors=[*list(exog.columns), endogenous],
        sample=sample,
        result=fitted,
        narrative_lines=[
            f"{model_label} estimated with linearmodels on {asset.title}.",
            f"Endogenous regressor: {endogenous}.",
            f"Instruments: {', '.join(instruments)}.",
        ],
        tables=tables,
        figures=[first_stage_figure],
        robustness_tables=robustness_tables,
        extra_specification={"endogenous_column": endogenous, "instrument_columns": instruments},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing variables are dropped."]},
    )


def run_iv_liml_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_iv_family(IVLIML, model_type="iv_liml", model_label="IV-LIML", settings=settings, db=db, **kwargs)


def run_iv_gmm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_iv_family(IVGMM, model_type="iv_gmm", model_label="IV-GMM", settings=settings, db=db, **kwargs)


def run_absorbing_ls_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])])
    absorb_columns = [column for column in [_spec_option(kwargs, "entity_column", kwargs.get("entity_column", "")), _spec_option(kwargs, "time_column", kwargs.get("time_column", ""))] if column]
    sample = frame[[dependent, *regressors, *absorb_columns]].copy()
    for column in [dependent, *regressors]:
        sample[column] = _pc()._coerce_numeric_series(sample[column])
    for column in absorb_columns:
        sample[column] = sample[column].astype("category")
    sample = sample.dropna().copy()
    absorb = sample[absorb_columns] if absorb_columns else None
    fitted = AbsorbingLS(sample[dependent], sample[regressors], absorb=absorb, drop_absorbed=True).fit(cov_type="robust")
    tables = {
        "absorbed_effects_audit": [
            {
                "absorbed_dimension": column,
                "levels": int(sample[column].astype(str).nunique()),
            }
            for column in absorb_columns
        ]
    }
    figure = _fitted_actual_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        actual=sample[dependent],
        fitted=getattr(fitted, "fitted_values", None),
        filename_slug="absorbing_ls_residual_by_group",
        title="Absorbing LS Residual by Group",
        summary="Observed dependent variable against absorbed-model fitted values.",
        xlabel=f"Observed {dependent}",
        ylabel="Absorbing-LS fitted",
    )
    return _regression_payload(
        model_type="absorbing_ls",
        model_label="Absorbing Least Squares",
        engine="linearmodels",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=[
            f"Absorbing least squares estimated with linearmodels on {asset.title}.",
            f"Absorbed effects: {', '.join(absorb_columns) if absorb_columns else 'none'}.",
        ],
        tables=tables,
        figures=[figure],
        extra_specification={"absorb_columns": absorb_columns},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent, regressors, or absorbed effects are dropped."]},
    )


def _system_equation_formulas(dependent: str, secondary: str, endogenous: str, instruments: list[str]) -> dict[str, str]:
    if secondary:
        if endogenous and instruments:
            return {
                "eq_primary": f"{dependent} ~ 1 + size + leverage + [ {endogenous} ~ {' + '.join(instruments)} ]",
                "eq_secondary": f"{secondary} ~ 1 + size + leverage + post",
            }
        return {
            "eq_primary": f"{dependent} ~ 1 + size + leverage + post",
            "eq_secondary": f"{secondary} ~ 1 + size + leverage + treated",
        }
    return {"eq_primary": f"{dependent} ~ 1 + size + leverage + post"}


def _system_payload(
    *,
    settings: Any,
    db: Any,
    user: Any,
    workspace: Any,
    fitted: Any,
    asset: Any,
    sample: pd.DataFrame,
    model_type: str,
    model_label: str,
    specification: dict[str, Any],
) -> dict[str, Any]:
    params = getattr(fitted, "params", None)
    summary_table = _equation_table(params)
    residuals = getattr(fitted, "resids", None)
    if isinstance(residuals, pd.Series):
        residual_frame = residuals.to_frame(name="eq_primary")
    elif isinstance(residuals, pd.DataFrame):
        residual_frame = residuals.copy()
    else:
        residual_frame = pd.DataFrame()
    tables = {
        "system_coefficients": summary_table,
        "equation_residual_summary": [
            {
                "equation": str(column),
                "mean": _safe_float(residual_frame[column].mean()),
                "std": _safe_float(residual_frame[column].std(ddof=0)),
                "rmse": _safe_float(np.sqrt(np.mean(np.square(residual_frame[column].dropna())))) if residual_frame[column].dropna().size else None,
            }
            for column in residual_frame.columns
        ],
    }
    figures: list[dict[str, Any]] = []
    if not residual_frame.empty and model_type == "sur":
        figures.append(
            _residual_correlation_figure(
                settings,
                db,
                user=user,
                workspace=workspace,
                source_asset=asset,
                residuals=residual_frame,
                filename_slug="sur_residual_correlation",
                title="System Residual Correlation Heatmap",
                summary="Residual correlation across system equations.",
            )
        )
    elif not residual_frame.empty:
        figures.append(
            _multi_series_line_figure(
                settings,
                db,
                user=user,
                workspace=workspace,
                source_asset=asset,
                frame=residual_frame.reset_index(drop=True),
                filename_slug=f"{model_type}_diagnostic",
                title="System Equation Diagnostic",
                summary="Equation-level residual or dynamic fit diagnostics across the estimated system.",
                ylabel="Residual / fit",
            )
        )
    metrics: dict[str, Any] = {}
    for attr in ["j_stat", "sigma", "method", "iterations"]:
        value = getattr(fitted, attr, None)
        if value is not None and not callable(value):
            metrics[attr] = str(value)
    return _nonregression_payload(
        model_type=model_type,
        model_label=model_label,
        engine="linearmodels",
        asset=asset,
        sample=sample,
        narrative_lines=[
            f"{model_label} estimated with linearmodels system estimators.",
            f"Equations estimated: {', '.join(sorted({str(row.get('equation', 'eq_primary')) for row in summary_table})) if summary_table else '1'}.",
        ],
        tables=tables,
        figures=figures,
        specification=specification,
        audit_trail={"derived_columns": [], "filters": ["Rows with missing variables used by any equation are dropped."]},
        metrics=metrics,
    )


def run_sur_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    secondary = _spec_option(kwargs, "secondary_dependent", "secondary_outcome")
    sample = _flat_frame(frame, numeric_columns=[dependent, secondary, "size", "leverage", "post", "treated"])
    formulas = _system_equation_formulas(dependent, secondary, "", [])
    fitted = SUR.from_formula(formulas, data=sample).fit()
    return _system_payload(
        settings=settings,
        db=db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        fitted=fitted,
        asset=asset,
        sample=sample,
        model_type="sur",
        model_label="Seemingly Unrelated Regressions",
        specification={"secondary_dependent": secondary},
    )


def run_iv_3sls_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    secondary = _spec_option(kwargs, "secondary_dependent", "secondary_outcome")
    endogenous = kwargs["endogenous_column"]
    instruments = kwargs.get("instrument_columns") or []
    sample = _flat_frame(frame, numeric_columns=[dependent, secondary, "size", "leverage", "post", "treated", endogenous, *instruments])
    formulas = _system_equation_formulas(dependent, secondary, endogenous, instruments)
    fitted = IV3SLS.from_formula(formulas, data=sample).fit(cov_type="robust")
    return _system_payload(
        settings=settings,
        db=db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        fitted=fitted,
        asset=asset,
        sample=sample,
        model_type="iv_3sls",
        model_label="IV-3SLS",
        specification={"secondary_dependent": secondary, "endogenous_column": endogenous, "instrument_columns": instruments},
    )


def run_system_gmm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    secondary = _spec_option(kwargs, "secondary_dependent", "secondary_outcome")
    endogenous = kwargs["endogenous_column"]
    instruments = kwargs.get("instrument_columns") or []
    sample = _flat_frame(frame, numeric_columns=[dependent, secondary, "size", "leverage", "post", "treated", endogenous, *instruments])
    formulas = _system_equation_formulas(dependent, secondary, endogenous, instruments)
    fitted = IVSystemGMM.from_formula(formulas, data=sample).fit()
    return _system_payload(
        settings=settings,
        db=db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        fitted=fitted,
        asset=asset,
        sample=sample,
        model_type="system_gmm",
        model_label="System GMM",
        specification={"secondary_dependent": secondary, "endogenous_column": endogenous, "instrument_columns": instruments},
    )


def run_glm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or _spec_option(kwargs, "dependent", "count_outcome")
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]) or ["size", "leverage", "post"]
    family_name = str(_spec_option(kwargs, "glm_family", "poisson")).lower()
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors])
    exog = sm.add_constant(sample[regressors], has_constant="add")
    family = {"gaussian": Gaussian(), "poisson": Poisson(), "negative_binomial": NegativeBinomial()}.get(family_name, Poisson())
    fitted = sm.GLM(sample[dependent], exog, family=family).fit()
    robustness_rows: list[dict[str, Any]] = []
    for alt_name, alt_family in [("gaussian", Gaussian()), ("poisson", Poisson()), ("negative_binomial", NegativeBinomial())]:
        if alt_name == family_name:
            continue
        try:
            alt = sm.GLM(sample[dependent], exog, family=alt_family).fit()
            robustness_rows.append({"family": alt_name, "aic": _safe_float(getattr(alt, "aic", None)), "deviance": _safe_float(getattr(alt, "deviance", None))})
        except Exception:
            pass
    figure = _fitted_actual_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        actual=sample[dependent],
        fitted=fitted.fittedvalues,
        filename_slug="glm_fitted_vs_actual",
        title="GLM Fitted vs Actual",
        summary="Observed dependent variable versus fitted GLM values.",
        xlabel=f"Observed {dependent}",
        ylabel="GLM fitted",
    )
    return _regression_payload(
        model_type="glm",
        model_label="Generalized Linear Model",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=fitted,
        narrative_lines=[
            f"GLM estimated with statsmodels on {asset.title}.",
            f"Family: {family_name}.",
        ],
        tables={"family_link_audit": [{"family": family_name, "link": family.link.__class__.__name__}]},
        figures=[figure],
        robustness_tables={"alternative_family_table": robustness_rows},
        extra_specification={"glm_family": family_name},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped."]},
    )


def run_quantile_regression_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]) or ["size", "leverage", "post"]
    quantile = float(_spec_option(kwargs, "quantile", 0.5))
    alt_quantiles = [0.25, 0.5, 0.75]
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors])
    exog = sm.add_constant(sample[regressors], has_constant="add")
    fitted = sm.QuantReg(sample[dependent], exog).fit(q=quantile)
    robustness_rows: list[dict[str, Any]] = []
    for q in alt_quantiles:
        try:
            alt = sm.QuantReg(sample[dependent], exog).fit(q=q)
            for row in _series_to_table(alt.params, value_name="coefficient"):
                row["quantile"] = q
                robustness_rows.append(row)
        except Exception:
            pass
    coefficient_frame = pd.DataFrame(robustness_rows)
    if coefficient_frame.empty:
        coefficient_frame = pd.DataFrame(_series_to_table(fitted.params, value_name="coefficient"))
        coefficient_frame["quantile"] = quantile
    coefficient_path = coefficient_frame.pivot_table(index="quantile", columns="term", values="coefficient", aggfunc="first").sort_index()
    figure = _multi_series_line_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=coefficient_path,
        filename_slug="quantile_regression_path",
        title="Coefficient Path by Quantile",
        summary="Coefficient path across estimated quantiles.",
        xlabel="Quantile",
        ylabel="Coefficient",
    )
    return _regression_payload(
        model_type="quantile_regression",
        model_label="Quantile Regression",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=fitted,
        narrative_lines=[
            f"Quantile regression estimated at tau={quantile:.2f}.",
            f"Asset: {asset.title}.",
        ],
        figures=[figure],
        robustness_tables={"alternative_quantiles": robustness_rows},
        extra_specification={"quantile": quantile},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped."]},
    )


def run_gee_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "outcome_y"
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]) or ["size", "leverage", "post"]
    group_column = str(_spec_option(kwargs, "gee_group_column", kwargs.get("entity_column") or "firm_id") or kwargs.get("entity_column") or "firm_id").strip()
    family_name = str(_spec_option(kwargs, "gee_family", "gaussian")).lower()
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors], keep_columns=[group_column])
    exog = sm.add_constant(sample[regressors], has_constant="add")
    family = {"gaussian": Gaussian(), "poisson": Poisson(), "negative_binomial": NegativeBinomial()}.get(family_name, Gaussian())
    fitted = GEE(sample[dependent], exog, groups=sample[group_column].astype(str), family=family).fit()
    residuals = pd.Series(sample[dependent] - np.asarray(fitted.fittedvalues).reshape(-1), index=sample.index)
    grouped = (
        pd.DataFrame({group_column: sample[group_column].astype(str), "residual": residuals})
        .groupby(group_column)["residual"]
        .agg(["mean", "std"])
        .head(20)
    )
    figure = _multi_series_line_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=grouped,
        filename_slug="gee_cluster_diagnostic",
        title="Cluster Diagnostic Plot",
        summary="Mean and standard deviation of residuals by cluster.",
        xlabel="Cluster index",
        ylabel="Residual diagnostic",
    )
    return _regression_payload(
        model_type="gee",
        model_label="Generalized Estimating Equations",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=fitted,
        narrative_lines=[
            f"GEE estimated with groups defined by {group_column}.",
            f"Family: {family_name}.",
        ],
        tables={"group_audit": _serialize_rows(sample.groupby(group_column).size().reset_index(name="n"))},
        figures=[figure],
        extra_specification={"gee_group_column": group_column, "gee_family": family_name},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent, regressors, or group ids are dropped."]},
    )


def run_mnlogit_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "multiclass_outcome"
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]) or ["size", "leverage", "post"]
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors])
    observed_classes = sorted(sample[dependent].astype(int).unique().tolist())
    sample = sample.copy()
    sample[dependent] = sample[dependent].astype(int)
    x = sample[regressors]
    y = sample[dependent]
    formula = f"{dependent} ~ " + " + ".join(regressors)
    engine_name = "statsmodels"
    metric_payload: dict[str, Any] = {}
    try:
        fitted = smf.mnlogit(formula, data=sample).fit(disp=False)
        coef_rows = _equation_table(fitted.params)
        predicted = np.asarray(fitted.predict(sample))
        if predicted.ndim == 1:
            if predicted.shape[0] == len(sample) and len(observed_classes) == 2 and np.all((predicted >= 0.0) & (predicted <= 1.0)):
                predicted = np.column_stack([1.0 - predicted, predicted])
            elif predicted.shape[0] == len(sample):
                label_frame = pd.get_dummies(pd.Series(predicted).round().astype(int), prefix="class")
                for class_id in observed_classes:
                    column_name = f"class_{class_id}"
                    if column_name not in label_frame.columns:
                        label_frame[column_name] = 0.0
                predicted = label_frame[[f"class_{class_id}" for class_id in observed_classes]].to_numpy(dtype=float)
            else:
                predicted = predicted.reshape(1, -1)
        elif predicted.ndim == 2 and predicted.shape[1] == 1 and len(observed_classes) == 2:
            predicted = np.column_stack([1.0 - predicted[:, 0], predicted[:, 0]])
        if predicted.ndim != 2:
            raise ValueError("MNLogit predicted probability output could not be normalized to a 2D matrix.")
        if predicted.shape[1] != len(observed_classes):
            if predicted.shape[1] < len(observed_classes):
                padding = np.zeros((predicted.shape[0], len(observed_classes) - predicted.shape[1]))
                predicted = np.hstack([predicted, padding])
            else:
                predicted = predicted[:, : len(observed_classes)]
        metric_payload = {"llf": _safe_float(getattr(fitted, "llf", None)), "aic": _safe_float(getattr(fitted, "aic", None))}
    except Exception:
        fallback = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=42)
        fallback.fit(x, y)
        predicted = fallback.predict_proba(x)
        coefficient_rows: list[dict[str, Any]] = []
        intercepts = np.asarray(fallback.intercept_).reshape(-1)
        coefficients = np.asarray(fallback.coef_)
        for class_index, class_id in enumerate(fallback.classes_.tolist()):
            coefficient_rows.append({"equation": f"class_{class_id}", "term": "Intercept", "coefficient": float(intercepts[class_index])})
            for regressor, coefficient in zip(regressors, coefficients[class_index], strict=False):
                coefficient_rows.append({"equation": f"class_{class_id}", "term": regressor, "coefficient": float(coefficient)})
        coef_rows = coefficient_rows
        observed_classes = [int(class_id) for class_id in fallback.classes_.tolist()]
        engine_name = "sklearn"
        metric_payload = {"training_accuracy": float((fallback.predict(x) == y).mean())}
    probability_columns = [f"class_{class_id}" for class_id in observed_classes]
    class_probabilities = pd.DataFrame(
        predicted,
        columns=probability_columns,
    ).mean(axis=0).to_frame(name="mean_probability")
    figure = _multi_series_line_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=class_probabilities.T,
        filename_slug="mnlogit_class_distribution",
        title="Predicted Class Distribution",
        summary="Average predicted class probabilities across the estimation sample.",
        xlabel="Class",
        ylabel="Mean predicted probability",
    )
    return _nonregression_payload(
        model_type="mnlogit",
        model_label="Multinomial Logit",
        engine=engine_name,
        asset=asset,
        sample=sample,
        narrative_lines=[
            f"Multinomial logit estimated on {asset.title}.",
            f"Estimation engine: {engine_name}.",
            f"Outcome classes: {observed_classes}.",
        ],
        tables={
            "coefficient_table": coef_rows,
            "class_audit": [{"class": int(label), "count": int(count)} for label, count in sample[dependent].astype(int).value_counts().sort_index().items()],
            "class_probability_table": _serialize_rows(class_probabilities.reset_index().rename(columns={"index": "class"})),
        },
        figures=[figure],
        specification={"dependent": dependent, "regressors": regressors, "formula": formula},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped."]},
        metrics=metric_payload,
    )


def run_negative_binomial_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "count_outcome"
    regressors = _clean_columns([*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]) or ["size", "leverage", "post"]
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors])
    exog = sm.add_constant(sample[regressors], has_constant="add")
    fitted = sm.NegativeBinomial(sample[dependent], exog).fit(disp=False)
    figure = _count_fit_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        actual=sample[dependent],
        fitted=fitted.predict(exog),
        filename_slug="negative_binomial_fit",
        title="Predicted vs Observed Count",
        summary="Observed versus fitted counts for the negative-binomial model.",
    )
    return _regression_payload(
        model_type="negative_binomial",
        model_label="Negative Binomial",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=fitted,
        narrative_lines=["Negative binomial count model estimated with statsmodels."],
        tables={"dispersion_audit": [{"alpha": _safe_float(getattr(fitted, "lnalpha", None)), "aic": _safe_float(getattr(fitted, "aic", None))}]},
        figures=[figure],
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped."]},
    )


def run_zero_inflated_count_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "count_outcome"
    regressors = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])] or ["size", "leverage", "post"]
    inflation_regressors = _clean_columns(list(_spec_option(kwargs, "inflation_regressors", ["size", "post"])))
    family = str(_spec_option(kwargs, "count_family", "poisson")).lower()
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors, *inflation_regressors])
    exog = sm.add_constant(sample[regressors], has_constant="add")
    exog_infl = sm.add_constant(sample[inflation_regressors], has_constant="add")
    if family in {"negative_binomial", "zinb"}:
        fitted = ZeroInflatedNegativeBinomialP(sample[dependent], exog, exog_infl=exog_infl).fit(disp=False)
        label = "Zero-Inflated Negative Binomial"
    else:
        fitted = ZeroInflatedPoisson(sample[dependent], exog, exog_infl=exog_infl).fit(disp=False)
        label = "Zero-Inflated Poisson"
    figure = _count_fit_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        actual=sample[dependent],
        fitted=fitted.predict(exog=exog, exog_infl=exog_infl),
        filename_slug="zero_inflated_count_fit",
        title="Observed vs Fitted Count",
        summary="Observed counts versus fitted counts for the zero-inflated model.",
    )
    return _regression_payload(
        model_type="zero_inflated_count",
        model_label=label,
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=fitted,
        narrative_lines=[f"{label} estimated with separate inflation equation."],
        tables={"inflation_equation_audit": [{"count_family": family, "inflation_regressors": ", ".join(inflation_regressors)}]},
        figures=[figure],
        extra_specification={"count_family": family, "inflation_regressors": inflation_regressors},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing variables are dropped."]},
    )


def _ts_figure(title: str) -> tuple[Any, Any]:
    figure, axis = plt.subplots(figsize=(10, 5), dpi=160)
    figure.patch.set_facecolor("#fffdf8")
    axis.set_facecolor("#fffdf8")
    axis.set_title(title)
    return figure, axis


def run_varmax_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    sample = _timeseries_frame(frame, value_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    order = tuple(_spec_option(kwargs, "varmax_order", (1, 1)))
    fitted = VARMAX(sample, order=order, trend="c").fit(disp=False, maxiter=200)
    forecast_steps = int(kwargs.get("forecast_steps", 5))
    forecast = fitted.forecast(steps=forecast_steps)
    figure, axis = _ts_figure("VARMAX Forecast Paths")
    sample.iloc[-40:].plot(ax=axis, alpha=0.5)
    forecast.plot(ax=axis, style="--")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="varmax_forecast", title="VARMAX forecast paths", summary="Forecast trajectories from the fitted VARMAX model.")
    return _nonregression_payload(
        model_type="varmax",
        model_label="VARMAX",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"VARMAX{order} estimated with statsmodels.", f"Forecast horizon: {forecast_steps}."],
        tables={"system_table": _equation_table(getattr(fitted, "params", None)), "forecast_summary": _serialize_rows(forecast.reset_index())},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "varmax_order": list(order), "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
        metrics={"aic": _safe_float(getattr(fitted, "aic", None)), "bic": _safe_float(getattr(fitted, "bic", None))},
    )


def run_vecm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    series_columns = kwargs.get("series_columns") or ["level_a", "level_b"]
    sample = _timeseries_frame(frame, value_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    coint_rank = int(_spec_option(kwargs, "coint_rank", 1))
    k_ar_diff = int(_spec_option(kwargs, "vecm_diff_lags", 1))
    fitted = VECM(sample, coint_rank=coint_rank, k_ar_diff=k_ar_diff, deterministic="co").fit()
    forecast_steps = int(kwargs.get("forecast_steps", 5))
    forecast = fitted.predict(steps=forecast_steps)
    forecast_frame = _forecast_frame_with_time_index(forecast, columns=series_columns, source_index=sample.index)
    figure, axis = _ts_figure("VECM Forecast Paths")
    sample.iloc[-40:].plot(ax=axis, alpha=0.5)
    forecast_frame.plot(ax=axis, style="--")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="vecm_forecast", title="VECM forecast paths", summary="Forecast trajectories from the fitted VECM.")
    alpha_table = _serialize_rows(pd.DataFrame(fitted.alpha, index=series_columns).reset_index().rename(columns={"index": "series"}))
    beta_table = _serialize_rows(pd.DataFrame(fitted.beta, index=series_columns).reset_index().rename(columns={"index": "series"}))
    sample_table = sample.reset_index().rename(columns={sample.index.name or "index": "date"})
    forecast_table = forecast_frame.reset_index().rename(columns={forecast_frame.index.name or "index": "forecast_date"})
    return _nonregression_payload(
        model_type="vecm",
        model_label="Vector Error Correction Model",
        engine="statsmodels",
        asset=asset,
        sample=sample_table,
        narrative_lines=[f"VECM estimated with coint_rank={coint_rank} and k_ar_diff={k_ar_diff}."],
        tables={"alpha_adjustment": alpha_table, "beta_cointegration": beta_table, "forecast_summary": _serialize_rows(forecast_table)},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "coint_rank": coint_rank, "vecm_diff_lags": k_ar_diff, "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
    )


def run_markov_switching_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "asset_return"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    regimes = int(_spec_option(kwargs, "markov_regimes", 2))
    fitted = MarkovRegression(sample[dependent], k_regimes=regimes, trend="c", switching_variance=True).fit(disp=False)
    smoothed = pd.DataFrame({f"regime_{idx}_prob": fitted.smoothed_marginal_probabilities[idx] for idx in range(regimes)})
    figure, axis = _ts_figure("Markov Regime Probabilities")
    smoothed.plot(ax=axis)
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="markov_regime_probabilities", title="Markov regime probabilities", summary="Smoothed marginal regime probabilities from the Markov-switching model.")
    return _nonregression_payload(
        model_type="markov_switching",
        model_label="Markov Switching",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"Markov-switching model estimated with {regimes} regimes."],
        tables={"parameter_table": _series_to_table(fitted.params, value_name="coefficient"), "smoothed_probabilities": _serialize_rows(smoothed.reset_index())},
        figures=[fig_asset],
        specification={"dependent": dependent, "markov_regimes": regimes},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
        metrics={"llf": _safe_float(getattr(fitted, "llf", None)), "aic": _safe_float(getattr(fitted, "aic", None))},
    )


def run_unobserved_components_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "policy_rate"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    season = int(_spec_option(kwargs, "seasonal_periods", 12))
    fitted = UnobservedComponents(sample[dependent], level="local level", seasonal=season).fit(disp=False)
    figure, axis = _ts_figure("Unobserved Components Trend")
    sample[dependent].plot(ax=axis, alpha=0.4, label="observed")
    pd.Series(fitted.level.smoothed, index=sample.index).plot(ax=axis, label="smoothed_level")
    axis.legend()
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="unobserved_components_level", title="Unobserved-components smoothed level", summary="Observed series and smoothed level from the unobserved-components model.")
    return _nonregression_payload(
        model_type="unobserved_components",
        model_label="Unobserved Components",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"Local-level unobserved-components model with seasonal={season}."],
        tables={"parameter_table": _series_to_table(fitted.params, value_name="coefficient")},
        figures=[fig_asset],
        specification={"dependent": dependent, "seasonal_periods": season},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
    )


def run_exponential_smoothing_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "policy_rate"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    seasonal = _spec_option(kwargs, "seasonal", None)
    seasonal_periods = int(_spec_option(kwargs, "seasonal_periods", 12))
    fitted = ExponentialSmoothing(sample[dependent], trend="add", seasonal=seasonal, seasonal_periods=seasonal_periods if seasonal else None).fit()
    forecast_steps = int(kwargs.get("forecast_steps", 5))
    forecast = fitted.forecast(forecast_steps)
    figure, axis = _ts_figure("Exponential Smoothing Forecast")
    sample[dependent].iloc[-40:].plot(ax=axis, label="history")
    forecast.plot(ax=axis, style="--", label="forecast")
    axis.legend()
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="exp_smoothing_forecast", title="Exponential smoothing forecast", summary="Forecast path from the fitted exponential smoothing model.")
    return _nonregression_payload(
        model_type="exponential_smoothing",
        model_label="Exponential Smoothing",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"Exponential smoothing estimated with seasonal={seasonal or 'none'}."],
        tables={"parameter_table": _series_to_table(fitted.params, value_name="coefficient"), "forecast_summary": _serialize_rows(forecast.reset_index(name="forecast"))},
        figures=[fig_asset],
        specification={"dependent": dependent, "seasonal": seasonal or "", "seasonal_periods": seasonal_periods, "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
    )


def run_mixedlm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    regressors = _clean_columns(list(kwargs.get("independents") or kwargs.get("controls") or []))
    if not regressors:
        raise ValueError("MixedLM requires at least one regressor.")
    group_column = kwargs.get("entity_column") or "firm_id"
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    sample = _flat_frame(frame, numeric_columns=[dependent, *regressors], keep_columns=[group_column])
    formula = f"{dependent} ~ {' + '.join(regressors)}"
    result = MixedLM.from_formula(formula, groups=sample[group_column].astype(str), data=sample).fit(reml=False, disp=False)
    grouped_fit = (
        pd.DataFrame(
            {
                group_column: sample[group_column].astype(str),
                "actual_mean": sample.groupby(group_column)[dependent].transform("mean"),
                "fitted_mean": pd.Series(np.asarray(result.fittedvalues).reshape(-1), index=sample.index).groupby(sample[group_column].astype(str)).transform("mean"),
            }
        )
        .drop_duplicates(subset=[group_column])
        .set_index(group_column)[["actual_mean", "fitted_mean"]]
        .head(20)
    )
    figure = _multi_series_line_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=grouped_fit,
        filename_slug="mixedlm_grouped_fit",
        title="Fitted vs Actual Grouped Plot",
        summary="Group-level actual and fitted means from the mixed-effects model.",
        xlabel="Group",
        ylabel="Grouped mean",
    )
    return _regression_payload(
        model_type="mixedlm",
        model_label="Mixed Effects Linear Model",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=result,
        narrative_lines=["Linear mixed-effects model estimated with statsmodels MixedLM."],
        tables={"group_variance_table": [{"group_column": group_column, "group_count": int(sample[group_column].nunique())}]},
        figures=[figure],
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent, regressor, or grouping values are dropped."]},
        extra_specification={"group_column": group_column},
    )


def _run_arch_family(
    *,
    model_type: str,
    vol: str,
    settings: Any,
    db: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "asset_return"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    distribution = str(_spec_option(kwargs, "distribution", "normal")).lower()
    fitted = arch_model(sample[dependent], mean="Constant", vol=vol, p=int(kwargs.get("garch_p", 1)), o=int(_spec_option(kwargs, "garch_o", 1 if model_type == "gjr_garch" else 0)), q=int(kwargs.get("garch_q", 1)), dist=distribution).fit(disp="off")
    forecast_steps = int(kwargs.get("forecast_steps", 5))
    forecast_method = "analytic"
    try:
        forecast = fitted.forecast(horizon=forecast_steps)
    except ValueError as exc:
        message = str(exc).lower()
        if "analytic forecasts not available" not in message:
            raise
        forecast_method = "simulation"
        forecast = fitted.forecast(
            horizon=forecast_steps,
            method="simulation",
            simulations=int(_spec_option(kwargs, "forecast_simulations", 500)),
        )
    variance = forecast.variance.iloc[-1]
    variance_frame = _forecast_frame_with_time_index(variance.values.reshape(-1, 1), columns=["forecast_variance"], source_index=sample.index)
    figure_a, axis_a = _ts_figure(f"{model_type.upper()} conditional volatility")
    pd.Series(fitted.conditional_volatility, index=sample.index).plot(ax=axis_a)
    figure_a.tight_layout()
    fig1 = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure_a, filename_slug=f"{model_type}_conditional_volatility", title=f"{model_type.upper()} conditional volatility", summary="In-sample conditional volatility from the fitted volatility model.")
    figure_b, axis_b = _ts_figure(f"{model_type.upper()} forecast volatility")
    pd.Series(np.sqrt(variance_frame["forecast_variance"].values), index=variance_frame.index, name="forecast_volatility").plot(ax=axis_b)
    figure_b.tight_layout()
    fig2 = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure_b, filename_slug=f"{model_type}_forecast_volatility", title=f"{model_type.upper()} forecast volatility", summary="Out-of-sample volatility forecast from the fitted model.")
    sample_table = sample.reset_index().rename(columns={sample.index.name or "index": "date"})
    variance_table = variance_frame.reset_index().rename(columns={variance_frame.index.name or "index": "forecast_date"})
    return _nonregression_payload(
        model_type=model_type,
        model_label=model_type.replace("_", " ").upper(),
        engine="arch",
        asset=asset,
        sample=sample_table,
        narrative_lines=[
            f"{model_type.upper()} estimated with distribution={distribution}.",
            f"Forecast horizon: {forecast_steps}.",
            f"Forecast method: {forecast_method}.",
        ],
        tables={"parameter_table": _series_to_table(fitted.params, value_name="coefficient"), "forecast_volatility": _serialize_rows(variance_table)},
        figures=[fig1, fig2],
        specification={"dependent": dependent, "distribution": distribution, "forecast_steps": forecast_steps, "forecast_method": forecast_method},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent are dropped."]},
        metrics={"loglikelihood": _safe_float(getattr(fitted, "loglikelihood", None)), "aic": _safe_float(getattr(fitted, "aic", None)), "bic": _safe_float(getattr(fitted, "bic", None))},
    )


def run_egarch_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_arch_family(model_type="egarch", vol="EGARCH", settings=settings, db=db, **kwargs)


def run_gjr_garch_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _run_arch_family(model_type="gjr_garch", vol="GARCH", settings=settings, db=db, **kwargs)


def run_harx_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "asset_return"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    lags = list(_spec_option(kwargs, "harx_lags", [1, 5, 22]))
    fitted = arch_model(sample[dependent], mean="HARX", lags=lags, vol="GARCH", p=int(kwargs.get("garch_p", 1)), q=int(kwargs.get("garch_q", 1))).fit(disp="off")
    forecast_steps = int(kwargs.get("forecast_steps", 5))
    forecast = fitted.forecast(horizon=forecast_steps)
    variance = forecast.variance.iloc[-1]
    mean_path = forecast.mean.iloc[-1]
    variance_frame = _forecast_frame_with_time_index(variance.values.reshape(-1, 1), columns=["forecast_variance"], source_index=sample.index)
    mean_frame = _forecast_frame_with_time_index(mean_path.values.reshape(-1, 1), columns=["forecast_mean"], source_index=sample.index)
    figure_a, axis_a = _ts_figure("HARX conditional volatility")
    pd.Series(fitted.conditional_volatility, index=sample.index).plot(ax=axis_a)
    figure_a.tight_layout()
    fig1 = _candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=figure_a,
        filename_slug="harx_conditional_volatility",
        title="HARX conditional volatility",
        summary="In-sample conditional volatility from the fitted HARX model.",
    )
    figure_b, axis_b = _ts_figure("HARX forecast path")
    pd.Series(sample[dependent].iloc[-40:], index=sample.index[-40:]).plot(ax=axis_b, label="history")
    mean_frame["forecast_mean"].plot(ax=axis_b, style="--", label="forecast_mean")
    axis_b.legend()
    figure_b.tight_layout()
    fig2 = _candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=figure_b,
        filename_slug="harx_forecast_path",
        title="HARX forecast path",
        summary="Out-of-sample mean forecast from the fitted HARX model.",
    )
    sample_table = sample.reset_index().rename(columns={sample.index.name or "index": "date"})
    mean_table = mean_frame.reset_index().rename(columns={mean_frame.index.name or "index": "forecast_date"})
    variance_table = variance_frame.reset_index().rename(columns={variance_frame.index.name or "index": "forecast_date"})
    return _nonregression_payload(
        model_type="harx",
        model_label="HARX",
        engine="arch",
        asset=asset,
        sample=sample_table,
        narrative_lines=[f"HARX mean model estimated with lags {lags}.", f"Forecast horizon: {forecast_steps}."],
        tables={
            "parameter_table": _series_to_table(fitted.params, value_name="coefficient"),
            "forecast_mean_table": _serialize_rows(mean_table),
            "forecast_volatility": _serialize_rows(variance_table),
        },
        figures=[fig1, fig2],
        specification={"dependent": dependent, "harx_lags": lags, "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent are dropped."]},
        metrics={"aic": _safe_float(getattr(fitted, "aic", None)), "bic": _safe_float(getattr(fitted, "bic", None))},
    )


def _unit_root_sample(settings: Any, db: Any, **kwargs: Any) -> tuple[Any, pd.DataFrame, str]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs.get("dependent") or "asset_return"
    sample = _timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    return asset, sample, dependent


def _series_plot_asset(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    sample: pd.DataFrame,
    column: str,
    title: str,
    filename_slug: str,
    summary: str,
) -> dict[str, Any]:
    figure, axis = _ts_figure(title)
    sample[column].plot(ax=axis, color="#1f4b99", linewidth=1.8)
    axis.axhline(float(sample[column].mean()), color="#ef4444", linestyle="--", linewidth=1.2, label="mean")
    axis.legend()
    figure.tight_layout()
    return _candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=figure,
        filename_slug=filename_slug,
        title=title,
        summary=summary,
    )


def _unit_root_payload(
    *,
    model_type: str,
    model_label: str,
    asset: Any,
    sample: pd.DataFrame,
    engine: str,
    test_result: Any,
    dependent: str,
    settings: Any,
    db: Any,
    kwargs: dict[str, Any],
    extra_specification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    figure = _series_plot_asset(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        sample=sample,
        column=dependent,
        title=f"{model_label} series path",
        filename_slug=f"{model_type}_series",
        summary=f"Series path used in the {model_label} run.",
    )
    critical_values = getattr(test_result, "critical_values", None)
    if isinstance(critical_values, pd.Series):
        critical_rows = [{"level": str(idx), "critical_value": _safe_float(val)} for idx, val in critical_values.items()]
    elif isinstance(critical_values, dict):
        critical_rows = [{"level": str(idx), "critical_value": _safe_float(val)} for idx, val in critical_values.items()]
    else:
        critical_rows = []
    return _nonregression_payload(
        model_type=model_type,
        model_label=model_label,
        engine=engine,
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[
            f"{model_label} evaluated on {dependent}.",
            f"Test statistic: {_safe_float(getattr(test_result, 'stat', None))}.",
            f"P-value: {_safe_float(getattr(test_result, 'pvalue', None))}.",
        ],
        tables={
            "test_summary": [
                {
                    "series": dependent,
                    "statistic": _safe_float(getattr(test_result, "stat", None)),
                    "p_value": _safe_float(getattr(test_result, "pvalue", None)),
                    "lags": _safe_float(getattr(test_result, "lags", None)),
                    "trend": str(getattr(test_result, "trend", "")),
                }
            ],
            "critical_values": critical_rows,
        },
        figures=[figure],
        specification={"dependent": dependent, **(extra_specification or {})},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped before the test."]},
    )


def run_adf_test_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, sample, dependent = _unit_root_sample(settings, db, **kwargs)
    trend = str(_spec_option(kwargs, "trend", "c"))
    lags = _spec_option(kwargs, "unit_root_lags", None)
    result = ADF(sample[dependent], lags=None if lags in {None, ""} else int(lags), trend=trend)
    return _unit_root_payload(
        model_type="adf_test",
        model_label="ADF Unit Root Test",
        asset=asset,
        sample=sample,
        engine="arch",
        test_result=result,
        dependent=dependent,
        settings=settings,
        db=db,
        kwargs=kwargs,
        extra_specification={"trend": trend, "unit_root_lags": None if lags in {None, ""} else int(lags)},
    )


def run_kpss_test_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, sample, dependent = _unit_root_sample(settings, db, **kwargs)
    trend = str(_spec_option(kwargs, "trend", "c"))
    lags = _spec_option(kwargs, "unit_root_lags", None)
    result = KPSS(sample[dependent], lags=None if lags in {None, ""} else int(lags), trend=trend)
    return _unit_root_payload(
        model_type="kpss_test",
        model_label="KPSS Stationarity Test",
        asset=asset,
        sample=sample,
        engine="arch",
        test_result=result,
        dependent=dependent,
        settings=settings,
        db=db,
        kwargs=kwargs,
        extra_specification={"trend": trend, "unit_root_lags": None if lags in {None, ""} else int(lags)},
    )


def run_pp_test_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, sample, dependent = _unit_root_sample(settings, db, **kwargs)
    trend = str(_spec_option(kwargs, "trend", "c"))
    lags = _spec_option(kwargs, "unit_root_lags", None)
    result = PhillipsPerron(sample[dependent], lags=None if lags in {None, ""} else int(lags), trend=trend)
    return _unit_root_payload(
        model_type="pp_test",
        model_label="Phillips-Perron Test",
        asset=asset,
        sample=sample,
        engine="arch",
        test_result=result,
        dependent=dependent,
        settings=settings,
        db=db,
        kwargs=kwargs,
        extra_specification={"trend": trend, "unit_root_lags": None if lags in {None, ""} else int(lags)},
    )


def run_zivot_andrews_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, sample, dependent = _unit_root_sample(settings, db, **kwargs)
    trend = str(_spec_option(kwargs, "trend", "ct"))
    lags = _spec_option(kwargs, "unit_root_lags", None)
    result = ZivotAndrews(sample[dependent], lags=None if lags in {None, ""} else int(lags), trend=trend)
    return _unit_root_payload(
        model_type="zivot_andrews",
        model_label="Zivot-Andrews Break Test",
        asset=asset,
        sample=sample,
        engine="arch",
        test_result=result,
        dependent=dependent,
        settings=settings,
        db=db,
        kwargs=kwargs,
        extra_specification={"trend": trend, "unit_root_lags": None if lags in {None, ""} else int(lags)},
    )


def run_engle_granger_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs.get("dependent") or "level_a"
    exog_columns = kwargs.get("series_columns") or _spec_option(kwargs, "series_columns", ["level_b"])
    if isinstance(exog_columns, str):
        exog_columns = [exog_columns]
    sample = _timeseries_frame(frame, value_columns=[dependent, *list(exog_columns)], time_column=kwargs.get("time_column", "date"))
    result = engle_granger(sample[dependent], sample[list(exog_columns)])
    figure, axis = _ts_figure("Cointegrated series path")
    sample[[dependent, *list(exog_columns)]].plot(ax=axis, linewidth=1.5)
    figure.tight_layout()
    fig_asset = _candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=figure,
        filename_slug="engle_granger_series",
        title="Cointegrated series path",
        summary="Series included in the Engle-Granger cointegration test.",
    )
    critical_values = getattr(result, "critical_values", None)
    critical_rows = []
    if isinstance(critical_values, pd.Series):
        critical_rows = [{"level": str(idx), "critical_value": _safe_float(val)} for idx, val in critical_values.items()]
    return _nonregression_payload(
        model_type="engle_granger",
        model_label="Engle-Granger Cointegration",
        engine="arch",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[
            f"Engle-Granger cointegration test with dependent series {dependent}.",
            f"Cointegrating regressors: {', '.join(list(exog_columns))}.",
        ],
        tables={
            "cointegration_test": [
                {
                    "dependent": dependent,
                    "regressors": ", ".join(list(exog_columns)),
                    "statistic": _safe_float(getattr(result, "stat", None)),
                    "p_value": _safe_float(getattr(result, "pvalue", None)),
                    "distribution_order": _safe_float(getattr(result, "distribution_order", None)),
                }
            ],
            "critical_values": critical_rows,
        },
        figures=[fig_asset],
        specification={"dependent": dependent, "series_columns": list(exog_columns)},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped before the test."]},
    )


def _cointegration_regression(
    *,
    settings: Any,
    db: Any,
    kwargs: dict[str, Any],
    model_type: str,
    model_label: str,
    fitter: Callable[[pd.Series, pd.DataFrame], Any],
) -> dict[str, Any]:
    pc = _pc()
    asset, frame = _load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs.get("dependent") or "level_a"
    exog_columns = kwargs.get("series_columns") or _spec_option(kwargs, "series_columns", ["level_b"])
    if isinstance(exog_columns, str):
        exog_columns = [exog_columns]
    sample = _timeseries_frame(frame, value_columns=[dependent, *list(exog_columns)], time_column=kwargs.get("time_column", "date"))
    fitted = fitter(sample[dependent], sample[list(exog_columns)])
    fitted_values = getattr(fitted, "fitted_values", None)
    if fitted_values is None:
        design_matrix = sm.add_constant(sample[list(exog_columns)], has_constant="add")
        param_vector = np.zeros(design_matrix.shape[1], dtype=float)
        raw_params = getattr(fitted, "params", None)
        if raw_params is not None:
            param_series = pd.Series(raw_params)
            for column_index, column_name in enumerate(design_matrix.columns):
                param_vector[column_index] = _safe_float(param_series.get(column_name, 0.0)) or 0.0
        fitted_values = pd.Series(np.dot(design_matrix, param_vector), index=sample.index)
    else:
        fitted_values = pd.Series(fitted_values, index=sample.index)
    residuals = sample[dependent] - fitted_values
    figure, axis = _ts_figure(f"{model_label} residual path")
    residuals.plot(ax=axis, color="#7c3aed")
    axis.axhline(0, color="#0f172a", linewidth=1.0)
    figure.tight_layout()
    fig_asset = _candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=figure,
        filename_slug=f"{model_type}_residuals",
        title=f"{model_label} residual path",
        summary=f"Residual series from the {model_label} cointegration regression.",
    )
    parameter_table = pc._parameter_table(
        getattr(fitted, "params", None),
        std_errors=getattr(fitted, "std_errors", getattr(fitted, "bse", None)),
        tvalues=getattr(fitted, "tvalues", getattr(fitted, "tstats", None)),
        pvalues=list(getattr(fitted, "pvalues", [])) if getattr(fitted, "pvalues", None) is not None else None,
    )
    residual_summary = [
        {
            "residual_mean": _safe_float(residuals.mean()),
            "residual_std": _safe_float(residuals.std(ddof=1)),
            "residual_min": _safe_float(residuals.min()),
            "residual_max": _safe_float(residuals.max()),
            "residual_variance": _safe_float(getattr(fitted, "residual_variance", None)),
            "long_run_variance": _safe_float(getattr(fitted, "long_run_variance", None)),
            "kernel": getattr(fitted, "kernel", None),
            "bandwidth": _safe_float(getattr(fitted, "bandwidth", None)),
            "leads": _safe_float(getattr(fitted, "leads", None)),
            "lags": _safe_float(getattr(fitted, "lags", None)),
            "r_squared": _safe_float(getattr(fitted, "rsquared", None)),
            "adj_r_squared": _safe_float(getattr(fitted, "rsquared_adj", None)),
        }
    ]
    fitted_preview = pd.DataFrame(
        {
            "date": sample.index,
            "observed": sample[dependent].to_numpy(),
            "fitted": fitted_values.to_numpy(),
            "residual": residuals.to_numpy(),
        }
    )
    return _regression_payload(
        model_type=model_type,
        model_label=model_label,
        engine="arch",
        asset=asset,
        dependent=dependent,
        regressors=list(exog_columns),
        sample=sample.reset_index(),
        result=fitted,
        narrative_lines=[
            f"{model_label} estimated with dependent series {dependent}.",
            f"Cointegrating regressors: {', '.join(list(exog_columns))}.",
            "The result includes parameter estimates, long-run diagnostics, and fitted-versus-observed previews for manual verification.",
        ],
        tables={
            "cointegration_regression": parameter_table,
            "residual_diagnostics": residual_summary,
            "fitted_preview": _serialize_rows(fitted_preview, limit=24),
        },
        figures=[fig_asset],
        extra_specification={"dependent": dependent, "series_columns": list(exog_columns)},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped before estimation."]},
    )


def run_dynamic_ols_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _cointegration_regression(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="dynamic_ols",
        model_label="Dynamic OLS",
        fitter=lambda y, x: DynamicOLS(y, x).fit(),
    )


def run_fm_ols_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    return _cointegration_regression(
        settings=settings,
        db=db,
        kwargs=kwargs,
        model_type="fm_ols",
        model_label="Fully Modified OLS",
        fitter=lambda y, x: FullyModifiedOLS(y, x).fit(),
    )


def _return_matrix_sample(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    asset_id: str,
    series_columns: list[str],
    time_column: str,
) -> tuple[Any, pd.DataFrame]:
    asset, frame = _load_asset_frame(settings, db, user=user, workspace=workspace, asset_id=asset_id)
    if not series_columns:
        raise ValueError("Portfolio optimization requires return series columns.")
    sample = _timeseries_frame(frame, value_columns=series_columns, time_column=time_column or "date")
    return asset, sample


def _portfolio_weights_table(weights: dict[str, float]) -> list[dict[str, Any]]:
    return [{"asset": asset, "weight": _safe_float(weight)} for asset, weight in weights.items()]


def _portfolio_metric_rows(expected_ret: float, volatility: float, sharpe: float, *, label: str = "portfolio") -> list[dict[str, Any]]:
    return [
        {"portfolio": label, "metric": "expected_return", "value": _safe_float(expected_ret)},
        {"portfolio": label, "metric": "volatility", "value": _safe_float(volatility)},
        {"portfolio": label, "metric": "sharpe", "value": _safe_float(sharpe)},
    ]


def _portfolio_performance_values(values: Any) -> tuple[float, float, float]:
    if isinstance(values, (list, tuple)):
        if len(values) >= 3:
            return float(values[0]), float(values[1]), float(values[2])
        if len(values) == 2:
            return float(values[0]), float(values[1]), 0.0
        if len(values) == 1:
            return float(values[0]), 0.0, 0.0
    return _safe_float(values), 0.0, 0.0


def _portfolio_frontier_figure(
    settings: Any,
    db: Any,
    *,
    user: Any,
    workspace: Any,
    source_asset: Any,
    frontier_rows: list[dict[str, Any]],
    filename_slug: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    frontier_frame = pd.DataFrame(frontier_rows)
    figure, axis = _ts_figure(title)
    axis.scatter(frontier_frame["volatility"], frontier_frame["expected_return"], color="#2563eb", s=28)
    axis.set_xlabel("Volatility")
    axis.set_ylabel("Expected return")
    figure.tight_layout()
    return _candidate_figure(settings, db, user=user, workspace=workspace, source_asset=source_asset, figure=figure, filename_slug=filename_slug, title=title, summary=summary)


def _build_frontier_rows(mu: pd.Series, sigma: pd.DataFrame, *, weight_bounds: tuple[float, float]) -> list[dict[str, Any]]:
    frontier_rows: list[dict[str, Any]] = []
    min_mu = float(mu.min())
    max_mu = float(mu.max())
    targets = np.linspace(min_mu, max_mu, num=12)
    for target in targets:
        try:
            ef = EfficientFrontier(mu, sigma, weight_bounds=weight_bounds)
            ef.efficient_return(float(target))
            ret, vol, sharpe = _portfolio_performance_values(ef.portfolio_performance(verbose=False))
            frontier_rows.append({"target_return": float(target), "expected_return": _safe_float(ret), "volatility": _safe_float(vol), "sharpe": _safe_float(sharpe)})
        except Exception:
            continue
    return frontier_rows


def run_efficient_frontier_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    mu = expected_returns.mean_historical_return(returns, returns_data=True)
    sigma = risk_models.sample_cov(returns, returns_data=True)
    bounds = (0, 1) if bool(_spec_option(kwargs, "long_only", True)) else (-1, 1)
    objective = str(_spec_option(kwargs, "portfolio_objective", "max_sharpe")).lower()
    ef = EfficientFrontier(mu, sigma, weight_bounds=bounds)
    if objective == "min_volatility":
        ef.min_volatility()
    elif objective == "max_quadratic_utility":
        ef.max_quadratic_utility(risk_aversion=float(_spec_option(kwargs, "risk_aversion", 3.0)))
    else:
        ef.max_sharpe()
    weights = ef.clean_weights()
    ret, vol, sharpe = _portfolio_performance_values(ef.portfolio_performance(verbose=False))
    frontier_rows = _build_frontier_rows(mu, sigma, weight_bounds=bounds)
    fig_asset = _portfolio_frontier_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, frontier_rows=frontier_rows or [{"expected_return": ret, "volatility": vol, "sharpe": sharpe}], filename_slug="efficient_frontier", title="Efficient frontier", summary="Mean-variance frontier implied by the return sample.")
    return _nonregression_payload(
        model_type="efficient_frontier",
        model_label="Efficient Frontier",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"Efficient frontier optimized with objective {objective}.", f"Assets: {', '.join(series_columns)}."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(ret, vol, sharpe), "frontier_table": frontier_rows},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "portfolio_objective": objective, "long_only": bool(_spec_option(kwargs, "long_only", True))},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_semivariance_frontier_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    mu = expected_returns.mean_historical_return(returns, returns_data=True)
    bounds = (0, 1) if bool(_spec_option(kwargs, "long_only", True)) else (-1, 1)
    es = EfficientSemivariance(mu, returns, weight_bounds=bounds)
    es.min_semivariance()
    weights = es.clean_weights()
    ret, vol, sharpe = _portfolio_performance_values(es.portfolio_performance(verbose=False))
    downside = returns.clip(upper=0).pow(2).mean()
    figure, axis = _ts_figure("Downside risk contribution")
    downside.plot(kind="bar", ax=axis, color="#b45309")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="semivariance_contribution", title="Downside risk contribution", summary="Per-asset downside semivariance contribution.")
    return _nonregression_payload(
        model_type="semivariance_frontier",
        model_label="Efficient Semivariance",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Efficient semivariance portfolio estimated with PyPortfolioOpt."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(ret, vol, sharpe), "downside_semivariance": _serialize_rows(downside.reset_index().rename(columns={"index": "asset", 0: "downside_semivariance"}))},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "long_only": bool(_spec_option(kwargs, "long_only", True))},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_cvar_frontier_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    mu = expected_returns.mean_historical_return(returns, returns_data=True)
    bounds = (0, 1) if bool(_spec_option(kwargs, "long_only", True)) else (-1, 1)
    beta = float(_spec_option(kwargs, "cvar_beta", 0.95))
    ec = EfficientCVaR(mu, returns, beta=beta, weight_bounds=bounds)
    ec.min_cvar()
    weights = ec.clean_weights()
    ret, vol, sharpe = _portfolio_performance_values(ec.portfolio_performance(verbose=False))
    portfolio_returns = returns.mul(pd.Series(weights), axis=1).sum(axis=1)
    cvar = float(portfolio_returns[portfolio_returns <= portfolio_returns.quantile(1 - beta)].mean())
    figure, axis = _ts_figure("Portfolio return distribution")
    axis.hist(portfolio_returns, bins=25, color="#2563eb", alpha=0.75)
    axis.axvline(portfolio_returns.quantile(1 - beta), color="#ef4444", linestyle="--", linewidth=1.2)
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="cvar_distribution", title="Portfolio return distribution", summary="Portfolio return distribution used in the CVaR optimization.")
    return _nonregression_payload(
        model_type="cvar_frontier",
        model_label="Efficient CVaR",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"CVaR frontier estimated at beta={beta:.2f}."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(ret, vol, sharpe), "tail_risk_table": [{"beta": beta, "portfolio_cvar": cvar}]},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "cvar_beta": beta, "long_only": bool(_spec_option(kwargs, "long_only", True))},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_cdar_frontier_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    mu = expected_returns.mean_historical_return(returns, returns_data=True)
    bounds = (0, 1) if bool(_spec_option(kwargs, "long_only", True)) else (-1, 1)
    beta = float(_spec_option(kwargs, "cdar_beta", 0.95))
    ec = EfficientCDaR(mu, returns, beta=beta, weight_bounds=bounds)
    ec.min_cdar()
    weights = ec.clean_weights()
    ret, vol, sharpe = _portfolio_performance_values(ec.portfolio_performance(verbose=False))
    portfolio_returns = returns.mul(pd.Series(weights), axis=1).sum(axis=1)
    running_wealth = (1.0 + portfolio_returns).cumprod()
    drawdown = running_wealth / running_wealth.cummax() - 1.0
    cdar = float(drawdown[drawdown <= drawdown.quantile(1 - beta)].mean())
    figure, axis = _ts_figure("Portfolio drawdown path")
    axis.plot(drawdown.index, drawdown.to_numpy(), color="#dc2626")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="cdar_drawdown", title="Portfolio drawdown path", summary="Portfolio drawdown series used in the CDaR optimization.")
    return _nonregression_payload(
        model_type="cdar_frontier",
        model_label="Efficient CDaR",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"CDaR frontier estimated at beta={beta:.2f}."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(ret, vol, sharpe), "drawdown_risk_table": [{"beta": beta, "portfolio_cdar": cdar}]},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "cdar_beta": beta, "long_only": bool(_spec_option(kwargs, "long_only", True))},
        audit_trail={"derived_columns": ["running_wealth", "drawdown"], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_black_litterman_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    covariance = risk_models.sample_cov(returns, returns_data=True)
    market_caps = {column: 1.0 for column in series_columns}
    views = {column: float(returns[column].mean()) for column in series_columns[: min(2, len(series_columns))]}
    bl = black_litterman.BlackLittermanModel(covariance, pi="equal", absolute_views=views, market_caps=market_caps)
    posterior_rets = bl.bl_returns()
    posterior_cov = bl.bl_cov()
    ef = EfficientFrontier(posterior_rets, posterior_cov)
    ef.max_sharpe()
    weights = ef.clean_weights()
    ret, vol, sharpe = _portfolio_performance_values(ef.portfolio_performance(verbose=False))
    view_frame = pd.DataFrame({"asset": list(views.keys()), "view_return": list(views.values()), "posterior_return": [posterior_rets[k] for k in views.keys()]})
    figure, axis = _ts_figure("Black-Litterman prior vs posterior returns")
    view_frame.set_index("asset")[["view_return", "posterior_return"]].plot(kind="bar", ax=axis)
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="black_litterman_views", title="Black-Litterman posterior returns", summary="Posterior asset-return views after combining priors and user views.")
    return _nonregression_payload(
        model_type="black_litterman",
        model_label="Black-Litterman",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Black-Litterman posterior returns combined with an efficient frontier optimizer."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(ret, vol, sharpe), "view_table": _serialize_rows(view_frame)},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "view_assets": list(views.keys())},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_hrp_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    returns = sample[series_columns]
    hrp = HRPOpt(returns=returns)
    weights = hrp.optimize()
    cov = returns.cov()
    weights_series = pd.Series(weights)
    port_vol = float(np.sqrt(weights_series.T @ cov @ weights_series))
    port_ret = float(returns.mean().dot(weights_series))
    sharpe = port_ret / port_vol if port_vol else 0.0
    figure, axis = _ts_figure("HRP weights")
    weights_series.sort_values(ascending=False).plot(kind="bar", ax=axis, color="#0f766e")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="hrp_weights", title="Hierarchical risk parity weights", summary="Weight allocation from the hierarchical risk parity optimizer.")
    return _nonregression_payload(
        model_type="hrp",
        model_label="Hierarchical Risk Parity",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Hierarchical risk parity allocation estimated from the sample covariance structure."],
        tables={"weights_table": _portfolio_weights_table(weights), "portfolio_metrics": _portfolio_metric_rows(port_ret, port_vol, sharpe)},
        figures=[fig_asset],
        specification={"series_columns": series_columns},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )


def run_discrete_allocation_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    asset, sample = _return_matrix_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], series_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    prices = pd.DataFrame({column: 100 * np.exp(sample[column].cumsum()) for column in series_columns}, index=sample.index)
    latest_prices = get_latest_prices(prices)
    mu = expected_returns.mean_historical_return(sample[series_columns], returns_data=True)
    sigma = risk_models.sample_cov(sample[series_columns], returns_data=True)
    ef = EfficientFrontier(mu, sigma)
    ef.max_sharpe()
    weights = ef.clean_weights()
    capital = float(_spec_option(kwargs, "capital", 100000.0))
    allocation, leftover = DiscreteAllocation(weights, latest_prices, total_portfolio_value=capital).lp_portfolio()
    alloc_frame = pd.DataFrame({"asset": list(allocation.keys()), "shares": list(allocation.values()), "latest_price": [float(latest_prices[k]) for k in allocation.keys()]})
    figure, axis = _ts_figure("Discrete allocation")
    alloc_frame.set_index("asset")["shares"].plot(kind="bar", ax=axis, color="#9333ea")
    figure.tight_layout()
    fig_asset = _candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=figure, filename_slug="discrete_allocation", title="Discrete allocation", summary="Integer holdings implied by the optimized continuous weights.")
    return _nonregression_payload(
        model_type="discrete_allocation",
        model_label="Discrete Allocation",
        engine="pypfopt",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=[f"Discrete allocation solved for capital={capital:.2f}.", f"Leftover cash: {leftover:.2f}."],
        tables={"weights_table": _portfolio_weights_table(weights), "allocation_table": _serialize_rows(alloc_frame), "cash_table": [{"capital": capital, "leftover_cash": float(leftover)}]},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "capital": capital},
        audit_trail={"derived_columns": ["synthetic_price_paths_from_returns"], "filters": ["Rows with missing return observations are dropped before optimization."]},
    )
