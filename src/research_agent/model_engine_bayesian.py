from __future__ import annotations

from typing import Any

import arviz as az
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymc as pm

import research_agent.model_engine_extensions as base


def _load_sample(settings: Any, db: Any, *, user: Any, workspace: Any, asset_id: str, required: list[str]) -> tuple[Any, pd.DataFrame]:
    asset, frame = base._load_asset_frame(settings, db, user=user, workspace=workspace, asset_id=asset_id)
    sample = base._flat_frame(frame, numeric_columns=required, keep_columns=[])
    return asset, sample


def _posterior_table(idata: az.InferenceData, variables: list[str]) -> list[dict[str, Any]]:
    summary = az.summary(idata, var_names=variables, round_to=4).reset_index().rename(columns={"index": "term"})
    return base._serialize_rows(summary)


def _trace_asset(settings: Any, db: Any, *, user: Any, workspace: Any, source_asset: Any, idata: az.InferenceData, var_names: list[str], slug: str, title: str, summary: str) -> dict[str, Any]:
    az.plot_trace(idata, var_names=var_names)
    fig = plt.gcf()
    fig.tight_layout()
    return base._candidate_figure(settings, db, user=user, workspace=workspace, source_asset=source_asset, figure=fig, filename_slug=slug, title=title, summary=summary)


def _line_figure(settings: Any, db: Any, *, user: Any, workspace: Any, source_asset: Any, frame: pd.DataFrame, x: str, y_cols: list[str], slug: str, title: str, summary: str) -> dict[str, Any]:
    fig, ax = base._ts_figure(title)
    for col in y_cols:
        ax.plot(frame[x], frame[col], label=col)
    ax.legend()
    fig.tight_layout()
    return base._candidate_figure(settings, db, user=user, workspace=workspace, source_asset=source_asset, figure=fig, filename_slug=slug, title=title, summary=summary)


def _bayes_settings(kwargs: dict[str, Any]) -> tuple[int, int, int]:
    draws = int(base._spec_option(kwargs, "draws", 150))
    tune = int(base._spec_option(kwargs, "tune", 150))
    chains = int(base._spec_option(kwargs, "chains", 2))
    return draws, tune, chains


def _fit_variational(model: pm.Model, *, draws: int, tune: int, seed: int) -> az.InferenceData:
    with model:
        approx = pm.fit(
            n=max(500, tune * 20),
            method="advi",
            progressbar=False,
            random_seed=seed,
        )
        return approx.sample(draws=max(100, draws * 10), random_seed=seed, return_inferencedata=True)


def run_bayesian_linear_regression_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    regressors = list(kwargs.get("independents") or kwargs.get("controls") or [])
    if not regressors:
        raise ValueError("Bayesian linear regression requires at least one regressor.")
    asset, sample = _load_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], required=[dependent, *regressors])
    X = sample[regressors].to_numpy(dtype=float)
    y = sample[dependent].to_numpy(dtype=float)
    draws, tune, chains = _bayes_settings(kwargs)
    with pm.Model() as model:
        beta = pm.Normal("beta", 0.0, 1.0, shape=len(regressors))
        alpha = pm.Normal("alpha", 0.0, 5.0)
        sigma = pm.HalfNormal("sigma", 1.0)
        mu = alpha + pm.math.dot(X, beta)
        pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
        idata = _fit_variational(model, draws=draws, tune=tune, seed=42)
        post_pred = pm.sample_posterior_predictive(idata, var_names=["obs"], progressbar=False, random_seed=42)
    sample["_posterior_mean"] = np.asarray(post_pred.posterior_predictive["obs"]).mean(axis=(0, 1))
    trace_asset = _trace_asset(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, idata=idata, var_names=["alpha", "beta", "sigma"], slug="bayes_linear_trace", title="Bayesian linear trace", summary="Trace plots for the Bayesian linear regression.")
    pred_asset = _line_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, frame=sample.reset_index(), x="index", y_cols=[dependent, "_posterior_mean"], slug="bayes_linear_predictive", title="Posterior predictive fit", summary="Observed series against posterior predictive mean.")
    return base._nonregression_payload(
        model_type="bayesian_linear_regression",
        model_label="Bayesian Linear Regression",
        engine="pymc",
        asset=asset,
        sample=sample.reset_index(drop=True),
        narrative_lines=["Bayesian linear regression estimated with PyMC using weakly informative priors."],
        tables={
            "posterior_summary_table": _posterior_table(idata, ["alpha", "beta", "sigma"]),
            "predictor_contribution_table": [{"term": reg, "posterior_mean": float(az.summary(idata, var_names=['beta']).loc[f'beta[{idx}]', 'mean'])} for idx, reg in enumerate(regressors)],
        },
        figures=[trace_asset, pred_asset],
        specification={"dependent": dependent, "regressors": regressors, "draws": draws, "tune": tune, "chains": chains},
        audit_trail={"derived_columns": ["_posterior_mean"], "filters": []},
    )


def run_bayesian_panel_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    regressors = list(kwargs.get("independents") or kwargs.get("controls") or [])
    entity_column = kwargs.get("entity_column") or "firm_id"
    time_column = kwargs.get("time_column") or "month_index"
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    required = [dependent, entity_column, time_column, *regressors]
    base._ensure_columns(frame, required)
    sample = frame[required].copy()
    for column in [dependent, *regressors]:
        sample[column] = base._pc()._coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    entities, entity_idx = np.unique(sample[entity_column].astype(str), return_inverse=True)
    X = sample[regressors].to_numpy(dtype=float)
    y = sample[dependent].to_numpy(dtype=float)
    draws, tune, chains = _bayes_settings(kwargs)
    with pm.Model() as model:
        alpha = pm.Normal("alpha", 0.0, 3.0)
        sigma_entity = pm.HalfNormal("sigma_entity", 1.0)
        entity_effect = pm.Normal("entity_effect", 0.0, sigma_entity, shape=len(entities))
        beta = pm.Normal("beta", 0.0, 1.0, shape=len(regressors))
        sigma = pm.HalfNormal("sigma", 1.0)
        mu = alpha + entity_effect[entity_idx] + pm.math.dot(X, beta)
        pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
        idata = _fit_variational(model, draws=draws, tune=tune, seed=43)
        post_pred = pm.sample_posterior_predictive(idata, var_names=["obs"], progressbar=False, random_seed=43)
    sample["_posterior_mean"] = np.asarray(post_pred.posterior_predictive["obs"]).mean(axis=(0, 1))
    grouped = sample.groupby(entity_column, as_index=False)[[dependent, "_posterior_mean"]].mean()
    trace_asset = _trace_asset(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, idata=idata, var_names=["alpha", "beta", "sigma", "sigma_entity"], slug="bayes_panel_trace", title="Bayesian panel trace", summary="Trace plots for the Bayesian panel model.")
    panel_asset = _line_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, frame=grouped.reset_index(), x="index", y_cols=[dependent, "_posterior_mean"], slug="bayes_panel_predictive", title="Posterior predictive panel fit", summary="Observed group means against posterior predictive group means.")
    return base._nonregression_payload(
        model_type="bayesian_panel",
        model_label="Bayesian Panel",
        engine="pymc",
        asset=asset,
        sample=sample.reset_index(drop=True),
        narrative_lines=["Hierarchical Bayesian panel regression with random unit effects."],
        tables={
            "posterior_coefficient_table": _posterior_table(idata, ["alpha", "beta", "sigma"]),
            "group_variance_table": _posterior_table(idata, ["sigma_entity"]),
        },
        figures=[trace_asset, panel_asset],
        specification={"dependent": dependent, "regressors": regressors, "entity_column": entity_column, "time_column": time_column},
        audit_trail={"derived_columns": ["_posterior_mean"], "filters": []},
    )


def run_bayesian_did_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    treated_col = kwargs.get("treatment_column") or "treated"
    post_col = kwargs.get("post_column") or "post"
    controls = list(kwargs.get("controls") or [])
    asset, sample = _load_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], required=[dependent, treated_col, post_col, *controls])
    sample[treated_col] = sample[treated_col].round().clip(0, 1)
    sample[post_col] = sample[post_col].round().clip(0, 1)
    sample["did_term"] = sample[treated_col] * sample[post_col]
    regressors = [treated_col, post_col, "did_term", *controls]
    X = sample[regressors].to_numpy(dtype=float)
    y = sample[dependent].to_numpy(dtype=float)
    draws, tune, chains = _bayes_settings(kwargs)
    with pm.Model() as model:
        beta = pm.Normal("beta", 0.0, 1.0, shape=len(regressors))
        alpha = pm.Normal("alpha", 0.0, 5.0)
        sigma = pm.HalfNormal("sigma", 1.0)
        mu = alpha + pm.math.dot(X, beta)
        pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
        idata = _fit_variational(model, draws=draws, tune=tune, seed=44)
    effect_summary = az.summary(idata, var_names=["beta"]).reset_index()
    did_row = effect_summary.iloc[2].to_dict() if len(effect_summary) >= 3 else {}
    cell_means = (
        sample.groupby([treated_col, post_col], as_index=False)[dependent]
        .mean()
        .rename(columns={dependent: "mean_outcome"})
    )
    trace_asset = _trace_asset(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, idata=idata, var_names=["alpha", "beta", "sigma"], slug="bayes_did_trace", title="Bayesian DID trace", summary="Trace plots for the Bayesian DID model.")
    fig, ax = base._ts_figure("Posterior DID effect")
    ax.bar(["did_term"], [float(did_row.get("mean", 0.0))], color="#2563eb")
    fig.tight_layout()
    effect_asset = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig, filename_slug="bayes_did_effect", title="Posterior DID effect", summary="Posterior mean of the treatment interaction term.")
    return base._nonregression_payload(
        model_type="bayesian_did",
        model_label="Bayesian DID",
        engine="pymc",
        asset=asset,
        sample=sample.reset_index(drop=True),
        narrative_lines=["Bayesian difference-in-differences model estimated with a posterior on the treatment interaction."],
        tables={
            "posterior_treatment_effect_table": base._serialize_rows(effect_summary),
            "cell_mean_posterior_table": base._serialize_rows(cell_means),
        },
        figures=[trace_asset, effect_asset],
        specification={"dependent": dependent, "treated_column": treated_col, "post_column": post_col, "controls": controls},
        audit_trail={"derived_columns": ["did_term"], "filters": []},
    )


def run_bayesian_its_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    time_column = kwargs.get("time_column") or "date"
    asset, frame = base._load_asset_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    base._ensure_columns(frame, [dependent, time_column])
    sample = frame[[dependent, time_column]].copy()
    sample[dependent] = base._pc()._coerce_numeric_series(sample[dependent])
    sample = base._pc()._sort_sample_by_time(sample, time_column).dropna().copy()
    sample["_time_index"] = np.arange(len(sample))
    cutoff = int(base._spec_option(kwargs, "treatment_index", len(sample) // 2))
    sample["post_treatment"] = (sample["_time_index"] >= cutoff).astype(int)
    sample["time_after_treatment"] = np.where(sample["post_treatment"] == 1, sample["_time_index"] - cutoff, 0)
    X = sample[["_time_index", "post_treatment", "time_after_treatment"]].to_numpy(dtype=float)
    y = sample[dependent].to_numpy(dtype=float)
    draws, tune, chains = _bayes_settings(kwargs)
    with pm.Model() as model:
        beta = pm.Normal("beta", 0.0, 1.0, shape=X.shape[1])
        alpha = pm.Normal("alpha", 0.0, 5.0)
        sigma = pm.HalfNormal("sigma", 1.0)
        mu = alpha + pm.math.dot(X, beta)
        pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
        idata = _fit_variational(model, draws=draws, tune=tune, seed=45)
        post_pred = pm.sample_posterior_predictive(idata, var_names=["obs"], progressbar=False, random_seed=45)
    sample["_posterior_mean"] = np.asarray(post_pred.posterior_predictive["obs"]).mean(axis=(0, 1))
    trace_asset = _trace_asset(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, idata=idata, var_names=["alpha", "beta", "sigma"], slug="bayes_its_trace", title="Bayesian ITS trace", summary="Trace plots for the Bayesian interrupted time-series model.")
    pred_asset = _line_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, frame=sample.reset_index(), x="_time_index", y_cols=[dependent, "_posterior_mean"], slug="bayes_its_predictive", title="Bayesian ITS path", summary="Observed and posterior-predictive interrupted time-series path.")
    return base._nonregression_payload(
        model_type="bayesian_its",
        model_label="Bayesian ITS",
        engine="pymc",
        asset=asset,
        sample=sample.reset_index(drop=True),
        narrative_lines=["Bayesian interrupted time-series with posterior level and slope changes."],
        tables={
            "posterior_intervention_table": _posterior_table(idata, ["alpha", "beta", "sigma"]),
            "slope_change_posterior_table": [{"cutoff_index": cutoff, "post_periods": int(sample["post_treatment"].sum())}],
        },
        figures=[trace_asset, pred_asset],
        specification={"dependent": dependent, "time_column": time_column, "treatment_index": cutoff},
        audit_trail={"derived_columns": ["_time_index", "post_treatment", "time_after_treatment", "_posterior_mean"], "filters": []},
    )
