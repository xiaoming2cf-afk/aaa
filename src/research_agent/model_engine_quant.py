from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score

import research_agent.model_engine_extensions as base


def _require_lightgbm() -> Any:
    try:
        import lightgbm as lgb
    except Exception as exc:  # pragma: no cover - optional dependency resolution
        raise ImportError(
            "Quant LightGBM requires the optional dependency 'lightgbm'. "
            "Install the project with the 'quant-tree' extra or add lightgbm to the runtime environment."
        ) from exc
    return lgb


def _require_catboost() -> Any:
    try:
        from catboost import CatBoostRegressor
    except Exception as exc:  # pragma: no cover - optional dependency resolution
        raise ImportError(
            "Quant CatBoost requires the optional dependency 'catboost'. "
            "Install the project with the 'quant-tree' extra or add catboost to the runtime environment."
        ) from exc
    return CatBoostRegressor


def _load_quant_sample(settings: Any, db: Any, *, user: Any, workspace: Any, asset_id: str, dependent: str, feature_columns: list[str], time_column: str) -> tuple[Any, pd.DataFrame]:
    asset, frame = base._load_asset_frame(settings, db, user=user, workspace=workspace, asset_id=asset_id)
    required = [dependent, time_column, *feature_columns]
    base._ensure_columns(frame, required)
    sample = frame[required].copy()
    sample = base._pc()._sort_sample_by_time(sample, time_column)
    for column in [dependent, *feature_columns]:
        sample[column] = base._pc()._coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if len(sample) < 30:
        raise ValueError("Quant research methods require at least 30 complete observations.")
    return asset, sample


def _split_sample(sample: pd.DataFrame, *, time_column: str, split_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    sample = sample.reset_index(drop=True).copy()
    split_idx = max(12, min(len(sample) - 6, int(len(sample) * split_ratio)))
    return sample.iloc[:split_idx].copy(), sample.iloc[split_idx:].copy()


def _ic_stats(actual: pd.Series, predicted: pd.Series) -> tuple[float, float]:
    if len(actual) < 3:
        return 0.0, 0.0
    ic = float(pd.Series(actual).corr(pd.Series(predicted), method="pearson"))
    rank_ic = float(pd.Series(actual).corr(pd.Series(predicted), method="spearman"))
    return ic if np.isfinite(ic) else 0.0, rank_ic if np.isfinite(rank_ic) else 0.0


def _strategy_curve(frame: pd.DataFrame, *, label: str, transaction_cost_bps: float = 0.0) -> pd.DataFrame:
    strategy = frame.copy()
    cost_rate = max(0.0, float(transaction_cost_bps)) / 10000.0
    strategy["signal"] = np.sign(strategy["prediction"]).replace(0, 1)
    strategy["executed_signal"] = strategy["signal"].shift(1).fillna(0.0)
    strategy["turnover"] = strategy["executed_signal"].diff().abs().fillna(strategy["executed_signal"].abs())
    strategy["transaction_cost"] = strategy["turnover"] * cost_rate
    strategy["strategy_return"] = strategy["executed_signal"] * strategy["actual"] - strategy["transaction_cost"]
    strategy["cumulative_return"] = (1.0 + strategy["strategy_return"]).cumprod()
    strategy["benchmark_return"] = (1.0 + strategy["actual"]).cumprod()
    strategy["label"] = label
    strategy["transaction_cost_bps"] = float(transaction_cost_bps)
    return strategy


def _curve_figure(settings: Any, db: Any, *, user: Any, workspace: Any, source_asset: Any, strategy: pd.DataFrame, time_column: str, slug: str, title: str, summary: str) -> dict[str, Any]:
    fig, ax = base._ts_figure(title)
    ax.plot(strategy[time_column], strategy["cumulative_return"], label="strategy")
    ax.plot(strategy[time_column], strategy["benchmark_return"], label="benchmark")
    ax.legend()
    fig.tight_layout()
    return base._candidate_figure(settings, db, user=user, workspace=workspace, source_asset=source_asset, figure=fig, filename_slug=slug, title=title, summary=summary)


def _feature_label_tables(test: pd.DataFrame, *, dependent: str, feature_columns: list[str]) -> dict[str, Any]:
    return {
        "feature_label_spec_table": [
            {
                "feature_columns": ", ".join(feature_columns),
                "label_column": dependent,
                "observation_count": int(len(test)),
            }
        ]
    }


def run_quant_linear_model_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    feature_columns = list(base._spec_option(kwargs, "feature_columns", kwargs.get("independents") or []))
    time_column = kwargs.get("time_column") or "date"
    if not feature_columns:
        raise ValueError("Quant linear model requires feature columns.")
    asset, sample = _load_quant_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], dependent=dependent, feature_columns=feature_columns, time_column=time_column)
    train, test = _split_sample(sample, time_column=time_column, split_ratio=float(base._spec_option(kwargs, "split_ratio", 0.7)))
    model = LinearRegression()
    model.fit(train[feature_columns], train[dependent])
    test["prediction"] = model.predict(test[feature_columns])
    ic, rank_ic = _ic_stats(test[dependent], test["prediction"])
    transaction_cost_bps = float(base._spec_option(kwargs, "transaction_cost_bps", 0.0))
    strategy = _strategy_curve(test.rename(columns={dependent: "actual"}), label="linear", transaction_cost_bps=transaction_cost_bps)
    fig_asset = _curve_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, strategy=strategy, time_column=time_column, slug="quant_linear_curve", title="Quant linear strategy curve", summary="Strategy curve from the linear alpha model.")
    return base._nonregression_payload(
        model_type="quant_linear_model",
        model_label="Quant Linear Model",
        engine="qlib",
        asset=asset,
        sample=test.reset_index(drop=True),
        narrative_lines=["Linear alpha model evaluated with information coefficients and a simple long-short strategy curve."],
        tables={
            "prediction_metric_table": [{
                "mse": float(mean_squared_error(test[dependent], test["prediction"])),
                "r2": float(r2_score(test[dependent], test["prediction"])),
            }],
            "ic_summary_table": [{"ic": ic, "rank_ic": rank_ic}],
            "coefficient_table": [{"feature": feature, "coefficient": float(coef)} for feature, coef in zip(feature_columns, model.coef_)],
            **_feature_label_tables(test, dependent=dependent, feature_columns=feature_columns),
        },
        figures=[fig_asset],
        specification={"dependent": dependent, "feature_columns": feature_columns, "time_column": time_column},
        audit_trail={"derived_columns": ["prediction", "signal", "executed_signal", "turnover", "transaction_cost", "strategy_return", "cumulative_return"], "filters": [], "signal_lag": 1, "transaction_cost_bps": transaction_cost_bps},
    )


def run_quant_lightgbm_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    lgb = _require_lightgbm()
    dependent = kwargs["dependent"]
    feature_columns = list(base._spec_option(kwargs, "feature_columns", kwargs.get("independents") or []))
    time_column = kwargs.get("time_column") or "date"
    if not feature_columns:
        raise ValueError("Quant LightGBM requires feature columns.")
    asset, sample = _load_quant_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], dependent=dependent, feature_columns=feature_columns, time_column=time_column)
    train, test = _split_sample(sample, time_column=time_column, split_ratio=float(base._spec_option(kwargs, "split_ratio", 0.7)))
    model = lgb.LGBMRegressor(
        n_estimators=int(base._spec_option(kwargs, "n_estimators", 120)),
        learning_rate=float(base._spec_option(kwargs, "learning_rate", 0.05)),
        num_leaves=int(base._spec_option(kwargs, "num_leaves", 31)),
        random_state=42,
        verbosity=-1,
    )
    model.fit(train[feature_columns], train[dependent])
    test["prediction"] = model.predict(test[feature_columns])
    ic, rank_ic = _ic_stats(test[dependent], test["prediction"])
    transaction_cost_bps = float(base._spec_option(kwargs, "transaction_cost_bps", 0.0))
    strategy = _strategy_curve(test.rename(columns={dependent: "actual"}), label="lightgbm", transaction_cost_bps=transaction_cost_bps)
    curve_asset = _curve_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, strategy=strategy, time_column=time_column, slug="quant_lgb_curve", title="Quant LightGBM strategy curve", summary="Strategy curve from the LightGBM alpha model.")
    importance_frame = pd.DataFrame({"feature": feature_columns, "importance": model.feature_importances_}).sort_values("importance", ascending=False)
    fig, ax = base._ts_figure("LightGBM feature importance")
    importance_frame.set_index("feature")["importance"].plot(kind="bar", ax=ax, color="#2563eb")
    fig.tight_layout()
    importance_asset = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig, filename_slug="quant_lgb_importance", title="LightGBM feature importance", summary="Feature importance from the LightGBM alpha model.")
    return base._nonregression_payload(
        model_type="quant_lightgbm",
        model_label="Quant LightGBM",
        engine="lightgbm",
        asset=asset,
        sample=test.reset_index(drop=True),
        narrative_lines=["Gradient-boosted alpha model evaluated with IC metrics and a strategy curve."],
        tables={
            "prediction_metric_table": [{"mse": float(mean_squared_error(test[dependent], test["prediction"])), "r2": float(r2_score(test[dependent], test["prediction"]))}],
            "feature_importance_table": base._serialize_rows(importance_frame),
            "ic_summary_table": [{"ic": ic, "rank_ic": rank_ic}],
            **_feature_label_tables(test, dependent=dependent, feature_columns=feature_columns),
        },
        figures=[importance_asset, curve_asset],
        specification={"dependent": dependent, "feature_columns": feature_columns, "time_column": time_column},
        audit_trail={"derived_columns": ["prediction", "signal", "executed_signal", "turnover", "transaction_cost", "strategy_return", "cumulative_return"], "filters": [], "signal_lag": 1, "transaction_cost_bps": transaction_cost_bps},
    )


def run_quant_backtest_report_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    feature_columns = list(base._spec_option(kwargs, "feature_columns", kwargs.get("independents") or []))
    time_column = kwargs.get("time_column") or "date"
    if not feature_columns:
        raise ValueError("Quant backtest report requires feature columns.")
    asset, sample = _load_quant_sample(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], asset_id=kwargs["asset_id"], dependent=dependent, feature_columns=feature_columns, time_column=time_column)
    train, test = _split_sample(sample, time_column=time_column, split_ratio=float(base._spec_option(kwargs, "split_ratio", 0.7)))
    model = LinearRegression().fit(train[feature_columns], train[dependent])
    test["prediction"] = model.predict(test[feature_columns])
    transaction_cost_bps = float(base._spec_option(kwargs, "transaction_cost_bps", 0.0))
    strategy = _strategy_curve(test.rename(columns={dependent: "actual"}), label="backtest", transaction_cost_bps=transaction_cost_bps)
    turnover = strategy["turnover"]
    metrics = {
        "mean_return": float(strategy["strategy_return"].mean()),
        "volatility": float(strategy["strategy_return"].std(ddof=1)),
        "sharpe": float(strategy["strategy_return"].mean() / (strategy["strategy_return"].std(ddof=1) or 1.0)),
        "max_drawdown": float((strategy["cumulative_return"] / strategy["cumulative_return"].cummax() - 1.0).min()),
        "turnover": float(turnover.mean()),
        "transaction_cost_bps": transaction_cost_bps,
    }
    curve_asset = _curve_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, strategy=strategy, time_column=time_column, slug="quant_backtest_curve", title="Backtest equity curve", summary="Equity curve from the ranked-signal backtest.")
    fig, ax = base._ts_figure("Turnover")
    ax.plot(strategy[time_column], turnover)
    fig.tight_layout()
    turnover_asset = base._candidate_figure(settings, db, user=kwargs["user"], workspace=kwargs["workspace"], source_asset=asset, figure=fig, filename_slug="quant_turnover", title="Backtest turnover", summary="Turnover path from the backtest signal changes.")
    top_positions = (
        strategy.assign(rank=strategy["prediction"].rank(ascending=False, method="first"))
        [[time_column, "prediction", "signal", "rank"]]
        .head(20)
    )
    return base._nonregression_payload(
        model_type="quant_backtest_report",
        model_label="Quant Backtest Report",
        engine="qlib",
        asset=asset,
        sample=strategy.reset_index(drop=True),
        narrative_lines=["Backtest report built from predicted signals with equity-curve and turnover diagnostics."],
        tables={
            "backtest_metric_table": [metrics],
            "position_analysis_table": base._serialize_rows(top_positions),
            **_feature_label_tables(test, dependent=dependent, feature_columns=feature_columns),
        },
        figures=[curve_asset, turnover_asset],
        specification={"dependent": dependent, "feature_columns": feature_columns, "time_column": time_column},
        audit_trail={"derived_columns": ["prediction", "signal", "executed_signal", "turnover", "transaction_cost", "strategy_return", "cumulative_return"], "filters": [], "signal_lag": 1, "transaction_cost_bps": transaction_cost_bps},
    )


def run_quant_catboost_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    CatBoostRegressor = _require_catboost()
    dependent = kwargs["dependent"]
    feature_columns = list(base._spec_option(kwargs, "feature_columns", kwargs.get("independents") or []))
    time_column = kwargs.get("time_column") or "date"
    if not feature_columns:
        raise ValueError("Quant CatBoost requires feature columns.")
    asset, sample = _load_quant_sample(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        asset_id=kwargs["asset_id"],
        dependent=dependent,
        feature_columns=feature_columns,
        time_column=time_column,
    )
    train, test = _split_sample(sample, time_column=time_column, split_ratio=float(base._spec_option(kwargs, "split_ratio", 0.7)))
    model = CatBoostRegressor(
        iterations=int(base._spec_option(kwargs, "iterations", 180)),
        learning_rate=float(base._spec_option(kwargs, "learning_rate", 0.05)),
        depth=int(base._spec_option(kwargs, "depth", 6)),
        loss_function="RMSE",
        random_seed=42,
        verbose=False,
    )
    model.fit(train[feature_columns], train[dependent])
    test["prediction"] = model.predict(test[feature_columns])
    ic, rank_ic = _ic_stats(test[dependent], test["prediction"])
    transaction_cost_bps = float(base._spec_option(kwargs, "transaction_cost_bps", 0.0))
    strategy = _strategy_curve(test.rename(columns={dependent: "actual"}), label="catboost", transaction_cost_bps=transaction_cost_bps)
    curve_asset = _curve_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        strategy=strategy,
        time_column=time_column,
        slug="quant_catboost_curve",
        title="Quant CatBoost strategy curve",
        summary="Strategy curve from the CatBoost alpha model.",
    )
    importance_frame = (
        pd.DataFrame({"feature": feature_columns, "importance": model.get_feature_importance()})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    fig, ax = base._ts_figure("CatBoost feature importance")
    importance_frame.set_index("feature")["importance"].plot(kind="bar", ax=ax, color="#0f766e")
    fig.tight_layout()
    importance_asset = base._candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=fig,
        filename_slug="quant_catboost_importance",
        title="CatBoost feature importance",
        summary="Feature importance from the CatBoost alpha model.",
    )
    return base._nonregression_payload(
        model_type="quant_catboost",
        model_label="Quant CatBoost",
        engine="catboost",
        asset=asset,
        sample=test.reset_index(drop=True),
        narrative_lines=["CatBoost alpha model evaluated with IC metrics and a simple long-short strategy curve."],
        tables={
            "prediction_metric_table": [{"mse": float(mean_squared_error(test[dependent], test["prediction"])), "r2": float(r2_score(test[dependent], test["prediction"]))}],
            "feature_importance_table": base._serialize_rows(importance_frame),
            "ic_summary_table": [{"ic": ic, "rank_ic": rank_ic}],
            **_feature_label_tables(test, dependent=dependent, feature_columns=feature_columns),
        },
        figures=[importance_asset, curve_asset],
        specification={"dependent": dependent, "feature_columns": feature_columns, "time_column": time_column},
        audit_trail={"derived_columns": ["prediction", "signal", "executed_signal", "turnover", "transaction_cost", "strategy_return", "cumulative_return"], "filters": [], "signal_lag": 1, "transaction_cost_bps": transaction_cost_bps},
    )


def run_quant_position_analysis(settings: Any, db: Any, **kwargs: Any) -> dict[str, Any]:
    dependent = kwargs["dependent"]
    feature_columns = list(base._spec_option(kwargs, "feature_columns", kwargs.get("independents") or []))
    time_column = kwargs.get("time_column") or "date"
    if not feature_columns:
        raise ValueError("Position analysis requires feature columns.")
    asset, sample = _load_quant_sample(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        asset_id=kwargs["asset_id"],
        dependent=dependent,
        feature_columns=feature_columns,
        time_column=time_column,
    )
    train, test = _split_sample(sample, time_column=time_column, split_ratio=float(base._spec_option(kwargs, "split_ratio", 0.7)))
    model = LinearRegression().fit(train[feature_columns], train[dependent])
    test["prediction"] = model.predict(test[feature_columns])
    test["signal"] = np.sign(test["prediction"]).replace(0, 1)
    test["decile"] = pd.qcut(test["prediction"].rank(method="first"), 10, labels=False, duplicates="drop") + 1
    test["actual"] = test[dependent]
    bucket = (
        test.groupby("decile", as_index=False)
        .agg(mean_prediction=("prediction", "mean"), mean_actual=("actual", "mean"), count=("actual", "size"))
    )
    transaction_cost_bps = float(base._spec_option(kwargs, "transaction_cost_bps", 0.0))
    strategy = _strategy_curve(test[["prediction", "actual", time_column]].copy(), label="position", transaction_cost_bps=transaction_cost_bps)
    curve_asset = _curve_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        strategy=strategy,
        time_column=time_column,
        slug="quant_position_curve",
        title="Position analysis strategy curve",
        summary="Strategy curve implied by ranked predictive positions.",
    )
    fig, ax = base._ts_figure("Decile spread")
    ax.bar(bucket["decile"].astype(str), bucket["mean_actual"], color="#9333ea")
    fig.tight_layout()
    bucket_asset = base._candidate_figure(
        settings,
        db,
        user=kwargs["user"],
        workspace=kwargs["workspace"],
        source_asset=asset,
        figure=fig,
        filename_slug="quant_position_deciles",
        title="Position decile outcomes",
        summary="Average realized outcomes by prediction decile.",
    )
    return base._nonregression_payload(
        model_type="position_analysis",
        model_label="Position Analysis",
        engine="qlib",
        asset=asset,
        sample=test.reset_index(drop=True),
        narrative_lines=["Position analysis ranks predictions into deciles and summarizes realized outcomes across buckets."],
        tables={
            "position_analysis_table": base._serialize_rows(bucket),
            "top_positions_table": base._serialize_rows(test[[time_column, "prediction", "signal", "decile"]].sort_values("prediction", ascending=False).head(20)),
            **_feature_label_tables(test, dependent=dependent, feature_columns=feature_columns),
        },
        figures=[bucket_asset, curve_asset],
        specification={"dependent": dependent, "feature_columns": feature_columns, "time_column": time_column},
        audit_trail={"derived_columns": ["prediction", "signal", "executed_signal", "decile", "turnover", "transaction_cost", "strategy_return", "cumulative_return"], "filters": [], "signal_lag": 1, "transaction_cost_bps": transaction_cost_bps},
    )
