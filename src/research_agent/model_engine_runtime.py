from __future__ import annotations

from typing import Any

import pandas as pd
from linearmodels.asset_pricing import LinearFactorModel
from statsmodels.discrete.discrete_model import Logit, Probit
from statsmodels.genmod.families import Poisson
from statsmodels.genmod.generalized_linear_model import GLM
from statsmodels.tsa.api import VAR
from statsmodels.tsa.arima.model import ARIMA

import research_agent.model_engine_extensions as base
from research_agent.model_engine_bayesian import (
    run_bayesian_did_analysis,
    run_bayesian_its_analysis,
    run_bayesian_linear_regression_analysis,
    run_bayesian_panel_analysis,
)
from research_agent.model_engine_causal import (
    run_candidate_did_analysis,
    run_candidate_event_study_analysis,
    run_candidate_rdd_analysis,
    run_instrumental_causal_analysis,
    run_interrupted_time_series_analysis,
    run_inverse_propensity_weighting_analysis,
    run_regression_kink_analysis,
    run_staggered_did_analysis,
    run_synthetic_control_analysis,
)
from research_agent.model_engine_quant import (
    run_quant_backtest_report_analysis,
    run_quant_catboost_analysis,
    run_quant_lightgbm_analysis,
    run_quant_linear_model_analysis,
    run_quant_position_analysis,
)


def _relabel_payload(payload: dict[str, Any], *, model_type: str, model_label: str) -> dict[str, Any]:
    payload = dict(payload)
    payload["model_type"] = model_type
    payload["model_label"] = model_label
    return payload


def _candidate_ols_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]
    sample = base._flat_frame(frame, numeric_columns=[dependent, *regressors], keep_columns=[])
    exog = base.sm.add_constant(sample[regressors], has_constant="add")
    result = base.sm.OLS(sample[dependent], exog).fit(cov_type="HC1")
    return base._regression_payload(
        model_type="ols",
        model_label="OLS",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=result,
        narrative_lines=["Candidate OLS estimated with statsmodels."],
        tables={"design_audit_table": [{"observation_count": int(len(sample)), "regressor_count": int(len(regressors))}]},
        figures=[],
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped."]},
    )


def _candidate_ppml_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]
    sample = base._flat_frame(frame, numeric_columns=[dependent, *regressors], keep_columns=[])
    if (sample[dependent] < 0).any():
        raise ValueError("PPML requires a nonnegative dependent variable; negative values must be fixed before modeling.")
    exog = base.sm.add_constant(sample[regressors], has_constant="add")
    result = GLM(sample[dependent], exog, family=Poisson()).fit(cov_type="HC1")
    return base._regression_payload(
        model_type="ppml",
        model_label="PPML",
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=result,
        narrative_lines=["Candidate PPML estimated with statsmodels GLM Poisson."],
        tables={"design_audit_table": [{"observation_count": int(len(sample)), "regressor_count": int(len(regressors))}]},
        figures=[],
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped.", "Dependent variable validated as nonnegative; no clipping applied."]},
    )


def _candidate_binary_analysis(settings: Any, db: Any, *, model_type: str, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"]
    regressors = [*(kwargs.get("independents") or []), *(kwargs.get("controls") or [])]
    sample = base._flat_frame(frame, numeric_columns=[dependent, *regressors], keep_columns=[])
    values = set(float(value) for value in sample[dependent].dropna().unique().tolist())
    if not values.issubset({0.0, 1.0}):
        raise ValueError(f"{model_type} requires a binary 0/1 dependent variable; coercive rounding is not allowed.")
    exog = base.sm.add_constant(sample[regressors], has_constant="add")
    fitter = Logit if model_type == "logit" else Probit
    result = fitter(sample[dependent], exog).fit(disp=False)
    return base._regression_payload(
        model_type=model_type,
        model_label=model_type.upper(),
        engine="statsmodels",
        asset=asset,
        dependent=dependent,
        regressors=list(exog.columns),
        sample=sample,
        result=result,
        narrative_lines=[f"Candidate {model_type} estimated with statsmodels discrete choice model."],
        tables={"classification_audit_table": [{"positive_share": float(sample[dependent].mean()), "observation_count": int(len(sample))}]},
        figures=[],
        audit_trail={"derived_columns": [], "filters": ["Rows with missing dependent or regressors are dropped.", "Dependent variable validated as binary 0/1; no rounding or clipping applied."]},
    )


def _candidate_arima_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    dependent = kwargs["dependent"] or "policy_rate"
    sample = base._timeseries_frame(frame, value_columns=[dependent], time_column=kwargs.get("time_column", "date"))
    order = (
        int(base._spec_option(kwargs, "arima_p", kwargs.get("arima_p", 1))),
        int(base._spec_option(kwargs, "arima_d", kwargs.get("arima_d", 0))),
        int(base._spec_option(kwargs, "arima_q", kwargs.get("arima_q", 1))),
    )
    forecast_steps = int(base._spec_option(kwargs, "forecast_steps", 6))
    fitted = ARIMA(sample[dependent], order=order).fit()
    forecast = fitted.get_forecast(steps=forecast_steps)
    forecast_frame = forecast.summary_frame().reset_index().rename(columns={"index": "step"})
    fig, ax = base._ts_figure("Candidate ARIMA forecast")
    sample[dependent].iloc[-40:].plot(ax=ax, label="history")
    pd.Series(forecast.predicted_mean).plot(ax=ax, style="--", label="forecast")
    ax.legend()
    fig.tight_layout()
    fig_asset = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig, filename_slug="candidate_arima_forecast", title="Candidate ARIMA forecast", summary="Forecast path from candidate ARIMA.")
    return base._nonregression_payload(
        model_type="arima",
        model_label="ARIMA Forecast",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Candidate ARIMA estimated with statsmodels."],
        tables={"parameter_table": base._series_to_table(fitted.params, value_name="coefficient"), "forecast_summary": base._serialize_rows(forecast_frame)},
        figures=[fig_asset],
        specification={"dependent": dependent, "order": order, "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
    )


def _candidate_var_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    lags = int(base._spec_option(kwargs, "var_lags", kwargs.get("var_lags", 2)))
    forecast_steps = int(base._spec_option(kwargs, "forecast_steps", 5))
    sample = base._timeseries_frame(frame, value_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    fitted = VAR(sample).fit(lags)
    forecast = fitted.forecast(sample.values[-lags:], steps=forecast_steps)
    forecast_frame = pd.DataFrame(forecast, columns=series_columns)
    fig, ax = base._ts_figure("Candidate VAR forecast")
    forecast_frame[series_columns[0]].plot(ax=ax, style="--", label="forecast")
    sample[series_columns[0]].iloc[-40:].reset_index(drop=True).plot(ax=ax, label="history")
    ax.legend()
    fig.tight_layout()
    fig_asset = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig, filename_slug="candidate_var_forecast", title="Candidate VAR forecast", summary="Forecast path from candidate VAR.")
    return base._nonregression_payload(
        model_type="var",
        model_label="Vector Autoregression",
        engine="statsmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Candidate VAR estimated with statsmodels."],
        tables={"coefficient_table": base._equation_table(fitted.params), "forecast_summary": base._serialize_rows(forecast_frame.reset_index().rename(columns={"index": "step"}))},
        figures=[fig_asset],
        specification={"series_columns": series_columns, "var_lags": lags, "forecast_steps": forecast_steps},
        audit_trail={"derived_columns": [], "filters": ["Rows with missing series values are dropped."]},
    )


def _candidate_svar_irf_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    payload = _candidate_var_analysis(settings, db, **kwargs)
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    series_columns = kwargs.get("series_columns") or ["return_a", "return_b", "return_c"]
    lags = int(base._spec_option(kwargs, "var_lags", kwargs.get("var_lags", 2)))
    horizon = int(base._spec_option(kwargs, "irf_horizon", kwargs.get("irf_horizon", 10)))
    impulse_column = kwargs.get("impulse_column") or series_columns[0]
    response_column = kwargs.get("response_column") or series_columns[min(1, len(series_columns) - 1)]
    sample = base._timeseries_frame(frame, value_columns=series_columns, time_column=kwargs.get("time_column", "date"))
    fitted = VAR(sample).fit(lags)
    irf = fitted.irf(horizon)
    impulse_idx = series_columns.index(impulse_column)
    response_idx = series_columns.index(response_column)
    response = irf.orth_irfs[:, response_idx, impulse_idx]
    cumulative = response.cumsum()
    irf_rows = [{"horizon": int(h), "response": base._safe_float(v), "cumulative_response": base._safe_float(c)} for h, (v, c) in enumerate(zip(response, cumulative, strict=False))]
    fig1, ax1 = base._ts_figure("Candidate SVAR IRF")
    ax1.plot(range(len(response)), response, marker="o")
    fig1.tight_layout()
    fig2, ax2 = base._ts_figure("Candidate cumulative SVAR IRF")
    ax2.plot(range(len(cumulative)), cumulative, marker="o")
    fig2.tight_layout()
    fig_asset_1 = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig1, filename_slug="candidate_svar_irf", title="Candidate SVAR IRF", summary="Orthogonal impulse response from candidate SVAR.")
    fig_asset_2 = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig2, filename_slug="candidate_svar_cum_irf", title="Candidate cumulative SVAR IRF", summary="Cumulative orthogonal impulse response from candidate SVAR.")
    return {
        **payload,
        "model_type": "svar_irf",
        "model_label": "SVAR IRF",
        "tables": {**(payload.get("tables") or {}), "irf_table": irf_rows},
        "figures": [fig_asset_1, fig_asset_2],
        "specification": {**(payload.get("specification") or {}), "irf_horizon": horizon, "impulse_column": impulse_column, "response_column": response_column},
    }


def _candidate_arch_family_analysis(settings: Any, db: Any, *, model_type: str, **kwargs: Any) -> dict[str, Any]:
    vol = "ARCH" if model_type == "arch" else "GARCH"
    return base._run_arch_family(model_type=model_type, vol=vol, settings=settings, db=db, **kwargs)


def _candidate_mean_variance_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    payload = base.run_efficient_frontier_analysis(settings, db, **kwargs)
    return _relabel_payload(payload, model_type="mean_variance", model_label="Mean-Variance Portfolio")


def _candidate_minimum_variance_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    payload = base.run_efficient_frontier_analysis(settings, db, **{**kwargs, "portfolio_objective": "min_volatility"})
    return _relabel_payload(payload, model_type="minimum_variance", model_label="Minimum Variance Portfolio")


def _candidate_risk_parity_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    payload = base.run_hrp_analysis(settings, db, **kwargs)
    return _relabel_payload(payload, model_type="risk_parity", model_label="Risk Parity")


def _candidate_capm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    market_column = kwargs.get("market_column") or "market_return"
    series_columns = kwargs.get("series_columns") or [kwargs.get("dependent") or "return_a"]
    columns = [market_column, *series_columns]
    sample = base._timeseries_frame(frame, value_columns=columns, time_column=kwargs.get("time_column", "date"))
    result = LinearFactorModel(sample[series_columns], sample[[market_column]]).fit()
    return base._nonregression_payload(
        model_type="capm",
        model_label="CAPM",
        engine="linearmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Candidate CAPM estimated with linearmodels asset pricing."],
        tables={
            "risk_premia_table": base._series_to_table(result.risk_premia, value_name="risk_premium"),
            "alpha_table": base._series_to_table(result.alphas, value_name="alpha"),
            "beta_table": base._serialize_rows(result.betas.reset_index().rename(columns={"index": "portfolio"})),
        },
        figures=[],
        specification={"market_column": market_column, "series_columns": series_columns},
        audit_trail={"derived_columns": [], "filters": []},
    )


def _candidate_fama_french_3_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    factor_columns = [kwargs.get("market_column") or "market_return", kwargs.get("smb_column") or "smb", kwargs.get("hml_column") or "hml"]
    series_columns = kwargs.get("series_columns") or [kwargs.get("dependent") or "return_a"]
    sample = base._timeseries_frame(frame, value_columns=[*series_columns, *factor_columns], time_column=kwargs.get("time_column", "date"))
    result = LinearFactorModel(sample[series_columns], sample[factor_columns]).fit()
    return base._nonregression_payload(
        model_type="fama_french_3",
        model_label="Fama-French 3-Factor",
        engine="linearmodels",
        asset=asset,
        sample=sample.reset_index(),
        narrative_lines=["Candidate Fama-French three-factor model estimated with linearmodels asset pricing."],
        tables={
            "risk_premia_table": base._series_to_table(result.risk_premia, value_name="risk_premium"),
            "alpha_table": base._series_to_table(result.alphas, value_name="alpha"),
            "beta_table": base._serialize_rows(result.betas.reset_index().rename(columns={"index": "portfolio"})),
        },
        figures=[],
        specification={"series_columns": series_columns, "factor_columns": factor_columns},
        audit_trail={"derived_columns": [], "filters": []},
    )


EXTENSION_RUNNERS = {
    "random_effects": base.run_random_effects_analysis,
    "first_difference": base.run_first_difference_analysis,
    "between_ols": base.run_between_ols_analysis,
    "pooled_ols": base.run_pooled_ols_analysis,
    "fama_macbeth": base.run_fama_macbeth_analysis,
    "iv_liml": base.run_iv_liml_analysis,
    "iv_gmm": base.run_iv_gmm_analysis,
    "absorbing_ls": base.run_absorbing_ls_analysis,
    "sur": base.run_sur_analysis,
    "iv_3sls": base.run_iv_3sls_analysis,
    "system_gmm": base.run_system_gmm_analysis,
    "traded_factor_model": base.run_traded_factor_model_analysis,
    "linear_factor_gmm": base.run_linear_factor_gmm_analysis,
    "glm": base.run_glm_analysis,
    "quantile_regression": base.run_quantile_regression_analysis,
    "gee": base.run_gee_analysis,
    "mnlogit": base.run_mnlogit_analysis,
    "negative_binomial": base.run_negative_binomial_analysis,
    "zero_inflated_count": base.run_zero_inflated_count_analysis,
    "mixedlm": base.run_mixedlm_analysis,
    "varmax": base.run_varmax_analysis,
    "vecm": base.run_vecm_analysis,
    "markov_switching": base.run_markov_switching_analysis,
    "unobserved_components": base.run_unobserved_components_analysis,
    "exponential_smoothing": base.run_exponential_smoothing_analysis,
    "egarch": base.run_egarch_analysis,
    "gjr_garch": base.run_gjr_garch_analysis,
    "harx": base.run_harx_analysis,
    "adf_test": base.run_adf_test_analysis,
    "kpss_test": base.run_kpss_test_analysis,
    "pp_test": base.run_pp_test_analysis,
    "zivot_andrews": base.run_zivot_andrews_analysis,
    "engle_granger": base.run_engle_granger_analysis,
    "dynamic_ols": base.run_dynamic_ols_analysis,
    "fm_ols": base.run_fm_ols_analysis,
    "efficient_frontier": base.run_efficient_frontier_analysis,
    "semivariance_frontier": base.run_semivariance_frontier_analysis,
    "cvar_frontier": base.run_cvar_frontier_analysis,
    "cdar_frontier": base.run_cdar_frontier_analysis,
    "black_litterman": base.run_black_litterman_analysis,
    "hrp": base.run_hrp_analysis,
    "discrete_allocation": base.run_discrete_allocation_analysis,
    "staggered_did": run_staggered_did_analysis,
    "synthetic_control": run_synthetic_control_analysis,
    "interrupted_time_series": run_interrupted_time_series_analysis,
    "regression_kink": run_regression_kink_analysis,
    "instrumental_causal": run_instrumental_causal_analysis,
    "inverse_propensity_weighting": run_inverse_propensity_weighting_analysis,
    "bayesian_linear_regression": run_bayesian_linear_regression_analysis,
    "bayesian_panel": run_bayesian_panel_analysis,
    "bayesian_did": run_bayesian_did_analysis,
    "bayesian_its": run_bayesian_its_analysis,
    "quant_linear_model": run_quant_linear_model_analysis,
    "quant_lightgbm": run_quant_lightgbm_analysis,
    "quant_catboost": run_quant_catboost_analysis,
    "quant_backtest_report": run_quant_backtest_report_analysis,
    "position_analysis": run_quant_position_analysis,
}


OVERLAP_CANDIDATE_RUNNERS = {
    "ols": _candidate_ols_analysis,
    "ppml": _candidate_ppml_analysis,
    "logit": lambda settings, db, **kwargs: _candidate_binary_analysis(settings, db, model_type="logit", **kwargs),
    "probit": lambda settings, db, **kwargs: _candidate_binary_analysis(settings, db, model_type="probit", **kwargs),
    "fixed_effects": base._candidate_fixed_effects_analysis,
    "panel_iv": base._candidate_panel_iv_analysis,
    "did": run_candidate_did_analysis,
    "event_study": run_candidate_event_study_analysis,
    "rdd": run_candidate_rdd_analysis,
    "arima": _candidate_arima_analysis,
    "var": _candidate_var_analysis,
    "svar_irf": _candidate_svar_irf_analysis,
    "arch": lambda settings, db, **kwargs: _candidate_arch_family_analysis(settings, db, model_type="arch", **kwargs),
    "garch": lambda settings, db, **kwargs: _candidate_arch_family_analysis(settings, db, model_type="garch", **kwargs),
    "mean_variance": _candidate_mean_variance_analysis,
    "minimum_variance": _candidate_minimum_variance_analysis,
    "risk_parity": _candidate_risk_parity_analysis,
    "capm": _candidate_capm_analysis,
    "fama_french_3": _candidate_fama_french_3_analysis,
}


def supports_model(model_type: str) -> bool:
    return model_type.strip().lower() in EXTENSION_RUNNERS


def has_candidate(model_type: str) -> bool:
    return model_type.strip().lower() in OVERLAP_CANDIDATE_RUNNERS


def run_extension_model_analysis(settings: Any, db: Any, *, model_type: str, **kwargs: Any) -> dict[str, Any]:
    normalized = model_type.strip().lower()
    try:
        runner = EXTENSION_RUNNERS[normalized]
    except KeyError as exc:
        raise KeyError(f"No extension runner registered for {normalized}.") from exc
    return runner(settings, db, **kwargs)


def run_candidate_model_analysis(settings: Any, db: Any, *, model_type: str, **kwargs: Any) -> dict[str, Any]:
    normalized = model_type.strip().lower()
    try:
        runner = OVERLAP_CANDIDATE_RUNNERS[normalized]
    except KeyError as exc:
        raise KeyError(f"No candidate runner registered for {normalized}.") from exc
    return runner(settings, db, **kwargs)
