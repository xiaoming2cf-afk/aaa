from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify_data_lab import auth_headers, build_panel_dataset, build_time_series_dataset, configure_test_environment, create_workspace, upload_csv_asset  # noqa: E402
from verify_data_lab_full import _assert_model_output, _comparison_frame, _save_result_bundle, _write_json  # noqa: E402


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _run_model(client: TestClient, token: str, workspace_id: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    if response.status_code >= 400:
        raise AssertionError(f"{label}: {response.status_code} {response.text}")
    run_payload = response.json()
    record_id = run_payload.get("result_record_id")
    if not record_id:
        raise AssertionError(f"{label}: missing result_record_id")
    detail = client.get(f"/api/data-lab/results/models/{record_id}", headers=auth_headers(token))
    detail.raise_for_status()
    detail_payload = detail.json()
    result = json.loads(json.dumps(detail_payload["result"], ensure_ascii=False))
    result["_record_id"] = record_id
    result["_detail_payload"] = detail_payload
    return result


def _panel_specs(panel_asset_id: str) -> list[dict[str, Any]]:
    return [
        {"group": "country_panel", "method": "random_effects", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "random_effects", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "month_index"}, "variant": {"variant_label": "re_treated", "variant_spec": {"controls": ["post", "treated"]}}},
        {"group": "country_panel", "method": "first_difference", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "first_difference", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "month_index"}, "variant": {"variant_label": "fd_endog", "variant_spec": {"independents": ["size", "leverage", "endogenous_x"]}}},
        {"group": "country_panel", "method": "between_ols", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "between_ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": [], "entity_column": "firm_id", "time_column": "month_index"}, "variant": {"variant_label": "between_treated", "variant_spec": {"controls": ["treated"]}}},
        {"group": "country_panel", "method": "pooled_ols", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "pooled_ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "month_index"}, "variant": {"variant_label": "pooled_endog", "variant_spec": {"independents": ["size", "leverage", "endogenous_x"]}}},
        {"group": "country_panel", "method": "fama_macbeth", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "fama_macbeth", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": [], "entity_column": "firm_id", "time_column": "month_index"}, "variant": {"variant_label": "fm_extra", "variant_spec": {"controls": ["treated"]}}},
        {"group": "country_panel", "method": "iv_liml", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "iv_liml", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "liml_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"group": "country_panel", "method": "iv_gmm", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "iv_gmm", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "gmm_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"group": "country_panel", "method": "absorbing_ls", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "absorbing_ls", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "date"}, "variant": {"variant_label": "absorbing_treated", "variant_spec": {"controls": ["post", "treated"]}}},
        {"group": "country_panel", "method": "sur", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "sur", "dependent": "outcome_y", "secondary_dependent": "secondary_outcome", "independents": ["size", "leverage"], "controls": ["post"]}, "variant": {"variant_label": "sur_count", "variant_spec": {"secondary_dependent": "count_outcome"}}},
        {"group": "country_panel", "method": "iv_3sls", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "iv_3sls", "dependent": "outcome_y", "secondary_dependent": "secondary_outcome", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "3sls_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"group": "country_panel", "method": "system_gmm", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "system_gmm", "dependent": "outcome_y", "secondary_dependent": "secondary_outcome", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "sysgmm_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"group": "country_panel", "method": "glm", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "glm", "dependent": "count_outcome", "independents": ["size", "leverage"], "controls": ["post"], "glm_family": "poisson"}, "variant": {"variant_label": "glm_nb", "variant_spec": {"glm_family": "negative_binomial"}}},
        {"group": "country_panel", "method": "quantile_regression", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "quantile_regression", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "quantile": 0.5}, "variant": {"variant_label": "qr_upper", "variant_spec": {"quantile": 0.75}}},
        {"group": "country_panel", "method": "gee", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "gee", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "gee_group_column": "firm_id", "gee_family": "gaussian"}, "variant": {"variant_label": "gee_count", "variant_spec": {"dependent": "count_outcome", "gee_family": "poisson"}}},
        {"group": "country_panel", "method": "mnlogit", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "mnlogit", "dependent": "multiclass_outcome", "independents": ["size", "leverage"], "controls": ["post"]}, "variant": {"variant_label": "mnlogit_extra", "variant_spec": {"independents": ["size", "leverage", "endogenous_x"]}}},
        {"group": "country_panel", "method": "negative_binomial", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "negative_binomial", "dependent": "count_outcome", "independents": ["size", "leverage"], "controls": ["post"]}, "variant": {"variant_label": "nb_treated", "variant_spec": {"controls": ["post", "treated"]}}},
        {"group": "country_panel", "method": "zero_inflated_count", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "zero_inflated_count", "dependent": "count_outcome", "independents": ["size", "leverage"], "controls": ["post"], "inflation_regressors": ["size", "post"], "count_family": "poisson"}, "variant": {"variant_label": "zi_nb", "variant_spec": {"count_family": "negative_binomial"}}},
        {"group": "country_panel", "method": "mixedlm", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "mixedlm", "dependent": "outcome_y", "independents": ["size", "leverage", "post"], "entity_column": "firm_id"}, "variant": {"variant_label": "mixed_treated", "variant_spec": {"independents": ["size", "leverage", "post", "treated"]}}},
        {"group": "country_panel", "method": "staggered_did", "baseline": {"asset_id": panel_asset_id, "model_family": "causal_inference", "model_type": "staggered_did", "dependent": "outcome_y", "controls": ["size", "leverage"], "entity_column": "firm_id", "time_column": "month_index", "treatment_column": "treated", "treatment_time_column": "treatment_time", "lead_window": 4, "lag_window": 4}, "variant": {"variant_label": "staggered_wide", "variant_spec": {"lead_window": 5, "lag_window": 5}}},
        {"group": "country_panel", "method": "synthetic_control", "baseline": {"asset_id": panel_asset_id, "model_family": "causal_inference", "model_type": "synthetic_control", "dependent": "outcome_y", "entity_column": "firm_id", "time_column": "month_index", "treated_unit": "firm_01", "control_units": ["firm_02", "firm_03", "firm_04", "firm_05", "firm_06"], "treatment_time": 18}, "variant": {"variant_label": "synthetic_alt_pool", "variant_spec": {"control_units": ["firm_07", "firm_08", "firm_09", "firm_10", "firm_11"]}}},
        {"group": "country_panel", "method": "regression_kink", "baseline": {"asset_id": panel_asset_id, "model_family": "causal_inference", "model_type": "regression_kink", "dependent": "outcome_y", "running_column": "running_score", "controls": ["size", "leverage"], "kink_point": 0.0, "bandwidth": 1.0}, "variant": {"variant_label": "kink_narrow", "variant_spec": {"bandwidth": 0.75}}},
        {"group": "country_panel", "method": "instrumental_causal", "baseline": {"asset_id": panel_asset_id, "model_family": "causal_inference", "model_type": "instrumental_causal", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "instr_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"group": "country_panel", "method": "inverse_propensity_weighting", "baseline": {"asset_id": panel_asset_id, "model_family": "causal_inference", "model_type": "inverse_propensity_weighting", "dependent": "outcome_y", "treatment_column": "treated", "controls": ["size", "leverage", "post"]}, "variant": {"variant_label": "ipw_endog", "variant_spec": {"controls": ["size", "leverage", "post", "endogenous_x"]}}},
        {"group": "country_panel", "method": "bayesian_linear_regression", "baseline": {"asset_id": panel_asset_id, "model_family": "bayesian", "model_type": "bayesian_linear_regression", "dependent": "outcome_y", "independents": ["size", "leverage", "post"], "draws": 100, "tune": 100, "chains": 1}, "variant": {"variant_label": "bayes_linear_treated", "variant_spec": {"independents": ["size", "leverage", "post", "treated"], "draws": 120, "tune": 120}}},
        {"group": "country_panel", "method": "bayesian_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "bayesian", "model_type": "bayesian_panel", "dependent": "outcome_y", "independents": ["size", "leverage"], "entity_column": "firm_id", "time_column": "date", "draws": 100, "tune": 100, "chains": 1}, "variant": {"variant_label": "bayes_panel_post", "variant_spec": {"independents": ["size", "leverage", "post"], "draws": 120, "tune": 120}}},
        {"group": "country_panel", "method": "bayesian_did", "baseline": {"asset_id": panel_asset_id, "model_family": "bayesian", "model_type": "bayesian_did", "dependent": "outcome_y", "treatment_column": "treated", "post_column": "post", "controls": ["size", "leverage"], "draws": 100, "tune": 100, "chains": 1}, "variant": {"variant_label": "bayes_did_extra", "variant_spec": {"controls": ["size", "leverage", "endogenous_x"], "draws": 120, "tune": 120}}},
    ]


def _time_series_specs(ts_asset_id: str) -> list[dict[str, Any]]:
    return [
        {"group": "macro_finance_ts", "method": "traded_factor_model", "baseline": {"asset_id": ts_asset_id, "model_family": "asset_pricing", "model_type": "traded_factor_model", "series_columns": ["asset_return", "return_a", "return_b"], "factor_columns": ["market_return", "smb", "hml"], "time_column": "date"}, "variant": {"variant_label": "factor_alt_assets", "variant_spec": {"series_columns": ["asset_return", "return_b", "return_c"]}}},
        {"group": "macro_finance_ts", "method": "linear_factor_gmm", "baseline": {"asset_id": ts_asset_id, "model_family": "asset_pricing", "model_type": "linear_factor_gmm", "series_columns": ["asset_return", "return_a", "return_b"], "factor_columns": ["market_return", "smb", "hml"], "time_column": "date"}, "variant": {"variant_label": "lfgmm_alt_assets", "variant_spec": {"series_columns": ["asset_return", "return_b", "return_c"]}}},
        {"group": "macro_finance_ts", "method": "varmax", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "varmax", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "varmax_order": [1, 1], "forecast_steps": 5}, "variant": {"variant_label": "varmax_alt", "variant_spec": {"varmax_order": [2, 1], "forecast_steps": 4}}},
        {"group": "macro_finance_ts", "method": "vecm", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "vecm", "series_columns": ["level_a", "level_b", "level_c"], "time_column": "date", "coint_rank": 1, "vecm_diff_lags": 1, "forecast_steps": 5}, "variant": {"variant_label": "vecm_alt", "variant_spec": {"vecm_diff_lags": 2, "forecast_steps": 4}}},
        {"group": "macro_finance_ts", "method": "markov_switching", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "markov_switching", "dependent": "asset_return", "time_column": "date", "markov_regimes": 2}, "variant": {"variant_label": "markov_three", "variant_spec": {"markov_regimes": 3}}},
        {"group": "macro_finance_ts", "method": "unobserved_components", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "unobserved_components", "dependent": "seasonal_series", "time_column": "date", "seasonal_periods": 12}, "variant": {"variant_label": "uc_policy", "variant_spec": {"dependent": "policy_rate", "seasonal_periods": 6}}},
        {"group": "macro_finance_ts", "method": "exponential_smoothing", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "exponential_smoothing", "dependent": "seasonal_series", "time_column": "date", "seasonal": "add", "seasonal_periods": 12, "forecast_steps": 6}, "variant": {"variant_label": "es_no_seasonal", "variant_spec": {"seasonal": "", "forecast_steps": 4}}},
        {"group": "macro_finance_ts", "method": "egarch", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "egarch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, "variant": {"variant_label": "egarch_alt", "variant_spec": {"garch_p": 2, "forecast_steps": 6}}},
        {"group": "macro_finance_ts", "method": "gjr_garch", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "gjr_garch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, "variant": {"variant_label": "gjr_alt", "variant_spec": {"garch_p": 2, "forecast_steps": 6}}},
        {"group": "macro_finance_ts", "method": "harx", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "harx", "dependent": "asset_return", "time_column": "date", "harx_lags": [1, 5, 22], "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, "variant": {"variant_label": "harx_alt", "variant_spec": {"harx_lags": [1, 3, 12], "forecast_steps": 6}}},
        {"group": "macro_finance_ts", "method": "adf_test", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "adf_test", "dependent": "policy_rate", "time_column": "date", "trend": "c", "unit_root_lags": 2}, "variant": {"variant_label": "adf_ct", "variant_spec": {"trend": "ct", "unit_root_lags": 3}}},
        {"group": "macro_finance_ts", "method": "kpss_test", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "kpss_test", "dependent": "policy_rate", "time_column": "date", "trend": "c", "unit_root_lags": 2}, "variant": {"variant_label": "kpss_ct", "variant_spec": {"trend": "ct", "unit_root_lags": 3}}},
        {"group": "macro_finance_ts", "method": "pp_test", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "pp_test", "dependent": "policy_rate", "time_column": "date", "trend": "c", "unit_root_lags": 2}, "variant": {"variant_label": "pp_ct", "variant_spec": {"trend": "ct", "unit_root_lags": 3}}},
        {"group": "macro_finance_ts", "method": "zivot_andrews", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "zivot_andrews", "dependent": "policy_rate", "time_column": "date", "trend": "c", "unit_root_lags": 2}, "variant": {"variant_label": "za_ct", "variant_spec": {"trend": "ct", "unit_root_lags": 3}}},
        {"group": "macro_finance_ts", "method": "engle_granger", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "engle_granger", "dependent": "level_a", "series_columns": ["level_b", "level_c"], "time_column": "date"}, "variant": {"variant_label": "eg_single", "variant_spec": {"series_columns": ["level_b"]}}},
        {"group": "macro_finance_ts", "method": "dynamic_ols", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "dynamic_ols", "dependent": "level_a", "series_columns": ["level_b", "level_c"], "time_column": "date"}, "variant": {"variant_label": "dols_single", "variant_spec": {"series_columns": ["level_b"]}}},
        {"group": "macro_finance_ts", "method": "fm_ols", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "fm_ols", "dependent": "level_a", "series_columns": ["level_b", "level_c"], "time_column": "date"}, "variant": {"variant_label": "fmols_single", "variant_spec": {"series_columns": ["level_b"]}}},
        {"group": "macro_finance_ts", "method": "interrupted_time_series", "baseline": {"asset_id": ts_asset_id, "model_family": "causal_inference", "model_type": "interrupted_time_series", "dependent": "policy_rate", "time_column": "date", "controls": ["inflation_gap", "output_gap"], "treatment_time": "2019-07-31"}, "variant": {"variant_label": "its_gap_focus", "variant_spec": {"dependent": "output_gap", "controls": ["inflation_gap"], "treatment_time": "2018-12-31"}}},
        {"group": "macro_finance_ts", "method": "bayesian_its", "baseline": {"asset_id": ts_asset_id, "model_family": "bayesian", "model_type": "bayesian_its", "dependent": "policy_rate", "time_column": "date", "treatment_index": 18, "draws": 100, "tune": 100, "chains": 1}, "variant": {"variant_label": "bayes_its_longer", "variant_spec": {"treatment_index": 24, "draws": 120, "tune": 120}}},
        {"group": "macro_finance_ts", "method": "quant_linear_model", "baseline": {"asset_id": ts_asset_id, "model_family": "quant_research", "model_type": "quant_linear_model", "dependent": "asset_return", "feature_columns": ["market_return", "smb", "hml", "policy_rate", "inflation_gap"], "time_column": "date", "split_ratio": 0.7}, "variant": {"variant_label": "quant_linear_alt", "variant_spec": {"feature_columns": ["market_return", "smb", "hml", "output_gap"], "split_ratio": 0.75}}},
        {"group": "macro_finance_ts", "method": "quant_lightgbm", "baseline": {"asset_id": ts_asset_id, "model_family": "quant_research", "model_type": "quant_lightgbm", "dependent": "asset_return", "feature_columns": ["market_return", "smb", "hml", "policy_rate", "inflation_gap"], "time_column": "date", "split_ratio": 0.7, "n_estimators": 80, "learning_rate": 0.05, "num_leaves": 15}, "variant": {"variant_label": "quant_lgbm_alt", "variant_spec": {"feature_columns": ["market_return", "smb", "hml", "output_gap"], "n_estimators": 120, "num_leaves": 21}}},
        {"group": "macro_finance_ts", "method": "quant_catboost", "baseline": {"asset_id": ts_asset_id, "model_family": "quant_research", "model_type": "quant_catboost", "dependent": "asset_return", "feature_columns": ["market_return", "smb", "hml", "policy_rate", "inflation_gap"], "time_column": "date", "split_ratio": 0.7, "iterations": 80, "depth": 4}, "variant": {"variant_label": "quant_cat_alt", "variant_spec": {"feature_columns": ["market_return", "smb", "hml", "output_gap"], "iterations": 120, "depth": 5}}},
        {"group": "macro_finance_ts", "method": "quant_backtest_report", "baseline": {"asset_id": ts_asset_id, "model_family": "quant_research", "model_type": "quant_backtest_report", "dependent": "asset_return", "feature_columns": ["market_return", "smb", "hml", "policy_rate", "inflation_gap"], "time_column": "date", "split_ratio": 0.7}, "variant": {"variant_label": "quant_backtest_alt", "variant_spec": {"feature_columns": ["market_return", "smb", "hml", "output_gap"], "split_ratio": 0.75}}},
        {"group": "macro_finance_ts", "method": "position_analysis", "baseline": {"asset_id": ts_asset_id, "model_family": "quant_research", "model_type": "position_analysis", "dependent": "asset_return", "feature_columns": ["market_return", "smb", "hml", "policy_rate", "inflation_gap"], "time_column": "date", "split_ratio": 0.7}, "variant": {"variant_label": "position_alt", "variant_spec": {"feature_columns": ["market_return", "smb", "hml", "output_gap"], "split_ratio": 0.75}}},
    ]


def _portfolio_specs(ts_asset_id: str) -> list[dict[str, Any]]:
    base = {"asset_id": ts_asset_id, "model_family": "portfolio_allocation", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date"}
    return [
        {"group": "macro_finance_ts", "method": "efficient_frontier", "baseline": {**base, "model_type": "efficient_frontier", "portfolio_objective": "max_sharpe", "long_only": True}, "variant": {"variant_label": "ef_min_vol", "variant_spec": {"portfolio_objective": "min_volatility"}}},
        {"group": "macro_finance_ts", "method": "semivariance_frontier", "baseline": {**base, "model_type": "semivariance_frontier", "long_only": True}, "variant": {"variant_label": "semi_ls", "variant_spec": {"long_only": False}}},
        {"group": "macro_finance_ts", "method": "cvar_frontier", "baseline": {**base, "model_type": "cvar_frontier", "cvar_beta": 0.95, "long_only": True}, "variant": {"variant_label": "cvar_tail", "variant_spec": {"cvar_beta": 0.99}}},
        {"group": "macro_finance_ts", "method": "cdar_frontier", "baseline": {**base, "model_type": "cdar_frontier", "cdar_beta": 0.95, "long_only": True}, "variant": {"variant_label": "cdar_tail", "variant_spec": {"cdar_beta": 0.99}}},
        {"group": "macro_finance_ts", "method": "black_litterman", "baseline": {**base, "model_type": "black_litterman"}, "variant": {"variant_label": "bl_alt_assets", "variant_spec": {"series_columns": ["asset_return", "return_a", "return_b"]}}},
        {"group": "macro_finance_ts", "method": "hrp", "baseline": {**base, "model_type": "hrp"}, "variant": {"variant_label": "hrp_alt_assets", "variant_spec": {"series_columns": ["asset_return", "return_a", "return_b"]}}},
        {"group": "macro_finance_ts", "method": "discrete_allocation", "baseline": {**base, "model_type": "discrete_allocation", "capital": 100000}, "variant": {"variant_label": "discrete_small", "variant_spec": {"capital": 50000}}},
    ]


def _normalize_filter(values: Iterable[str] | None) -> set[str]:
    return {str(value).strip() for value in (values or []) if str(value).strip()}


def run_verification(
    output_dir: Path | None = None,
    *,
    groups: Iterable[str] | None = None,
    methods: Iterable[str] | None = None,
    clean_output: bool = True,
    write_summary: bool = True,
) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-model-upgrade-"))
    configure_test_environment(temp_root)
    group_filter = _normalize_filter(groups)
    method_filter = _normalize_filter(methods)

    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            if clean_output:
                shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Upgrade Verifier", "email": "upgrade@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Model Upgrade Verification")

        panel_frame = build_panel_dataset()
        ts_frame = build_time_series_dataset()
        panel_asset_id = upload_csv_asset(client, token, workspace_id, "upgrade_panel.csv", panel_frame)
        ts_asset_id = upload_csv_asset(client, token, workspace_id, "upgrade_ts.csv", ts_frame)

        if output_dir:
            panel_dir = output_dir / "country_panel"
            ts_dir = output_dir / "macro_finance_ts"
            panel_dir.mkdir(parents=True, exist_ok=True)
            ts_dir.mkdir(parents=True, exist_ok=True)
            panel_frame.to_csv(panel_dir / "country_panel_input.csv", index=False)
            ts_frame.to_csv(ts_dir / "macro_finance_ts_input.csv", index=False)

        specs = _panel_specs(panel_asset_id) + _time_series_specs(ts_asset_id) + _portfolio_specs(ts_asset_id)
        if group_filter:
            specs = [spec for spec in specs if spec["group"] in group_filter]
        if method_filter:
            specs = [spec for spec in specs if spec["method"] in method_filter]
        model_reports: list[dict[str, Any]] = []
        group_counts: dict[str, int] = {}

        for spec in specs:
            method = spec["method"]
            started_at = time.perf_counter()
            print(f"[verify_model_upgrade] START {method}", flush=True)
            baseline_payload = dict(spec["baseline"])
            variant_payload = _merge(baseline_payload, spec["variant"].get("variant_spec", {}))
            if spec["variant"].get("variant_label"):
                variant_payload["variant_label"] = spec["variant"]["variant_label"]

            baseline_result = _run_model(client, token, workspace_id, baseline_payload, f"{method} baseline")
            variant_result = _run_model(client, token, workspace_id, variant_payload, f"{method} variant")

            _assert_model_output(f"{method} baseline", baseline_result)
            _assert_model_output(f"{method} variant", variant_result)

            group_counts[spec["group"]] = group_counts.get(spec["group"], 0) + 1
            model_reports.append(
                {
                    "group": spec["group"],
                    "method": method,
                    "baseline_record_id": baseline_result["_record_id"],
                    "variant_record_id": variant_result["_record_id"],
                    "baseline_tables": len((baseline_result.get("tables") or {}).keys()),
                    "variant_tables": len((variant_result.get("tables") or {}).keys()),
                    "baseline_figures": len(baseline_result.get("figures", []) or []),
                    "variant_figures": len(variant_result.get("figures", []) or []),
                }
            )

            if output_dir:
                model_root = output_dir / spec["group"] / "models" / method
                _save_result_bundle(client, token, baseline_result["_detail_payload"], model_root / "baseline")
                _save_result_bundle(client, token, variant_result["_detail_payload"], model_root / "variant")
                _comparison_frame(baseline_result, variant_result).to_csv(model_root / "comparison.csv", index=False)
            elapsed = time.perf_counter() - started_at
            print(f"[verify_model_upgrade] PASS {method} ({elapsed:.2f}s)", flush=True)

        report = {
            "status": "passed",
            "model_count": len(model_reports),
            "group_counts": group_counts,
            "groups": sorted(group_filter),
            "methods": sorted(method_filter),
            "models": model_reports,
        }
        if output_dir and write_summary:
            _write_json(output_dir / "verification_report.json", report)
            _write_json(output_dir / "model_anchor" / "model_upgrade_report.json", report)
        return report
    finally:
        client.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", default="", help="Comma-separated group filters.")
    parser.add_argument("--methods", default="", help="Comma-separated method filters.")
    parser.add_argument("--output-dir", default="", help="Optional output directory for artifacts.")
    args = parser.parse_args()
    groups = [value for value in args.groups.split(",") if value.strip()]
    methods = [value for value in args.methods.split(",") if value.strip()]
    output_dir = Path(args.output_dir) if args.output_dir.strip() else None
    report = run_verification(output_dir=output_dir, groups=groups, methods=methods)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
