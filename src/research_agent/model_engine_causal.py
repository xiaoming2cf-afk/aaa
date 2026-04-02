from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from linearmodels import IV2SLS as LMIV2SLS
from sklearn.linear_model import LogisticRegression

import research_agent.model_engine_extensions as base


def _load_frame(settings: Any, db: Any, *, user: Any, workspace: Any, asset_id: str) -> tuple[Any, pd.DataFrame]:
    asset, frame = base._load_asset_frame(settings, db, user=user, workspace=workspace, asset_id=asset_id)
    return asset, frame


def _time_order(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if parsed.notna().sum():
        return pd.Series(parsed.rank(method="dense").astype(int), index=values.index)
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum():
        return pd.Series(numeric.rank(method="dense").astype(int), index=values.index)
    return pd.Series(pd.factorize(values.astype(str))[0] + 1, index=values.index)


def _line_plot(settings: Any, db: Any, *, user: Any, workspace: Any, source_asset: Any, frame: pd.DataFrame, x: str, y_cols: list[str], title: str, slug: str, summary: str) -> dict[str, Any]:
    fig, ax = base._ts_figure(title)
    for col in y_cols:
        ax.plot(frame[x], frame[col], label=col)
    ax.legend()
    fig.tight_layout()
    return base._candidate_figure(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=source_asset,
        figure=fig,
        filename_slug=slug,
        title=title,
        summary=summary,
    )


def run_candidate_did_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    treated_col = kwargs.get("treatment_column") or "treated"
    post_col = kwargs.get("post_column") or "post"
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    asset, sample = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    required = [dependent, treated_col, post_col, *controls]
    base._ensure_columns(sample, required)
    sample = sample[required].copy()
    for col in [dependent, *controls]:
        sample[col] = base._pc()._coerce_numeric_series(sample[col])
    sample[treated_col] = pd.to_numeric(sample[treated_col], errors="coerce").fillna(0).astype(int)
    sample[post_col] = pd.to_numeric(sample[post_col], errors="coerce").fillna(0).astype(int)
    sample["did_interaction"] = sample[treated_col] * sample[post_col]
    regressors = [treated_col, post_col, "did_interaction", *controls]
    result = smf.ols(f"{dependent} ~ 1 + {' + '.join(regressors)}", data=sample.dropna()).fit(cov_type="HC1")
    cell_means = (
        sample.groupby([treated_col, post_col], as_index=False)[dependent]
        .mean()
        .rename(columns={dependent: "mean_outcome"})
    )
    payload = base._regression_payload(
        model_type="did",
        model_label="Difference-in-Differences",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample.dropna(),
        result=result,
        narrative_lines=["Candidate DID path benchmarked against baseline implementation."],
        tables={"cell_mean_table": base._serialize_rows(cell_means)},
        figures=[],
        audit_trail={"derived_columns": ["did_interaction"], "filters": []},
        extra_specification={"treated_column": treated_col, "post_column": post_col},
    )
    payload["cell_means"] = [
        {
            "treatment": int(row[treated_col]),
            "post": int(row[post_col]),
            "mean": base._safe_float(row["mean_outcome"]),
            "count": int(sample.loc[(sample[treated_col] == row[treated_col]) & (sample[post_col] == row[post_col])].shape[0]),
        }
        for _, row in cell_means.iterrows()
    ]
    return payload


def run_candidate_event_study_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    payload = run_staggered_did_analysis(settings, db, **kwargs)
    payload["model_type"] = "event_study"
    payload["model_label"] = "Event Study"
    tables = dict(payload.get("tables") or {})
    dynamic_rows = tables.get("dynamic_effect_table") or []
    window_rows = tables.get("event_window_audit") or []
    tables["event_study_table"] = dynamic_rows
    if window_rows:
        tables["event_study_window"] = window_rows
    payload["tables"] = tables
    payload["paper_output_contract"] = {
        "primary_tables": ["event_study_table", "cohort_time_table"],
        "robustness_tables": ["event_study_window"],
        "figure_count": len(payload.get("figures") or []),
    }
    return payload


def run_candidate_rdd_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    running_column = kwargs.get("running_column") or "running_score"
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    cutoff = float(base._spec_option(kwargs, "rdd_cutoff", kwargs.get("cutoff", 0.0)))
    bandwidth = float(base._spec_option(kwargs, "rdd_bandwidth", kwargs.get("bandwidth", 1.0)))
    order = int(base._spec_option(kwargs, "rdd_polynomial_order", 1))
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    sample = base._flat_frame(frame, numeric_columns=[dependent, running_column, *controls], keep_columns=[])
    sample = sample.loc[(sample[running_column] >= cutoff - bandwidth) & (sample[running_column] <= cutoff + bandwidth)].copy()
    sample["running_centered"] = sample[running_column] - cutoff
    sample["treated_side"] = (sample[running_column] >= cutoff).astype(int)
    poly_terms = ["treated_side", "running_centered"]
    if order >= 2:
        sample["running_sq"] = sample["running_centered"] ** 2
        poly_terms.append("running_sq")
    sample["interaction_term"] = sample["treated_side"] * sample["running_centered"]
    regressors = [*poly_terms, "interaction_term", *controls]
    result = smf.ols(f"{dependent} ~ 1 + {' + '.join(regressors)}", data=sample).fit(cov_type="HC1")
    sample = sample.sort_values(running_column)
    sample["_fitted"] = result.predict(sample)
    figure = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=sample[[running_column, dependent, "_fitted"]],
        x=running_column,
        y_cols=[dependent, "_fitted"],
        title="Candidate RDD fit",
        slug="candidate_rdd_fit",
        summary="Observed and fitted values around the discontinuity cutoff.",
    )
    payload = base._regression_payload(
        model_type="rdd",
        model_label="Regression Discontinuity",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=result,
        narrative_lines=["Candidate RDD benchmarked with local polynomial terms around the cutoff."],
        tables={"bandwidth_sensitivity": [{"cutoff": cutoff, "bandwidth": bandwidth, "polynomial_order": order, "sample_size": int(len(sample))}]},
        figures=[figure],
        audit_trail={"derived_columns": ["running_centered", "treated_side", "interaction_term"], "filters": ["Sample restricted to chosen bandwidth."]},
        extra_specification={"running_column": running_column},
    )
    payload["paper_output_contract"] = {
        "primary_tables": ["bandwidth_sensitivity"],
        "robustness_tables": [],
        "figure_count": len(payload.get("figures") or []),
    }
    return payload


def run_staggered_did_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    entity_column = kwargs.get("entity_column") or "firm_id"
    time_column = kwargs.get("time_column") or "month_index"
    treated_column = kwargs.get("treatment_column") or "treated"
    treatment_time_column = str(base._spec_option(kwargs, "treatment_time_column", "treatment_time"))
    lead_window = int(base._spec_option(kwargs, "lead_window", 4))
    lag_window = int(base._spec_option(kwargs, "lag_window", 4))
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    required = [dependent, entity_column, time_column, treated_column, treatment_time_column, *controls]
    base._ensure_columns(frame, required)
    sample = frame[required].copy()
    sample[dependent] = base._pc()._coerce_numeric_series(sample[dependent])
    for column in controls:
        sample[column] = base._pc()._coerce_numeric_series(sample[column])
    sample[treated_column] = pd.to_numeric(sample[treated_column], errors="coerce").fillna(0).astype(int)
    sample["_time_index"] = _time_order(sample[time_column])
    sample[treatment_time_column] = pd.to_numeric(sample[treatment_time_column], errors="coerce")
    sample["_event_time"] = sample["_time_index"] - sample[treatment_time_column]
    sample = sample.dropna(subset=[dependent]).copy()
    event_terms: list[str] = []
    event_rows: list[dict[str, Any]] = []
    for event_time in range(-lead_window, lag_window + 1):
        if event_time == -1:
            continue
        column = f"event_{event_time:+d}".replace("+", "p").replace("-", "m")
        sample[column] = ((sample[treated_column] == 1) & (sample["_event_time"] == event_time)).astype(int)
        event_terms.append(column)
    regressors = [*event_terms, *controls]
    formula = f"{dependent} ~ 1 + {' + '.join(regressors)} + C({entity_column}) + C({time_column})"
    result = smf.ols(formula, data=sample).fit(cov_type="HC1")
    for event_time in range(-lead_window, lag_window + 1):
        if event_time == -1:
            continue
        term = f"event_{event_time:+d}".replace("+", "p").replace("-", "m")
        event_rows.append(
            {
                "event_time": event_time,
                "coefficient": base._safe_float(result.params.get(term)),
                "std_error": base._safe_float(result.bse.get(term)),
                "pvalue": base._safe_float(result.pvalues.get(term)),
            }
        )
    event_frame = pd.DataFrame(event_rows)
    cohort_time = (
        sample.loc[sample[treated_column] == 1, [treatment_time_column, "_event_time", dependent]]
        .groupby([treatment_time_column, "_event_time"], as_index=False)[dependent]
        .mean()
        .rename(columns={dependent: "mean_outcome"})
    )
    figure_frame = event_frame.copy()
    fig, ax = base._ts_figure("Staggered DID dynamic effects")
    ax.axhline(0.0, color="#94a3b8", linewidth=1.0, linestyle="--")
    ax.plot(figure_frame["event_time"], figure_frame["coefficient"], marker="o", color="#2563eb")
    ax.fill_between(
        figure_frame["event_time"],
        figure_frame["coefficient"] - 1.96 * figure_frame["std_error"].fillna(0.0),
        figure_frame["coefficient"] + 1.96 * figure_frame["std_error"].fillna(0.0),
        color="#93c5fd",
        alpha=0.35,
    )
    fig.tight_layout()
    fig_asset = base._candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=fig,
        filename_slug="staggered_did_dynamic",
        title="Staggered DID dynamic effects",
        summary="Dynamic treatment effects by event time with 95% confidence bands.",
    )
    return base._regression_payload(
        model_type="staggered_did",
        model_label="Staggered DID",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, *regressors]].dropna(),
        result=result,
        narrative_lines=[
            "Staggered DID estimated with cohort-specific event-time indicators.",
            f"Event window: [{-lead_window}, {lag_window}] omitting -1.",
        ],
        tables={
            "dynamic_effect_table": event_rows,
            "cohort_time_table": base._serialize_rows(cohort_time),
        },
        figures=[fig_asset],
        robustness_tables={"event_window_audit": [{"lead_window": lead_window, "lag_window": lag_window}]},
        audit_trail={"derived_columns": ["_event_time", *event_terms], "filters": ["Rows without dependent variable are excluded."]},
        extra_specification={
            "entity_column": entity_column,
            "time_column": time_column,
            "treated_column": treated_column,
            "treatment_time_column": treatment_time_column,
        },
    )


def run_interrupted_time_series_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    time_column = kwargs.get("time_column") or "date"
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    intervention_at = base._spec_option(kwargs, "treatment_time") or base._spec_option(kwargs, "intervention_at")
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    required = [dependent, time_column, *controls]
    base._ensure_columns(frame, required)
    sample = frame[required].copy()
    sample[dependent] = base._pc()._coerce_numeric_series(sample[dependent])
    for column in controls:
        sample[column] = base._pc()._coerce_numeric_series(sample[column])
    sample = base._pc()._sort_sample_by_time(sample, time_column).dropna().copy()
    sample["_time_index"] = np.arange(len(sample))
    if intervention_at:
        intervention_time = pd.to_datetime(intervention_at, errors="coerce")
        parsed = pd.to_datetime(sample[time_column], errors="coerce")
        if pd.notna(intervention_time) and parsed.notna().sum():
            cutoff_index = int(np.searchsorted(parsed.sort_values(), intervention_time, side="left"))
        else:
            cutoff_index = int(float(intervention_at))
    else:
        cutoff_index = len(sample) // 2
    sample["post_treatment"] = (sample["_time_index"] >= cutoff_index).astype(int)
    sample["time_after_treatment"] = np.where(sample["post_treatment"] == 1, sample["_time_index"] - cutoff_index, 0)
    regressors = ["_time_index", "post_treatment", "time_after_treatment", *controls]
    result = smf.ols(f"{dependent} ~ 1 + {' + '.join(regressors)}", data=sample).fit(cov_type="HC1")
    sample["_fitted"] = result.predict(sample)
    summary_rows = [
        {
            "segment": "pre",
            "mean": base._safe_float(sample.loc[sample["post_treatment"] == 0, dependent].mean()),
            "slope": base._safe_float(result.params.get("_time_index")),
        },
        {
            "segment": "post",
            "mean": base._safe_float(sample.loc[sample["post_treatment"] == 1, dependent].mean()),
            "slope": base._safe_float(result.params.get("_time_index", 0.0) + result.params.get("time_after_treatment", 0.0)),
        },
    ]
    fig_asset = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=sample[["_time_index", dependent, "_fitted"]],
        x="_time_index",
        y_cols=[dependent, "_fitted"],
        title="Interrupted time-series observed vs fitted",
        slug="its_observed_fitted",
        summary="Observed series and fitted interrupted time-series path.",
    )
    return base._regression_payload(
        model_type="interrupted_time_series",
        model_label="Interrupted Time Series",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, *regressors]].dropna(),
        result=result,
        narrative_lines=["Interrupted time-series estimated with level and slope changes after intervention."],
        tables={"pre_post_summary": summary_rows},
        figures=[fig_asset],
        robustness_tables={"break_audit": [{"intervention_index": cutoff_index}]},
        audit_trail={"derived_columns": ["_time_index", "post_treatment", "time_after_treatment"], "filters": []},
        extra_specification={"time_column": time_column},
    )


def run_regression_kink_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    running_column = kwargs.get("running_column") or "running_score"
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    kink_point = float(base._spec_option(kwargs, "kink_point", 0.0))
    bandwidth = float(base._spec_option(kwargs, "bandwidth", 1.0))
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    required = [dependent, running_column, *controls]
    sample = base._flat_frame(frame, numeric_columns=[dependent, running_column, *controls], keep_columns=[])
    sample = sample.loc[(sample[running_column] >= kink_point - bandwidth) & (sample[running_column] <= kink_point + bandwidth)].copy()
    sample["running_centered"] = sample[running_column] - kink_point
    sample["kink_term"] = sample["running_centered"].clip(lower=0.0)
    regressors = ["running_centered", "kink_term", *controls]
    result = smf.ols(f"{dependent} ~ 1 + {' + '.join(regressors)}", data=sample).fit(cov_type="HC1")
    sample = sample.sort_values(running_column)
    sample["_fitted"] = result.predict(sample)
    fig_asset = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=sample[[running_column, dependent, "_fitted"]],
        x=running_column,
        y_cols=[dependent, "_fitted"],
        title="Regression kink fit",
        slug="regression_kink_fit",
        summary="Observed outcomes and fitted piecewise-linear kink regression.",
    )
    bandwidth_rows = [{"bandwidth": bandwidth, "kink_point": kink_point, "sample_size": int(len(sample))}]
    return base._regression_payload(
        model_type="regression_kink",
        model_label="Regression Kink",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, *regressors]].dropna(),
        result=result,
        narrative_lines=["Regression kink estimated with a slope break at the specified kink point."],
        tables={"bandwidth_audit": bandwidth_rows},
        figures=[fig_asset],
        robustness_tables={"kink_design_table": bandwidth_rows},
        audit_trail={"derived_columns": ["running_centered", "kink_term"], "filters": [f"Bandwidth restriction: ±{bandwidth}."]},
        extra_specification={"running_column": running_column, "kink_point": kink_point},
    )


def run_instrumental_causal_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    endogenous = kwargs.get("endogenous_column") or kwargs.get("treatment_column")
    instruments = list(kwargs.get("instrument_columns") or [])
    controls = list(kwargs.get("controls") or kwargs.get("independents") or [])
    if not endogenous or not instruments:
        raise ValueError("Instrumental causal requires an endogenous/treatment column and at least one instrument column.")
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    sample = base._flat_frame(frame, numeric_columns=[dependent, endogenous, *controls, *instruments], keep_columns=[])
    exog = sample[controls] if controls else pd.DataFrame(index=sample.index)
    result = LMIV2SLS(sample[dependent], sm.add_constant(exog, has_constant="add"), sample[[endogenous]], sample[instruments]).fit(cov_type="robust")
    first_stage = sm.OLS(sample[endogenous], sm.add_constant(sample[[*controls, *instruments]], has_constant="add")).fit(cov_type="HC1")
    sample["_fitted_treatment"] = first_stage.predict(sm.add_constant(sample[[*controls, *instruments]], has_constant="add"))
    fig_asset = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=sample.reset_index()[[endogenous, "_fitted_treatment"]].reset_index(),
        x="index",
        y_cols=[endogenous, "_fitted_treatment"],
        title="Observed vs fitted treatment",
        slug="causal_iv_first_stage",
        summary="First-stage fit for the treatment variable.",
    )
    return base._regression_payload(
        model_type="instrumental_causal",
        model_label="Instrumental Variable Causal",
        engine="causalpy",
        asset=asset,
        dependent=dependent,
        regressors=[endogenous, *controls],
        sample=sample[[dependent, endogenous, *controls, *instruments]].dropna(),
        result=result,
        narrative_lines=["Instrumental-variable causal effect estimated with linearmodels IV2SLS."],
        tables={
            "first_stage_table": base._series_to_table(first_stage.params, value_name="coefficient"),
            "first_stage_diagnostics": [{"rsquared": base._safe_float(first_stage.rsquared), "f_statistic": base._safe_float(getattr(first_stage.fvalue, 'item', lambda: first_stage.fvalue)() if hasattr(first_stage.fvalue, 'item') else first_stage.fvalue)}],
        },
        figures=[fig_asset],
        audit_trail={"derived_columns": ["_fitted_treatment"], "filters": []},
        extra_specification={"endogenous_column": endogenous, "instrument_columns": instruments},
    )


def run_inverse_propensity_weighting_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    outcome = kwargs["dependent"]
    treatment = kwargs.get("treatment_column") or "treated"
    covariates = list(kwargs.get("controls") or kwargs.get("independents") or [])
    if not covariates:
        raise ValueError("Inverse propensity weighting requires covariates in controls or independents.")
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    sample = base._flat_frame(frame, numeric_columns=[outcome, treatment, *covariates], keep_columns=[])
    sample[treatment] = sample[treatment].round().clip(0, 1).astype(int)
    model = LogisticRegression(max_iter=500)
    model.fit(sample[covariates], sample[treatment])
    propensity = model.predict_proba(sample[covariates])[:, 1]
    sample["_propensity"] = np.clip(propensity, 1e-4, 1 - 1e-4)
    sample["_weight"] = np.where(sample[treatment] == 1, 1.0 / sample["_propensity"], 1.0 / (1.0 - sample["_propensity"]))
    treated_mean = np.average(sample.loc[sample[treatment] == 1, outcome], weights=sample.loc[sample[treatment] == 1, "_weight"])
    control_mean = np.average(sample.loc[sample[treatment] == 0, outcome], weights=sample.loc[sample[treatment] == 0, "_weight"])
    ate = float(treated_mean - control_mean)
    before_rows = []
    after_rows = []
    for column in covariates:
        t = sample.loc[sample[treatment] == 1, column]
        c = sample.loc[sample[treatment] == 0, column]
        pooled = np.sqrt((t.var(ddof=1) + c.var(ddof=1)) / 2.0) or 1.0
        before_rows.append({"covariate": column, "smd": float((t.mean() - c.mean()) / pooled)})
        wt = np.average(t, weights=sample.loc[sample[treatment] == 1, "_weight"])
        wc = np.average(c, weights=sample.loc[sample[treatment] == 0, "_weight"])
        after_rows.append({"covariate": column, "weighted_mean_diff": float(wt - wc)})
    fig, ax = base._ts_figure("Propensity overlap")
    ax.hist(sample.loc[sample[treatment] == 1, "_propensity"], bins=20, alpha=0.6, label="treated")
    ax.hist(sample.loc[sample[treatment] == 0, "_propensity"], bins=20, alpha=0.6, label="control")
    ax.legend()
    fig.tight_layout()
    fig_asset = base._candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=fig,
        filename_slug="ipw_overlap",
        title="Propensity score overlap",
        summary="Propensity score overlap by treatment status.",
    )
    return base._nonregression_payload(
        model_type="inverse_propensity_weighting",
        model_label="Inverse Propensity Weighting",
        engine="causalpy",
        asset=asset,
        sample=sample.reset_index(drop=True),
        narrative_lines=["Inverse propensity weighting estimated with a logistic propensity model."],
        tables={
            "treatment_effect_table": [{"weighted_ate": ate, "treated_mean": float(treated_mean), "control_mean": float(control_mean)}],
            "propensity_summary_table": [{"min_propensity": float(sample["_propensity"].min()), "max_propensity": float(sample["_propensity"].max()), "mean_weight": float(sample["_weight"].mean())}],
            "balance_before_table": before_rows,
            "balance_after_table": after_rows,
        },
        figures=[fig_asset],
        specification={"outcome_variable": outcome, "treatment_column": treatment, "covariates": covariates},
        audit_trail={"derived_columns": ["_propensity", "_weight"], "filters": []},
    )


def run_synthetic_control_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    entity_column = kwargs.get("entity_column") or "firm_id"
    time_column = kwargs.get("time_column") or "month_index"
    treated_unit = str(base._spec_option(kwargs, "treated_unit", ""))
    control_units = list(base._spec_option(kwargs, "control_units", []))
    treatment_time = base._spec_option(kwargs, "treatment_time")
    asset, frame = _load_frame(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"])
    base._ensure_columns(frame, [dependent, entity_column, time_column])
    sample = frame[[dependent, entity_column, time_column]].copy()
    sample[dependent] = base._pc()._coerce_numeric_series(sample[dependent])
    sample["_time"] = _time_order(sample[time_column])
    sample = sample.dropna().copy()
    if not treated_unit:
        treated_candidates = sample.groupby(entity_column)[dependent].count().sort_values(ascending=False).index.tolist()
        treated_unit = str(treated_candidates[0])
    if not control_units:
        control_units = [str(unit) for unit in sample[entity_column].astype(str).unique().tolist() if str(unit) != treated_unit][: min(6, sample[entity_column].nunique() - 1)]
    if not control_units:
        raise ValueError("Synthetic control requires at least one donor unit.")
    if treatment_time is None:
        treatment_time = int(sample["_time"].max() * 0.6)
    treatment_time = int(float(treatment_time))
    wide = sample.pivot_table(index="_time", columns=entity_column, values=dependent)
    if treated_unit not in wide.columns:
        raise ValueError("Treated unit not found in panel.")
    donor_cols = [col for col in control_units if col in wide.columns and col != treated_unit]
    if not donor_cols:
        raise ValueError("No valid donor units found in the panel.")
    pre = wide.loc[wide.index < treatment_time]
    post = wide.loc[wide.index >= treatment_time]
    y_pre = pre[treated_unit].to_numpy(dtype=float)
    x_pre = pre[donor_cols].to_numpy(dtype=float)
    weights, *_ = np.linalg.lstsq(x_pre, y_pre, rcond=None)
    weights = np.clip(weights, 0, None)
    if weights.sum() == 0:
        weights = np.repeat(1 / len(donor_cols), len(donor_cols))
    else:
        weights = weights / weights.sum()
    synthetic = wide[donor_cols].to_numpy(dtype=float) @ weights
    synth_frame = pd.DataFrame({"time": wide.index, "observed": wide[treated_unit].to_numpy(dtype=float), "synthetic": synthetic})
    synth_frame["gap"] = synth_frame["observed"] - synth_frame["synthetic"]
    fit_rows = [
        {"period": "pre", "rmse": float(np.sqrt(np.mean(np.square(pre[treated_unit].to_numpy(dtype=float) - (pre[donor_cols].to_numpy(dtype=float) @ weights)))))},
        {"period": "post", "rmse": float(np.sqrt(np.mean(np.square(post[treated_unit].to_numpy(dtype=float) - (post[donor_cols].to_numpy(dtype=float) @ weights)))))},
    ]
    path_fig = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=synth_frame,
        x="time",
        y_cols=["observed", "synthetic"],
        title="Observed vs synthetic path",
        slug="synthetic_control_path",
        summary="Observed treated path against synthetic control counterfactual.",
    )
    gap_fig = _line_plot(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        frame=synth_frame[["time", "gap"]],
        x="time",
        y_cols=["gap"],
        title="Synthetic control gap",
        slug="synthetic_control_gap",
        summary="Gap between observed treated outcome and synthetic control path.",
    )
    return base._nonregression_payload(
        model_type="synthetic_control",
        model_label="Synthetic Control",
        engine="causalpy",
        asset=asset,
        sample=synth_frame,
        narrative_lines=["Synthetic control weights estimated from donor units using pre-treatment fit."],
        tables={
            "fit_table": fit_rows,
            "donor_weight_table": [{"donor_unit": donor, "weight": float(weight)} for donor, weight in zip(donor_cols, weights)],
            "path_table": base._serialize_rows(synth_frame),
        },
        figures=[path_fig, gap_fig],
        specification={"treated_unit": treated_unit, "control_units": donor_cols, "treatment_time": treatment_time},
        audit_trail={"derived_columns": ["synthetic", "gap"], "filters": []},
    )
