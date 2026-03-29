from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-data-lab-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-data-lab-encryption"
    os.environ["CRON_SECRET"] = "verify-data-lab-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"


def build_panel_dataset() -> pd.DataFrame:
    rng = np.random.default_rng(20260329)
    firms = [f"firm_{idx:02d}" for idx in range(1, 19)]
    periods = pd.date_range("2018-01-31", periods=36, freq="ME")
    rows: list[dict[str, float | int | str]] = []
    policy_start = 18
    for firm_index, firm in enumerate(firms):
        treated = 1 if firm_index < len(firms) // 2 else 0
        firm_effect = rng.normal(scale=0.5)
        for t_index, current_date in enumerate(periods):
            post = 1 if t_index >= policy_start else 0
            event_time = t_index - policy_start
            size = 8.0 + 0.03 * t_index + 0.12 * firm_index + rng.normal(scale=0.25)
            leverage = 0.35 + 0.01 * (firm_index % 5) + rng.normal(scale=0.03)
            profitability = 0.08 + 0.004 * np.sin(t_index / 4) + rng.normal(scale=0.015)
            instrument = rng.normal(loc=0.2 * post, scale=0.9)
            structural_error = rng.normal(scale=0.5)
            endogenous_x = 0.75 * instrument + 0.35 * structural_error + rng.normal(scale=0.35)
            running_score = rng.uniform(-1.5, 1.5) + 0.15 * treated
            jump = 1.1 if running_score >= 0 else 0.0
            did_effect = 1.35 * treated * post
            outcome = (
                2.0
                + 0.65 * size
                - 1.8 * leverage
                + 0.55 * endogenous_x
                + 0.08 * t_index
                + did_effect
                + jump
                + firm_effect
                + structural_error
            )
            latent_default = -0.2 + 1.4 * leverage - 0.09 * size + 0.45 * treated + 0.18 * post + rng.normal(scale=0.45)
            default_probability = 1.0 / (1.0 + np.exp(-latent_default))
            binary_outcome = int(rng.random() < default_probability)
            origin_gdp = np.exp(8.8 + 0.025 * firm_index + rng.normal(scale=0.05))
            destination_gdp = np.exp(8.5 + 0.015 * t_index + rng.normal(scale=0.05))
            distance_km = np.exp(6.2 + 0.03 * (firm_index % 6) + rng.normal(scale=0.06))
            gravity_noise = rng.normal(scale=0.18)
            export_flow = np.exp(
                0.55 * np.log(origin_gdp)
                + 0.45 * np.log(destination_gdp)
                - 0.72 * np.log(distance_km)
                + 0.16 * post
                + gravity_noise
            ) - 1.0
            total_assets = np.exp(size) * 100.0
            total_liabilities = total_assets * (0.42 + 0.03 * rng.random())
            market_equity = total_assets * (0.65 + 0.05 * rng.random())
            retained_earnings = total_assets * (0.08 + 0.03 * profitability)
            working_capital = total_assets * (0.12 + 0.02 * rng.random())
            ebit = total_assets * (0.065 + 0.02 * profitability)
            sales = total_assets * (0.72 + 0.05 * rng.random())
            revenue = sales
            net_income = revenue * profitability
            equity = total_assets - total_liabilities
            rows.append(
                {
                    "firm_id": firm,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "calendar_year": current_date.year,
                    "month_index": t_index + 1,
                    "treated": treated,
                    "post": post,
                    "event_time": event_time,
                    "size": float(size),
                    "leverage": float(leverage),
                    "instrument_z": float(instrument),
                    "endogenous_x": float(endogenous_x),
                    "outcome_y": float(outcome),
                    "binary_outcome": binary_outcome,
                    "running_score": float(running_score),
                    "export_flow": float(max(export_flow, 0.0)),
                    "origin_gdp": float(origin_gdp),
                    "destination_gdp": float(destination_gdp),
                    "distance_km": float(distance_km),
                    "working_capital": float(working_capital),
                    "retained_earnings": float(retained_earnings),
                    "ebit": float(ebit),
                    "market_equity": float(market_equity),
                    "sales": float(sales),
                    "total_assets": float(total_assets),
                    "total_liabilities": float(total_liabilities),
                    "net_income": float(net_income),
                    "revenue": float(revenue),
                    "equity": float(equity),
                }
            )
    return pd.DataFrame(rows)


def build_time_series_dataset() -> pd.DataFrame:
    rng = np.random.default_rng(20260330)
    dates = pd.date_range("2005-01-31", periods=240, freq="ME")
    n = len(dates)
    epsilon = rng.normal(size=(n, 3))
    h = np.zeros(n)
    asset_return = np.zeros(n)
    return_a = np.zeros(n)
    return_b = np.zeros(n)
    return_c = np.zeros(n)
    market_return = np.zeros(n)
    smb = np.zeros(n)
    hml = np.zeros(n)
    inflation_gap = np.zeros(n)
    output_gap = np.zeros(n)
    policy_rate = np.zeros(n)

    h[0] = 0.04
    asset_return[0] = np.sqrt(h[0]) * epsilon[0, 0]
    return_a[0], return_b[0], return_c[0] = epsilon[0]
    market_return[0] = 0.6 * asset_return[0] + rng.normal(scale=0.02)
    smb[0] = rng.normal(scale=0.02)
    hml[0] = rng.normal(scale=0.02)
    inflation_gap[0] = rng.normal(scale=0.3)
    output_gap[0] = rng.normal(scale=0.25)
    policy_rate[0] = 2.0 + 1.25 * inflation_gap[0] + 0.6 * output_gap[0] + rng.normal(scale=0.08)

    for t in range(1, n):
        h[t] = max(0.01, 0.02 + 0.14 * asset_return[t - 1] ** 2 + 0.78 * h[t - 1])
        asset_return[t] = 0.15 * asset_return[t - 1] + np.sqrt(h[t]) * epsilon[t, 0]
        return_a[t] = 0.42 * return_a[t - 1] + 0.16 * return_b[t - 1] + epsilon[t, 0] * 0.04
        return_b[t] = 0.28 * return_a[t - 1] + 0.38 * return_b[t - 1] + 0.12 * return_c[t - 1] + epsilon[t, 1] * 0.035
        return_c[t] = 0.18 * return_b[t - 1] + 0.36 * return_c[t - 1] + epsilon[t, 2] * 0.03
        market_return[t] = 0.72 * asset_return[t] + 0.18 * return_a[t] + rng.normal(scale=0.015)
        smb[t] = 0.35 * smb[t - 1] + rng.normal(scale=0.02)
        hml[t] = 0.32 * hml[t - 1] + rng.normal(scale=0.018)
        inflation_gap[t] = 0.68 * inflation_gap[t - 1] + rng.normal(scale=0.22)
        output_gap[t] = 0.51 * output_gap[t - 1] + rng.normal(scale=0.2)
        policy_rate[t] = (
            0.45 * policy_rate[t - 1]
            + 1.35 * inflation_gap[t]
            + 0.7 * output_gap[t]
            + rng.normal(scale=0.06)
        )

    spot_price = 100 * np.exp(np.cumsum(0.01 + asset_return / 10))
    strike_price = spot_price * 0.98
    time_to_maturity = np.linspace(0.2, 1.5, n)
    risk_free_rate = np.full(n, 0.02) + 0.002 * np.sin(np.arange(n) / 8)
    implied_vol = np.sqrt(h)

    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "asset_return": asset_return,
            "market_return": market_return,
            "smb": smb,
            "hml": hml,
            "risk_free_rate": risk_free_rate,
            "return_a": return_a,
            "return_b": return_b,
            "return_c": return_c,
            "policy_rate": policy_rate,
            "inflation_gap": inflation_gap,
            "output_gap": output_gap,
            "spot_price": spot_price,
            "strike_price": strike_price,
            "time_to_maturity": time_to_maturity,
            "implied_vol": implied_vol,
        }
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_png_response(response, label: str) -> None:
    if response.status_code != 200:
        raise AssertionError(f"{label}: download failed with {response.status_code}")
    if not response.content.startswith(b"\x89PNG"):
        raise AssertionError(f"{label}: response is not a PNG asset")


def create_workspace(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/workspaces",
        json={"name": name, "description": "Verification workspace", "research_domain": "economics"},
        headers=auth_headers(token),
    )
    response.raise_for_status()
    return response.json()["workspace"]["id"]


def upload_csv_asset(client: TestClient, token: str, workspace_id: str, filename: str, frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False).encode("utf-8")
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(payload), "text/csv")},
        data={"description": filename, "source_url": ""},
    )
    response.raise_for_status()
    return response.json()["asset"]["id"]


def run_prepare(client: TestClient, token: str, workspace_id: str, payload: dict, label: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("asset", {}).get("id"):
        raise AssertionError(f"{label}: missing prepared asset id")
    return data


def run_plot(client: TestClient, token: str, workspace_id: str, payload: dict, label: str) -> dict:
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
    assert_png_response(download, label)
    return data


def run_model(client: TestClient, token: str, workspace_id: str, payload: dict, label: str, *, expect_figure: bool = False) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    if response.status_code >= 400:
        raise AssertionError(f"{label}: {response.status_code} {response.text}")
    data = response.json()
    record_id = data.get("result_record_id")
    if not record_id:
        raise AssertionError(f"{label}: missing result_record_id")
    detail = client.get(f"/api/data-lab/results/models/{record_id}", headers=auth_headers(token))
    detail.raise_for_status()
    detail_payload = detail.json()
    result = detail_payload["result"]
    result["_record_id"] = record_id
    if expect_figure:
        figures = result.get("figures", [])
        if not figures:
            raise AssertionError(f"{label}: expected a figure but none were returned")
        for figure in figures:
            download = client.get(f"/api/assets/{figure['asset_id']}/download", headers=auth_headers(token))
            assert_png_response(download, f"{label} figure")
    return result


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-verify-"))
    configure_test_environment(temp_root)

    from research_agent.webapp import create_app

    client = TestClient(create_app())

    try:
        register = client.post(
            "/api/auth/register",
            json={"full_name": "Verifier", "email": "verifier@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Verification Lab")

        panel_asset_id = upload_csv_asset(client, token, workspace_id, "panel_dataset.csv", build_panel_dataset())
        ts_asset_id = upload_csv_asset(client, token, workspace_id, "timeseries_dataset.csv", build_time_series_dataset())

        panel_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{panel_asset_id}/profile", headers=auth_headers(token))
        panel_profile.raise_for_status()
        ts_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{ts_asset_id}/profile", headers=auth_headers(token))
        ts_profile.raise_for_status()

        variable_guide = client.post(
            f"/api/workspaces/{workspace_id}/analysis/variable-guide",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json={
                "asset_id": panel_asset_id,
                "prompt": "I want to study whether a policy increased firm outcomes after the reform, while controlling for size and leverage.",
            },
        )
        variable_guide.raise_for_status()
        guide_payload = variable_guide.json()
        if guide_payload["workflow_recommendation"]["model_type"] != "did":
            raise AssertionError("Variable guide did not identify the DID-style design on the verification prompt")
        if not guide_payload.get("suggested_roles"):
            raise AssertionError("Variable guide returned no suggested roles")

        processing_runs = {
            "sample_preparation": run_prepare(
                client,
                token,
                workspace_id,
                {
                    "asset_id": panel_asset_id,
                    "workflow_group": "sample_preparation",
                    "include_columns": ["firm_id", "date", "treated", "post", "size", "leverage", "outcome_y"],
                    "required_columns": ["firm_id", "date", "treated", "post", "outcome_y"],
                    "numeric_columns": ["size", "leverage", "outcome_y"],
                    "binary_columns": ["treated", "post"],
                    "date_columns": ["date"],
                    "drop_duplicates": True,
                    "drop_missing_required": True,
                },
                "sample preparation",
            ),
            "cleaning_transforms": run_prepare(
                client,
                token,
                workspace_id,
                {
                    "asset_id": panel_asset_id,
                    "workflow_group": "cleaning_transforms",
                    "impute_method": "median",
                    "impute_columns": ["size", "leverage"],
                    "winsorize_columns": ["outcome_y"],
                    "winsor_lower": 0.02,
                    "winsor_upper": 0.98,
                    "log_transform_columns": ["sales"],
                    "standardize_columns": ["size", "leverage"],
                    "outlier_columns": ["outcome_y"],
                    "outlier_method": "iqr",
                    "outlier_threshold": 1.5,
                },
                "cleaning transforms",
            ),
            "time_series_features": run_prepare(
                client,
                token,
                workspace_id,
                {
                    "asset_id": ts_asset_id,
                    "workflow_group": "time_series_features",
                    "sort_column": "date",
                    "difference_columns": ["policy_rate"],
                    "return_columns": ["spot_price"],
                    "return_method": "log",
                    "lag_columns": ["asset_return"],
                    "lag_periods": 2,
                    "lead_columns": ["asset_return"],
                    "lead_periods": 1,
                    "rolling_mean_columns": ["asset_return"],
                    "rolling_volatility_columns": ["asset_return"],
                    "rolling_window": 12,
                },
                "time-series features",
            ),
        }

        for label, run in processing_runs.items():
            processing_asset_id = run["asset"]["id"]
            detail = client.get(f"/api/data-lab/results/processing/{processing_asset_id}", headers=auth_headers(token))
            detail.raise_for_status()
            if detail.json()["result"]["workflow_type"] != "data_processing":
                raise AssertionError(f"{label}: processing detail route did not return a processing result")

        plot_result = run_plot(
            client,
            token,
            workspace_id,
            {
                "asset_id": ts_asset_id,
                "chart_type": "line",
                "x_column": "date",
                "y_columns": ["asset_return", "market_return"],
                "group_column": "",
                "title": "Verification line chart",
            },
            "line chart",
        )
        if plot_result.get("asset", {}).get("kind") not in {"plot_png", "chart_png"}:
            raise AssertionError("Visualization route did not save a plot asset")

        model_specs = [
            ("OLS", {"asset_id": panel_asset_id, "model_type": "ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"]}, False),
            ("PPML", {"asset_id": panel_asset_id, "model_type": "ppml", "dependent": "export_flow", "independents": ["size", "leverage"], "controls": ["post"]}, False),
            ("Logit", {"asset_id": panel_asset_id, "model_type": "logit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}, False),
            ("Probit", {"asset_id": panel_asset_id, "model_type": "probit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}, False),
            ("DID", {"asset_id": panel_asset_id, "model_type": "did", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "post_column": "post"}, False),
            ("Event Study", {"asset_id": panel_asset_id, "model_type": "event_study", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "event_time_column": "event_time", "entity_column": "firm_id", "time_column": "date", "include_time_effects": True, "lead_window": 4, "lag_window": 4, "omitted_period": -1}, True),
            ("RDD", {"asset_id": panel_asset_id, "model_type": "rdd", "dependent": "outcome_y", "controls": ["size"], "running_column": "running_score", "rdd_cutoff": 0.0, "rdd_bandwidth": 1.1, "rdd_polynomial_order": 2, "treat_above_cutoff": True}, True),
            ("Fixed Effects", {"asset_id": panel_asset_id, "model_type": "fixed_effects", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}, False),
            ("Gravity", {"asset_id": panel_asset_id, "model_type": "gravity", "dependent": "export_flow", "origin_mass_column": "origin_gdp", "destination_mass_column": "destination_gdp", "distance_column": "distance_km", "controls": ["post"]}, False),
            ("IV-2SLS", {"asset_id": panel_asset_id, "model_type": "iv_2sls", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}, False),
            ("Panel IV", {"asset_id": panel_asset_id, "model_type": "panel_iv", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}, False),
            ("ARIMA", {"asset_id": ts_asset_id, "model_type": "arima", "dependent": "policy_rate", "time_column": "date", "arima_p": 1, "arima_d": 0, "arima_q": 1, "forecast_steps": 6}, False),
            ("ARCH", {"asset_id": ts_asset_id, "model_type": "arch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, True),
            ("GARCH", {"asset_id": ts_asset_id, "model_type": "garch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}, True),
            ("VAR", {"asset_id": ts_asset_id, "model_type": "var", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "forecast_steps": 5}, False),
            ("SVAR IRF", {"asset_id": ts_asset_id, "model_type": "svar_irf", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10, "impulse_column": "return_a", "response_column": "return_b"}, True),
            ("VIRF", {"asset_id": ts_asset_id, "model_type": "virf", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "irf_horizon": 10, "virf_shock_size": 1.25}, True),
            ("DY Connectedness", {"asset_id": ts_asset_id, "model_type": "dy_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10}, True),
            ("BK Connectedness", {"asset_id": ts_asset_id, "model_type": "bk_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "bk_short_horizon": 5, "bk_medium_horizon": 20}, True),
            ("Historical VaR", {"asset_id": ts_asset_id, "model_type": "historical_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}, False),
            ("Parametric VaR", {"asset_id": ts_asset_id, "model_type": "parametric_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}, False),
            ("EWMA Volatility", {"asset_id": ts_asset_id, "model_type": "ewma_volatility", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1, "ewma_lambda": 0.94}, False),
            ("Altman Z", {"asset_id": panel_asset_id, "model_type": "altman_z", "working_capital_column": "working_capital", "retained_earnings_column": "retained_earnings", "ebit_column": "ebit", "market_equity_column": "market_equity", "sales_column": "sales", "total_assets_column": "total_assets", "total_liabilities_column": "total_liabilities"}, False),
            ("DuPont", {"asset_id": panel_asset_id, "model_type": "dupont", "net_income_column": "net_income", "revenue_column": "revenue", "total_assets_column": "total_assets", "equity_column": "equity"}, False),
            ("Black-Scholes", {"asset_id": ts_asset_id, "model_type": "black_scholes", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "call"}, False),
            ("Binomial Option", {"asset_id": ts_asset_id, "model_type": "binomial_option", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "put", "option_steps": 40}, False),
            ("Taylor Rule", {"asset_id": ts_asset_id, "model_type": "taylor_rule", "dependent": "policy_rate", "inflation_gap_column": "inflation_gap", "output_gap_column": "output_gap"}, False),
            ("Toy RBC / DSGE", {"asset_id": ts_asset_id, "model_type": "rbc_dsge", "dsge_alpha": 0.33, "dsge_beta": 0.99, "dsge_delta": 0.025, "dsge_productivity": 1.0, "dsge_labor": 0.33, "dsge_shock_persistence": 0.92, "dsge_shock_size": 0.02, "dsge_impulse_horizon": 10}, False),
            ("Mean-Variance", {"asset_id": ts_asset_id, "model_type": "mean_variance", "series_columns": ["return_a", "return_b", "return_c"], "risk_aversion": 3.0, "long_only": True}, False),
            ("Minimum Variance", {"asset_id": ts_asset_id, "model_type": "minimum_variance", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}, False),
            ("Risk Parity", {"asset_id": ts_asset_id, "model_type": "risk_parity", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}, False),
            ("CAPM", {"asset_id": ts_asset_id, "model_type": "capm", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate"}, False),
            ("Fama-French 3", {"asset_id": ts_asset_id, "model_type": "fama_french_3", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate", "smb_column": "smb", "hml_column": "hml"}, False),
        ]

        results: dict[str, dict] = {}
        for label, payload, expect_figure in model_specs:
            print(f"Running model verification: {label}")
            try:
                results[label] = run_model(client, token, workspace_id, payload, label, expect_figure=expect_figure)
            except Exception as exc:  # pragma: no cover - verification script
                raise AssertionError(f"{label} failed verification: {exc}") from exc

        did_result = results["DID"]
        if not any(row.get("term") == "did_interaction" for row in did_result.get("coefficients", [])):
            raise AssertionError("DID did not return the interaction term in the coefficient table")
        if len(did_result.get("cell_means", [])) < 4:
            raise AssertionError("DID did not return the 2x2 cell means table")

        svar_result = results["SVAR IRF"]
        if not svar_result.get("tables", {}).get("irf_table"):
            raise AssertionError("SVAR IRF did not return the impulse-response table")
        if len(svar_result.get("figures", [])) < 2:
            raise AssertionError("SVAR IRF did not return both orthogonalized and cumulative IRF figures")

        bk_result = results["BK Connectedness"]
        band_rows = bk_result.get("tables", {}).get("band_total_connectedness", [])
        if len(band_rows) < 3:
            raise AssertionError("BK connectedness did not return short/medium/long band summaries")
        if len(bk_result.get("figures", [])) < 2:
            raise AssertionError("BK connectedness did not return both the heatmap and band-summary figures")

        dydetail = results["DY Connectedness"].get("tables", {}).get("connectedness_matrix", [])
        if not dydetail:
            raise AssertionError("DY connectedness did not return a connectedness matrix")
        if len(results["DY Connectedness"].get("figures", [])) < 2:
            raise AssertionError("DY connectedness did not return both heatmap and directional-spillover figures")

        if len(results["GARCH"].get("figures", [])) < 2:
            raise AssertionError("GARCH did not return both in-sample and forecast-volatility figures")
        if len(results["ARCH"].get("figures", [])) < 2:
            raise AssertionError("ARCH did not return both in-sample and forecast-volatility figures")
        if len(results["VAR"].get("figures", [])) < 1:
            raise AssertionError("VAR did not return a forecast figure")
        if len(results["ARIMA"].get("figures", [])) < 1:
            raise AssertionError("ARIMA did not return a forecast figure")
        if len(results["VIRF"].get("figures", [])) < 2:
            raise AssertionError("VIRF did not return both volatility and variance response figures")

        if not results["DID"].get("interpretation", {}).get("sections"):
            raise AssertionError("DID result detail is missing interpretation metadata")
        if not results["SVAR IRF"].get("interpretation", {}).get("sections"):
            raise AssertionError("SVAR IRF result detail is missing interpretation metadata")

        home = client.get("/")
        home.raise_for_status()
        data_lab_page = client.get("/data-lab")
        data_lab_page.raise_for_status()
        if "Beginner Variable Guide" not in data_lab_page.text:
            raise AssertionError("Standalone Data Lab page is missing the beginner guide section")
        if "Time Series &amp; Econometric Finance" not in data_lab_page.text and "Time Series & Econometric Finance" not in data_lab_page.text:
            raise AssertionError("Standalone Data Lab page is missing the expanded time-series family section")

        catalog_response = client.get("/api/data-lab/catalog")
        catalog_response.raise_for_status()
        catalog_payload = catalog_response.json()
        for family in catalog_payload.get("model_families", []):
            family_slug = family["slug"]
            family_page = client.get(f"/data-lab/models/{family_slug}")
            family_page.raise_for_status()
            for method in family.get("methods", []):
                method_slug = method["slug"]
                method_detail = client.get(f"/api/data-lab/models/{family_slug}/{method_slug}")
                method_detail.raise_for_status()
                if method_detail.json()["method"]["slug"] != method_slug:
                    raise AssertionError(f"{family_slug}/{method_slug}: model detail route returned the wrong method payload")
                teaching_detail = client.get(f"/api/data-lab/learn/models/{family_slug}/{method_slug}")
                teaching_detail.raise_for_status()
                if not teaching_detail.json()["guide"].get("sections"):
                    raise AssertionError(f"{family_slug}/{method_slug}: teaching route returned no teaching sections")
                method_page = client.get(f"/data-lab/models/{family_slug}/{method_slug}")
                method_page.raise_for_status()
                if "lab-model-method-title" not in method_page.text:
                    raise AssertionError(f"{family_slug}/{method_slug}: method page template failed to load")
                teaching_page = client.get(f"/data-lab/learn/models/{family_slug}/{method_slug}")
                teaching_page.raise_for_status()
                if "lab-teaching-sections" not in teaching_page.text:
                    raise AssertionError(f"{family_slug}/{method_slug}: teaching page template failed to load")

        result_page = client.get(f"/data-lab/results/models/{results['DID']['_record_id']}")
        result_page.raise_for_status()
        if "Interpretation &amp; Replication" not in result_page.text and "Interpretation & Replication" not in result_page.text:
            raise AssertionError("Result detail page is missing the interpretation section")

        print("All Data Lab verification checks passed.")
        print(f"Workspace: {workspace_id}")
        print(f"Panel asset: {panel_asset_id}")
        print(f"Time-series asset: {ts_asset_id}")
        print(f"Models verified: {len(model_specs)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
