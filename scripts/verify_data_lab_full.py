from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from verify_data_lab import (
    auth_headers,
    build_panel_dataset,
    build_time_series_dataset,
    configure_test_environment,
    create_workspace,
    upload_csv_asset,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_frame(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        frame = rows
    elif isinstance(rows, list):
        frame = pd.DataFrame(rows)
    elif isinstance(rows, dict):
        frame = pd.DataFrame([rows])
    else:
        frame = pd.DataFrame()
    frame.to_csv(path, index=False)


def _download_asset(client: TestClient, token: str, asset_id: str) -> bytes:
    response = client.get(f"/api/assets/{asset_id}/download", headers=auth_headers(token))
    response.raise_for_status()
    return response.content


def _save_result_bundle(client: TestClient, token: str, detail_payload: dict[str, Any], output_dir: Path) -> None:
    result = detail_payload["result"]
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "detail.json", detail_payload)
    _write_json(output_dir / "result.json", result)
    if result.get("coefficients"):
        _write_frame(output_dir / "coefficients.csv", result["coefficients"])
    if result.get("interpretation"):
        _write_json(output_dir / "interpretation.json", result["interpretation"])
    if result.get("specification"):
        _write_json(output_dir / "specification.json", result["specification"])
    if result.get("audit_trail"):
        _write_json(output_dir / "audit_trail.json", result["audit_trail"])
    for table_name, rows in (result.get("tables") or {}).items():
        _write_frame(output_dir / "tables" / f"{table_name}.csv", rows)
    for figure in result.get("figures", []):
        filename = figure.get("filename") or f"{figure['asset_id']}.png"
        (output_dir / "figures").mkdir(parents=True, exist_ok=True)
        (output_dir / "figures" / filename).write_bytes(_download_asset(client, token, figure["asset_id"]))


def _run_prepare(client: TestClient, token: str, workspace_id: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    if response.status_code >= 400:
        raise AssertionError(f"{label}: {response.status_code} {response.text}")
    data = response.json()
    if not data.get("asset", {}).get("id"):
        raise AssertionError(f"{label}: missing prepared asset id")
    detail = client.get(f"/api/data-lab/results/processing/{data['asset']['id']}", headers=auth_headers(token))
    detail.raise_for_status()
    detail_payload = detail.json()
    if detail_payload["result"]["workflow_type"] != "data_processing":
        raise AssertionError(f"{label}: wrong processing workflow type")
    return {"response": data, "detail": detail_payload}


def _run_plot(client: TestClient, token: str, workspace_id: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/plot",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    asset_id = data.get("asset", {}).get("id")
    if not asset_id:
        raise AssertionError(f"{label}: missing plot asset id")
    download = client.get(f"/api/assets/{asset_id}/download", headers=auth_headers(token))
    download.raise_for_status()
    if not download.content.startswith(b"\x89PNG"):
        raise AssertionError(f"{label}: plot output is not a PNG")
    return data


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


def _create_template(client: TestClient, token: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/lab-templates",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    return response.json()["template"]


def _assert_model_output(label: str, result: dict[str, Any]) -> None:
    model_type = result.get("model_type", "")
    if not result.get("interpretation", {}).get("sections"):
        raise AssertionError(f"{label}: missing interpretation sections")
    if not result.get("audit_trail"):
        raise AssertionError(f"{label}: missing audit trail")
    if not result.get("specification"):
        raise AssertionError(f"{label}: missing specification")
    if model_type in {"ols", "ppml", "logit", "probit", "fixed_effects", "gravity", "iv_2sls", "panel_iv", "taylor_rule", "capm", "fama_french_3"} and not result.get("coefficients"):
        raise AssertionError(f"{label}: missing coefficient table")
    if model_type == "did":
        if not any(row.get("term") == "did_interaction" for row in result.get("coefficients", [])):
            raise AssertionError("DID: missing did_interaction")
        if len(result.get("cell_means", [])) < 4:
            raise AssertionError("DID: missing 2x2 cell means")
    if model_type == "event_study" and (not result.get("tables", {}).get("event_study_table") or not result.get("figures")):
        raise AssertionError("Event Study: missing dynamic table or figure")
    if model_type == "rdd" and (not result.get("tables", {}).get("bandwidth_sensitivity") or not result.get("figures")):
        raise AssertionError("RDD: missing sensitivity table or figure")
    if model_type == "svar_irf" and (not result.get("tables", {}).get("irf_table") or len(result.get("figures", [])) < 2):
        raise AssertionError("SVAR IRF: missing IRF table or figures")
    if model_type == "virf" and len(result.get("figures", [])) < 2:
        raise AssertionError("VIRF: missing response figures")
    if model_type == "dy_connectedness" and (not result.get("tables", {}).get("connectedness_matrix") or len(result.get("figures", [])) < 2):
        raise AssertionError("DY: missing connectedness matrix or figures")
    if model_type == "bk_connectedness" and (not result.get("tables", {}).get("band_total_connectedness") or len(result.get("figures", [])) < 2):
        raise AssertionError("BK: missing band table or figures")
    if model_type in {"arch", "garch"} and len(result.get("figures", [])) < 2:
        raise AssertionError(f"{label}: missing volatility figures")
    if model_type in {"arima", "var"} and not result.get("figures"):
        raise AssertionError(f"{label}: missing forecast figure")
    if model_type in {"historical_var", "parametric_var", "ewma_volatility"} and not result.get("tables", {}).get("risk_summary"):
        raise AssertionError(f"{label}: missing risk summary")
    if model_type in {"black_scholes", "binomial_option"} and not result.get("tables", {}).get("pricing_table"):
        raise AssertionError(f"{label}: missing pricing table")
    if model_type == "rbc_dsge" and not result.get("tables", {}).get("impulse_response_table"):
        raise AssertionError("RBC/DSGE: missing impulse response table")
    if model_type in {"mean_variance", "minimum_variance", "risk_parity"} and not result.get("tables", {}).get("weights_table"):
        raise AssertionError(f"{label}: missing weights table")
    if model_type in {"altman_z", "dupont"} and not result.get("tables"):
        raise AssertionError(f"{label}: missing corporate finance table output")


def _comparison_frame(left: dict[str, Any], right: dict[str, Any]) -> pd.DataFrame:
    left_rows = pd.DataFrame(left.get("coefficients", []))
    right_rows = pd.DataFrame(right.get("coefficients", []))
    if not left_rows.empty and not right_rows.empty and "term" in left_rows.columns and "term" in right_rows.columns:
        return left_rows.merge(right_rows, on="term", how="outer", suffixes=("_baseline", "_variant"))
    return pd.DataFrame([{"baseline_record_id": left.get("_record_id", ""), "variant_record_id": right.get("_record_id", "")}])


def _model_specs(panel_asset_id: str, ts_asset_id: str) -> list[dict[str, Any]]:
    return [
        {"family": "econometrics_baseline", "method": "ols", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"]}, "variant": {"variant_label": "robust_with_treatment", "variant_spec": {"controls": ["post", "treated"], "independents": ["size", "leverage", "endogenous_x"]}}},
        {"family": "econometrics_baseline", "method": "ppml", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "ppml", "dependent": "export_flow", "independents": ["size", "leverage"], "controls": ["post"]}, "variant": {"variant_label": "trade_controls", "variant_spec": {"controls": ["post", "treated"], "independents": ["size", "leverage", "distance_km"]}}},
        {"family": "econometrics_baseline", "method": "logit", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "logit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}, "variant": {"variant_label": "post_policy_binary", "variant_spec": {"controls": ["treated", "post"], "independents": ["size", "leverage", "endogenous_x"]}}},
        {"family": "econometrics_baseline", "method": "probit", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "probit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}, "variant": {"variant_label": "probit_extended", "variant_spec": {"controls": ["treated", "post"], "independents": ["size", "leverage", "endogenous_x"]}}},
        {"family": "econometrics_baseline", "method": "did", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "did", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "post_column": "post"}, "variant": {"variant_label": "did_alt_controls", "variant_spec": {"controls": ["size", "leverage", "endogenous_x"]}}},
        {"family": "econometrics_baseline", "method": "event_study", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "event_study", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "event_time_column": "event_time", "entity_column": "firm_id", "time_column": "date", "include_time_effects": True, "lead_window": 4, "lag_window": 4, "omitted_period": -1}, "variant": {"variant_label": "wider_window", "variant_spec": {"lead_window": 5, "lag_window": 5, "controls": ["size", "leverage", "endogenous_x"]}}},
        {"family": "econometrics_baseline", "method": "rdd", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "rdd", "dependent": "outcome_y", "controls": ["size"], "running_column": "running_score", "rdd_cutoff": 0.0, "rdd_bandwidth": 1.1, "rdd_polynomial_order": 2, "treat_above_cutoff": True}, "variant": {"variant_label": "narrow_bandwidth", "variant_spec": {"rdd_bandwidth": 0.8, "rdd_polynomial_order": 1, "controls": ["size", "leverage"]}}},
        {"family": "econometrics_baseline", "method": "fixed_effects", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "fixed_effects", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}, "variant": {"variant_label": "entity_only", "variant_spec": {"include_time_effects": False, "controls": ["post", "treated"]}}},
        {"family": "econometrics_baseline", "method": "gravity", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "gravity", "dependent": "export_flow", "origin_mass_column": "origin_gdp", "destination_mass_column": "destination_gdp", "distance_column": "distance_km", "controls": ["post"]}, "variant": {"variant_label": "gravity_extended", "variant_spec": {"controls": ["post", "treated"]}}},
        {"family": "econometrics_baseline", "method": "iv_2sls", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "iv_2sls", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, "variant": {"variant_label": "iv_with_post", "variant_spec": {"controls": ["leverage", "post"]}}},
        {"family": "econometrics_baseline", "method": "panel_iv", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "econometrics_baseline", "model_type": "panel_iv", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}, "variant": {"variant_label": "panel_iv_entity_only", "variant_spec": {"include_time_effects": False, "controls": ["leverage", "post"]}}},
        {"family": "time_series_finance", "method": "arima", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "arima", "dependent": "policy_rate", "time_column": "date", "arima_p": 1, "arima_d": 0, "arima_q": 1, "forecast_steps": 6}, "variant": {"variant_label": "arima_alt_order", "variant_spec": {"arima_p": 2, "arima_d": 1, "arima_q": 1, "forecast_steps": 4}}},
        {"family": "time_series_finance", "method": "arch", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "arch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, "variant": {"variant_label": "arch_alt_window", "variant_spec": {"garch_p": 2, "garch_q": 1, "forecast_steps": 6}}},
        {"family": "time_series_finance", "method": "garch", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "garch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, "variant": {"variant_label": "garch_alt_window", "variant_spec": {"garch_p": 2, "garch_q": 1, "forecast_steps": 6}}},
        {"family": "time_series_finance", "method": "var", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "var", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "forecast_steps": 5}, "variant": {"variant_label": "var_longer_lags", "variant_spec": {"var_lags": 3, "forecast_steps": 4}}},
        {"family": "time_series_finance", "method": "svar_irf", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "svar_irf", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10, "impulse_column": "return_a", "response_column": "return_b"}, "variant": {"variant_label": "svar_alt_response", "variant_spec": {"irf_horizon": 12, "impulse_column": "return_b", "response_column": "return_c"}}},
        {"family": "time_series_finance", "method": "virf", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "virf", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "irf_horizon": 10, "virf_shock_size": 1.25}, "variant": {"variant_label": "virf_larger_shock", "variant_spec": {"irf_horizon": 12, "virf_shock_size": 1.5}}},
        {"family": "time_series_finance", "method": "dy_connectedness", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "dy_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10}, "variant": {"variant_label": "dy_longer_horizon", "variant_spec": {"var_lags": 3, "irf_horizon": 12}}},
        {"family": "time_series_finance", "method": "bk_connectedness", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "time_series_finance", "model_type": "bk_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "bk_short_horizon": 5, "bk_medium_horizon": 20}, "variant": {"variant_label": "bk_alt_bands", "variant_spec": {"var_lags": 3, "bk_short_horizon": 4, "bk_medium_horizon": 16}}},
        {"family": "risk_management", "method": "historical_var", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "risk_management", "model_type": "historical_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}, "variant": {"variant_label": "hist_var_tail", "variant_spec": {"confidence_level": 0.99, "holding_period_days": 2}}},
        {"family": "risk_management", "method": "parametric_var", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "risk_management", "model_type": "parametric_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}, "variant": {"variant_label": "param_var_tail", "variant_spec": {"confidence_level": 0.99, "holding_period_days": 2}}},
        {"family": "risk_management", "method": "ewma_volatility", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "risk_management", "model_type": "ewma_volatility", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1, "ewma_lambda": 0.94}, "variant": {"variant_label": "ewma_slow_decay", "variant_spec": {"confidence_level": 0.99, "holding_period_days": 2, "ewma_lambda": 0.97}}},
        {"family": "corporate_finance", "method": "altman_z", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "corporate_finance", "model_type": "altman_z", "working_capital_column": "working_capital", "retained_earnings_column": "retained_earnings", "ebit_column": "ebit", "market_equity_column": "market_equity", "sales_column": "sales", "total_assets_column": "total_assets", "total_liabilities_column": "total_liabilities"}, "variant": {"variant_label": "altman_stress_note", "variant_spec": {"report_variant": "liquidity_stress"}}},
        {"family": "corporate_finance", "method": "dupont", "group": "country_panel", "baseline": {"asset_id": panel_asset_id, "model_family": "corporate_finance", "model_type": "dupont", "net_income_column": "net_income", "revenue_column": "revenue", "total_assets_column": "total_assets", "equity_column": "equity"}, "variant": {"variant_label": "dupont_margin_focus", "variant_spec": {"report_variant": "margin_focus"}}},
        {"family": "derivatives_pricing", "method": "black_scholes", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "derivatives_pricing", "model_type": "black_scholes", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "call"}, "variant": {"variant_label": "bs_put", "variant_spec": {"option_type": "put"}}},
        {"family": "derivatives_pricing", "method": "binomial_option", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "derivatives_pricing", "model_type": "binomial_option", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "put", "option_steps": 40}, "variant": {"variant_label": "binomial_call", "variant_spec": {"option_type": "call", "option_steps": 60}}},
        {"family": "macro_finance_dsge", "method": "taylor_rule", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "macro_finance_dsge", "model_type": "taylor_rule", "dependent": "policy_rate", "inflation_gap_column": "inflation_gap", "output_gap_column": "output_gap"}, "variant": {"variant_label": "taylor_output_focus", "variant_spec": {"report_variant": "output_weight_focus"}}},
        {"family": "macro_finance_dsge", "method": "rbc_dsge", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "macro_finance_dsge", "model_type": "rbc_dsge", "dsge_alpha": 0.33, "dsge_beta": 0.99, "dsge_delta": 0.025, "dsge_productivity": 1.0, "dsge_labor": 0.33, "dsge_shock_persistence": 0.92, "dsge_shock_size": 0.02, "dsge_impulse_horizon": 10}, "variant": {"variant_label": "larger_dsge_shock", "variant_spec": {"dsge_shock_size": 0.03, "dsge_impulse_horizon": 12}}},
        {"family": "portfolio_allocation", "method": "mean_variance", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "portfolio_allocation", "model_type": "mean_variance", "series_columns": ["return_a", "return_b", "return_c"], "risk_aversion": 3.0, "long_only": True}, "variant": {"variant_label": "more_aggressive_mv", "variant_spec": {"risk_aversion": 2.0}}},
        {"family": "portfolio_allocation", "method": "minimum_variance", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "portfolio_allocation", "model_type": "minimum_variance", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}, "variant": {"variant_label": "min_var_audit", "variant_spec": {"report_variant": "shorting_check"}}},
        {"family": "portfolio_allocation", "method": "risk_parity", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "portfolio_allocation", "model_type": "risk_parity", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}, "variant": {"variant_label": "risk_parity_audit", "variant_spec": {"report_variant": "turnover_check"}}},
        {"family": "asset_pricing", "method": "capm", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "asset_pricing", "model_type": "capm", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate"}, "variant": {"variant_label": "capm_alpha_focus", "variant_spec": {"report_variant": "alpha_focus"}}},
        {"family": "asset_pricing", "method": "fama_french_3", "group": "macro_finance_ts", "baseline": {"asset_id": ts_asset_id, "model_family": "asset_pricing", "model_type": "fama_french_3", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate", "smb_column": "smb", "hml_column": "hml"}, "variant": {"variant_label": "ff3_factor_focus", "variant_spec": {"report_variant": "factor_loading_focus"}}},
    ]


def run_verification(output_dir: Path | None = None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-verify-full-"))
    configure_test_environment(temp_root)

    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            for name in ["country_panel", "macro_finance_ts", "model_anchor"]:
                (output_dir / name).mkdir(parents=True, exist_ok=True)

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Verifier", "email": "verifier@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Verification Lab")

        panel_frame = build_panel_dataset()
        ts_frame = build_time_series_dataset()
        panel_asset_id = upload_csv_asset(client, token, workspace_id, "panel_dataset.csv", panel_frame)
        ts_asset_id = upload_csv_asset(client, token, workspace_id, "timeseries_dataset.csv", ts_frame)
        if output_dir:
            panel_frame.to_csv(output_dir / "country_panel" / "input_panel_dataset.csv", index=False)
            ts_frame.to_csv(output_dir / "macro_finance_ts" / "input_timeseries_dataset.csv", index=False)

        panel_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{panel_asset_id}/profile", headers=auth_headers(token))
        panel_profile.raise_for_status()
        ts_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{ts_asset_id}/profile", headers=auth_headers(token))
        ts_profile.raise_for_status()
        if output_dir:
            _write_json(output_dir / "country_panel" / "panel_profile.json", panel_profile.json())
            _write_json(output_dir / "macro_finance_ts" / "timeseries_profile.json", ts_profile.json())

        guide = client.post(
            f"/api/workspaces/{workspace_id}/analysis/variable-guide",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json={"asset_id": panel_asset_id, "prompt": "I want to study whether a policy increased firm outcomes after the reform, while controlling for size and leverage."},
        )
        guide.raise_for_status()
        guide_payload = guide.json()
        if guide_payload["workflow_recommendation"]["model_type"] != "did":
            raise AssertionError("Variable guide did not identify DID on the verification prompt")
        if output_dir:
            _write_json(output_dir / "country_panel" / "variable_guide.json", guide_payload)

        prepare_template = _create_template(client, token, workspace_id, {"template_scope": "workspace", "workflow_type": "data_processing", "family": "sample_preparation", "method": "sample_preparation", "name": "Panel sample prep template", "description": "Verification sample preparation template", "is_default": True, "specification": {"workflow_group": "sample_preparation", "include_columns": ["firm_id", "date", "treated", "post", "size", "leverage", "outcome_y"], "required_columns": ["firm_id", "date", "treated", "post", "outcome_y"], "numeric_columns": ["size", "leverage", "outcome_y"], "binary_columns": ["treated", "post"], "date_columns": ["date"], "drop_duplicates": True, "drop_missing_required": True}})
        model_template = _create_template(client, token, workspace_id, {"template_scope": "workspace", "workflow_type": "model", "family": "econometrics_baseline", "method": "ols", "name": "OLS baseline template", "description": "Verification OLS template", "is_default": True, "specification": {"model_family": "econometrics_baseline", "model_type": "ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"]}})
        templates = client.get(f"/api/workspaces/{workspace_id}/lab-templates", headers=auth_headers(token))
        templates.raise_for_status()
        if output_dir:
            _write_json(output_dir / "model_anchor" / "lab_templates.json", templates.json())

        processing_runs = {
            "sample_preparation_baseline": _run_prepare(client, token, workspace_id, {"asset_id": panel_asset_id, "template_id": prepare_template["id"]}, "sample prep baseline"),
            "sample_preparation_variant": _run_prepare(client, token, workspace_id, {"asset_id": panel_asset_id, "template_id": prepare_template["id"], "variant_label": "add_endogenous", "variant_spec": {"include_columns": ["firm_id", "date", "treated", "post", "size", "leverage", "outcome_y", "endogenous_x"], "required_columns": ["firm_id", "date", "treated", "post", "outcome_y", "endogenous_x"]}}, "sample prep variant"),
            "cleaning_transforms_baseline": _run_prepare(client, token, workspace_id, {"asset_id": panel_asset_id, "workflow_group": "cleaning_transforms", "impute_method": "median", "impute_columns": ["size", "leverage"], "winsorize_columns": ["outcome_y"], "winsor_lower_quantile": 0.02, "winsor_upper_quantile": 0.98, "log_transform_columns": ["sales"], "standardize_columns": ["size", "leverage"], "outlier_columns": ["outcome_y"], "outlier_method": "iqr", "outlier_threshold": 1.5}, "cleaning baseline"),
            "cleaning_transforms_variant": _run_prepare(client, token, workspace_id, {"asset_id": panel_asset_id, "workflow_group": "cleaning_transforms", "variant_label": "minmax_variant", "variant_spec": {"impute_method": "mean", "minmax_scale_columns": ["size", "leverage"], "outlier_threshold": 1.25}, "impute_columns": ["size", "leverage"], "winsorize_columns": ["outcome_y"], "winsor_lower_quantile": 0.01, "winsor_upper_quantile": 0.99, "outlier_columns": ["outcome_y"], "outlier_method": "iqr"}, "cleaning variant"),
            "time_series_features_baseline": _run_prepare(client, token, workspace_id, {"asset_id": ts_asset_id, "workflow_group": "time_series_features", "sort_column": "date", "difference_columns": ["policy_rate"], "return_columns": ["spot_price"], "return_method": "log", "lag_columns": ["asset_return"], "lag_periods": 2, "lead_columns": ["asset_return"], "lead_periods": 1, "rolling_mean_columns": ["asset_return"], "rolling_volatility_columns": ["asset_return"], "rolling_window": 12}, "time-series baseline"),
            "time_series_features_variant": _run_prepare(client, token, workspace_id, {"asset_id": ts_asset_id, "workflow_group": "time_series_features", "variant_label": "shorter_window", "variant_spec": {"return_method": "simple", "lag_periods": 3, "lead_periods": 2, "rolling_window": 6}, "sort_column": "date", "difference_columns": ["policy_rate"], "return_columns": ["spot_price"], "lag_columns": ["asset_return"], "lead_columns": ["asset_return"], "rolling_mean_columns": ["asset_return"], "rolling_volatility_columns": ["asset_return"]}, "time-series variant"),
        }
        if output_dir:
            for key, payload in processing_runs.items():
                root = output_dir / ("macro_finance_ts" if "time_series" in key else "country_panel") / "processing" / key
                _save_result_bundle(client, token, payload["detail"], root)
                (root / "prepared_asset.csv").write_bytes(_download_asset(client, token, payload["response"]["asset"]["id"]))

        line_plot = _run_plot(client, token, workspace_id, {"asset_id": ts_asset_id, "chart_type": "line", "x_column": "date", "y_columns": ["asset_return", "market_return"], "title": "Verification line chart"}, "verification-line-chart")
        hist_plot = _run_plot(client, token, workspace_id, {"asset_id": panel_asset_id, "chart_type": "histogram", "x_column": "outcome_y", "title": "Outcome distribution"}, "outcome-distribution")
        if output_dir:
            (output_dir / "macro_finance_ts" / "plots").mkdir(parents=True, exist_ok=True)
            (output_dir / "macro_finance_ts" / "plots" / "verification_line_chart.png").write_bytes(_download_asset(client, token, line_plot["asset"]["id"]))
            (output_dir / "country_panel" / "plots").mkdir(parents=True, exist_ok=True)
            (output_dir / "country_panel" / "plots" / "outcome_distribution.png").write_bytes(_download_asset(client, token, hist_plot["asset"]["id"]))

        results: dict[str, dict[str, Any]] = {}
        for spec in _model_specs(panel_asset_id, ts_asset_id):
            label = f"{spec['family']}/{spec['method']}"
            baseline_payload = dict(spec["baseline"])
            if spec["method"] == "ols":
                baseline_payload["template_id"] = model_template["id"]
            baseline = _run_model(client, token, workspace_id, baseline_payload, f"{label} baseline")
            variant_payload = dict(spec["baseline"])
            variant_payload.update(spec["variant"])
            variant = _run_model(client, token, workspace_id, variant_payload, f"{label} variant")
            _assert_model_output(f"{label} baseline", baseline)
            _assert_model_output(f"{label} variant", variant)
            results[label] = {"group": spec["group"], "baseline": baseline, "variant": variant}

        if output_dir:
            for label, bundle in results.items():
                family, method = label.split("/", 1)
                root = output_dir / bundle["group"] / "models" / family / method
                _save_result_bundle(client, token, bundle["baseline"]["_detail_payload"], root / "baseline")
                _save_result_bundle(client, token, bundle["variant"]["_detail_payload"], root / "variant")
                _comparison_frame(bundle["baseline"], bundle["variant"]).to_csv(root / "comparison.csv", index=False)

        remote_headers = {"host": "economic-research-web.onrender.com", **auth_headers(token)}
        data_lab_page = client.get("/data-lab", headers=remote_headers)
        data_lab_page.raise_for_status()
        if "Beginner Variable Guide" not in data_lab_page.text or "Optimization Module" not in data_lab_page.text:
            raise AssertionError("Data Lab page is missing the expected guide or optimization sections")
        catalog_response = client.get("/api/data-lab/catalog", headers=remote_headers)
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
        if output_dir:
            _write_text(output_dir / "model_anchor" / "data_lab_page.html", data_lab_page.text)
            _write_json(output_dir / "model_anchor" / "data_lab_catalog.json", catalog)

        checked_method_pages = []
        for family in catalog.get("model_families", []):
            family_slug = family["slug"]
            client.get(f"/data-lab/models/{family_slug}", headers=remote_headers).raise_for_status()
            for method in family.get("methods", []):
                method_slug = method["slug"]
                method_detail = client.get(f"/api/data-lab/models/{family_slug}/{method_slug}", headers=remote_headers)
                method_detail.raise_for_status()
                payload = method_detail.json()
                if not payload["method"].get("paper_template") or "variant_presets" not in payload["method"]:
                    raise AssertionError(f"{family_slug}/{method_slug}: missing method metadata")
                teaching_detail = client.get(f"/api/data-lab/learn/models/{family_slug}/{method_slug}", headers=remote_headers)
                teaching_detail.raise_for_status()
                if not teaching_detail.json()["guide"].get("sections"):
                    raise AssertionError(f"{family_slug}/{method_slug}: missing teaching sections")
                method_page = client.get(f"/data-lab/models/{family_slug}/{method_slug}", headers=remote_headers)
                method_page.raise_for_status()
                teaching_page = client.get(f"/data-lab/learn/models/{family_slug}/{method_slug}", headers=remote_headers)
                teaching_page.raise_for_status()
                if "Paper Results Template" not in method_page.text or "Paper Table Preview" not in teaching_page.text:
                    raise AssertionError(f"{family_slug}/{method_slug}: method/teaching page lost paper reporting blocks")
                checked_method_pages.append({"family": family_slug, "method": method_slug})

        result_page = client.get(f"/data-lab/results/models/{results['econometrics_baseline/did']['baseline']['_record_id']}", headers=remote_headers)
        result_page.raise_for_status()
        if "Interpretation &amp; Replication" not in result_page.text and "Interpretation & Replication" not in result_page.text:
            raise AssertionError("Result detail page is missing the interpretation section")
        if output_dir:
            _write_text(output_dir / "model_anchor" / "sample_result_page.html", result_page.text)

        report = {
            "status": "passed",
            "workspace_id": workspace_id,
            "panel_asset_id": panel_asset_id,
            "timeseries_asset_id": ts_asset_id,
            "processing_run_count": len(processing_runs),
            "model_count": len(results),
            "checked_method_pages": len(checked_method_pages),
            "model_anchor_rows": [
                {
                    "label": label,
                    "group": bundle["group"],
                    "baseline_record_id": bundle["baseline"]["_record_id"],
                    "variant_record_id": bundle["variant"]["_record_id"],
                    "baseline_figures": len(bundle["baseline"].get("figures", [])),
                    "variant_figures": len(bundle["variant"].get("figures", [])),
                    "baseline_table_count": len((bundle["baseline"].get("tables") or {}).keys()),
                    "variant_table_count": len((bundle["variant"].get("tables") or {}).keys()),
                }
                for label, bundle in results.items()
            ],
        }
        if output_dir:
            _write_json(output_dir / "model_anchor" / "model_anchor_report.json", report["model_anchor_rows"])
            _write_json(output_dir / "verification_report.json", report)
        return report
    finally:
        client.close()


def main() -> None:
    report = run_verification()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
