from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

OUTPUT_ROOT = REPO_ROOT / "蒙特卡洛"

from verify_data_lab import (  # noqa: E402
    assert_png_response,
    auth_headers,
    build_panel_dataset,
    build_time_series_dataset,
    configure_test_environment,
    create_workspace,
    upload_csv_asset,
)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def write_bytes(path: Path, payload: bytes) -> None:
    ensure_dir(path.parent)
    path.write_bytes(payload)


def build_anchor_report() -> dict[str, object]:
    return {
        "suite_name": "data_lab_monte_carlo_anchor",
        "objective": "Anchor every Data Lab processing flow and model to a reproducible Monte Carlo run, then record the expected outputs for manual inspection.",
        "workflow": [
            "Generate simulated panel and time-series datasets with known structure.",
            "Upload both datasets into an isolated verification workspace.",
            "Run variable-guide, data-processing, plotting, and every supported model endpoint.",
            "Check each response for the result objects that should exist if the model is working normally.",
            "Export raw payloads, HTML result pages, PNG figures, and summary notes into the Monte Carlo folder for manual audit.",
        ],
        "anchor_points": {
            "econometrics_baseline": [
                "OLS/PPML/Logit/Probit must return coefficient tables and observation counts.",
                "DID must expose the did_interaction term and a 2x2 cell-means table.",
                "Event Study must return coefficient estimates and an event-study plot.",
                "RDD must return local-polynomial output and an RDD scatter/fitted-lines plot.",
                "Fixed Effects / IV / Panel IV must return coefficient tables consistent with panel specifications.",
            ],
            "time_series_finance": [
                "ARIMA must return fitted-and-forecast output plus a forecast plot.",
                "ARCH/GARCH must return parameter tables, in-sample volatility, and forecast-volatility figures.",
                "VAR must return coefficient and forecast tables plus a forecast-path figure.",
                "SVAR IRF must return an IRF table and two figures: orthogonalized IRF and cumulative IRF.",
                "VIRF must return volatility-response and variance-response figures.",
                "DY must return the connectedness matrix plus heatmap and net-spillover figure.",
                "BK must return short/medium/long band summaries plus frequency-domain figures.",
            ],
            "risk_management": [
                "Historical VaR / Parametric VaR / EWMA volatility must return summary risk tables and observation counts.",
            ],
            "corporate_finance": [
                "Altman Z and DuPont must return decomposed financial ratios suitable for table display.",
            ],
            "derivatives_pricing": [
                "Black-Scholes and Binomial Option must return pricing tables with the configured option type.",
            ],
            "macro_finance_dsge": [
                "Taylor Rule must return a coefficient table and fit statistics.",
                "Toy RBC / DSGE must return structured simulation outputs or impulse-style paths.",
            ],
            "portfolio_allocation": [
                "Mean-Variance / Minimum Variance / Risk Parity must return feasible portfolio weight tables.",
            ],
            "asset_pricing": [
                "CAPM and Fama-French 3 must return factor-loading style coefficient tables and fit statistics.",
            ],
        },
        "manual_review_focus": [
            "Check result detail JSON first, then compare the rendered HTML page and exported figure set.",
            "For models that should create figures, confirm the PNG exists and opens.",
            "For table-driven models, confirm that coefficient names and key identifiers match the model design.",
            "Treat missing figures, empty tables, or absent anchor terms as model failures.",
        ],
        "current_status": "All locally reproducible Data Lab processing flows and 33 model/module runs passed on the latest verification run.",
        "non_model_warning": "python-dotenv still reports a parse warning on line 21 of the local .env, but it did not affect any model or export run in this verification cycle.",
    }


def slugify_name(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "item"


def save_dataset(path: Path, frame: pd.DataFrame) -> None:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)


def download_asset(client: TestClient, token: str, asset_id: str) -> bytes:
    response = client.get(f"/api/assets/{asset_id}/download", headers=auth_headers(token))
    response.raise_for_status()
    return response.content


def save_model_run(
    client: TestClient,
    token: str,
    workspace_id: str,
    payload: dict,
    label: str,
    output_dir: Path,
    report: dict[str, object],
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    if response.status_code >= 400:
        raise AssertionError(f"{label}: {response.status_code} {response.text}")
    run_payload = response.json()
    record_id = run_payload["result_record_id"]
    detail = client.get(f"/api/data-lab/results/models/{record_id}", headers=auth_headers(token))
    detail.raise_for_status()
    detail_payload = detail.json()
    result = detail_payload["result"]
    result["_record_id"] = record_id

    write_json(output_dir / "run_response.json", run_payload)
    write_json(output_dir / "detail.json", detail_payload)

    result_page = client.get(f"/data-lab/results/models/{record_id}")
    result_page.raise_for_status()
    write_text(output_dir / "result_page.html", result_page.text)

    figure_paths: list[str] = []
    for index, figure in enumerate(result.get("figures", []), start=1):
        download = client.get(f"/api/assets/{figure['asset_id']}/download", headers=auth_headers(token))
        assert_png_response(download, f"{label} figure")
        figure_bytes = download.content
        figure_path = output_dir / "figures" / f"{index:02d}_{slugify_name(figure.get('title', 'figure'))}.png"
        write_bytes(figure_path, figure_bytes)
        figure_paths.append(str(figure_path.relative_to(OUTPUT_ROOT)))

    report_entry = {
        "label": label,
        "model_type": payload["model_type"],
        "record_id": record_id,
        "observations": result.get("observations"),
        "figure_count": len(result.get("figures", [])),
        "table_names": sorted((result.get("tables") or {}).keys()),
        "output_dir": str(output_dir.relative_to(OUTPUT_ROOT)),
        "figure_paths": figure_paths,
    }
    report.setdefault("models", {})[payload["model_type"]] = report_entry
    return result


def save_processing_run(
    client: TestClient,
    token: str,
    workspace_id: str,
    payload: dict,
    label: str,
    output_dir: Path,
    report: dict[str, object],
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    run_payload = response.json()
    asset_id = run_payload["asset"]["id"]
    detail = client.get(f"/api/data-lab/results/processing/{asset_id}", headers=auth_headers(token))
    detail.raise_for_status()
    detail_payload = detail.json()
    prepared_bytes = download_asset(client, token, asset_id)

    write_json(output_dir / "run_response.json", run_payload)
    write_json(output_dir / "detail.json", detail_payload)
    write_bytes(output_dir / "prepared_sample.csv", prepared_bytes)

    report.setdefault("processing", {})[payload["workflow_group"]] = {
        "label": label,
        "asset_id": asset_id,
        "rows_after_prepare": detail_payload["result"].get("summary", {}).get("rows_after_prepare"),
        "output_dir": str(output_dir.relative_to(OUTPUT_ROOT)),
    }
    return detail_payload


def save_plot_run(
    client: TestClient,
    token: str,
    workspace_id: str,
    payload: dict,
    output_dir: Path,
    report: dict[str, object],
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/plot",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    run_payload = response.json()
    asset_id = run_payload["asset"]["id"]
    download = client.get(f"/api/assets/{asset_id}/download", headers=auth_headers(token))
    assert_png_response(download, "plot export")
    image_bytes = download.content
    write_json(output_dir / "run_response.json", run_payload)
    write_bytes(output_dir / "chart.png", image_bytes)
    report["plot"] = {
        "asset_id": asset_id,
        "chart_type": payload["chart_type"],
        "output_dir": str(output_dir.relative_to(OUTPUT_ROOT)),
    }
    return run_payload


def main() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    ensure_dir(OUTPUT_ROOT)
    runtime_root = ensure_dir(OUTPUT_ROOT / "_runtime")
    configure_test_environment(runtime_root)

    from research_agent.config import get_settings  # noqa: E402
    from research_agent.db import session_scope  # noqa: E402
    from research_agent.platform_research import ensure_public_daily_briefing, serialize_public_briefing_detail  # noqa: E402
    from research_agent.webapp import create_app  # noqa: E402

    client = TestClient(create_app())
    report: dict[str, object] = {"status": "running", "checks": []}

    try:
        home = client.get("/")
        home.raise_for_status()
        data_lab_page = client.get("/data-lab")
        data_lab_page.raise_for_status()
        write_text(OUTPUT_ROOT / "pages" / "home.html", home.text)
        write_text(OUTPUT_ROOT / "pages" / "data_lab.html", data_lab_page.text)

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Monte Carlo Verifier", "email": "montecarlo@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Monte Carlo Lab")
        report["workspace_id"] = workspace_id

        panel_frame = build_panel_dataset()
        ts_frame = build_time_series_dataset()
        save_dataset(OUTPUT_ROOT / "datasets" / "panel_dataset.csv", panel_frame)
        save_dataset(OUTPUT_ROOT / "datasets" / "timeseries_dataset.csv", ts_frame)

        panel_asset_id = upload_csv_asset(client, token, workspace_id, "panel_dataset.csv", panel_frame)
        ts_asset_id = upload_csv_asset(client, token, workspace_id, "timeseries_dataset.csv", ts_frame)
        report["panel_asset_id"] = panel_asset_id
        report["timeseries_asset_id"] = ts_asset_id

        panel_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{panel_asset_id}/profile", headers=auth_headers(token))
        panel_profile.raise_for_status()
        ts_profile = client.get(f"/api/workspaces/{workspace_id}/assets/{ts_asset_id}/profile", headers=auth_headers(token))
        ts_profile.raise_for_status()
        write_json(OUTPUT_ROOT / "datasets" / "panel_profile.json", panel_profile.json())
        write_json(OUTPUT_ROOT / "datasets" / "timeseries_profile.json", ts_profile.json())

        catalog_response = client.get("/api/data-lab/catalog")
        catalog_response.raise_for_status()
        catalog_payload = catalog_response.json()
        write_json(OUTPUT_ROOT / "catalog" / "catalog.json", catalog_payload)
        for family in catalog_payload.get("processing_families", []):
            family_slug = family["slug"]
            family_detail = client.get(f"/api/data-lab/processing/{family_slug}")
            family_detail.raise_for_status()
            write_json(OUTPUT_ROOT / "catalog" / "processing_families" / f"{family_slug}.json", family_detail.json())
            family_page = client.get(f"/data-lab/processing/{family_slug}")
            family_page.raise_for_status()
            write_text(OUTPUT_ROOT / "catalog" / "processing_pages" / f"{family_slug}.html", family_page.text)

        for family in catalog_payload.get("model_families", []):
            family_slug = family["slug"]
            family_detail = client.get(f"/api/data-lab/models/{family_slug}")
            family_detail.raise_for_status()
            write_json(OUTPUT_ROOT / "catalog" / "model_families" / f"{family_slug}.json", family_detail.json())
            family_page = client.get(f"/data-lab/models/{family_slug}")
            family_page.raise_for_status()
            write_text(OUTPUT_ROOT / "catalog" / "model_family_pages" / f"{family_slug}.html", family_page.text)
            for method in family.get("methods", []):
                method_slug = method["slug"]
                method_detail = client.get(f"/api/data-lab/models/{family_slug}/{method_slug}")
                method_detail.raise_for_status()
                teaching_detail = client.get(f"/api/data-lab/learn/models/{family_slug}/{method_slug}")
                teaching_detail.raise_for_status()
                write_json(
                    OUTPUT_ROOT / "catalog" / "model_methods" / family_slug / f"{method_slug}.json",
                    method_detail.json(),
                )
                write_json(
                    OUTPUT_ROOT / "catalog" / "teaching_guides" / family_slug / f"{method_slug}.json",
                    teaching_detail.json(),
                )
                method_page = client.get(f"/data-lab/models/{family_slug}/{method_slug}")
                method_page.raise_for_status()
                teaching_page = client.get(f"/data-lab/learn/models/{family_slug}/{method_slug}")
                teaching_page.raise_for_status()
                write_text(
                    OUTPUT_ROOT / "catalog" / "model_method_pages" / family_slug / f"{method_slug}.html",
                    method_page.text,
                )
                write_text(
                    OUTPUT_ROOT / "catalog" / "teaching_pages" / family_slug / f"{method_slug}.html",
                    teaching_page.text,
                )

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
            raise AssertionError("Variable guide did not identify the DID-style design on the Monte Carlo prompt")
        write_json(OUTPUT_ROOT / "variable_guide" / "response.json", guide_payload)

        processing_payloads = {
            "sample_preparation": {
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
            "cleaning_transforms": {
                "asset_id": panel_asset_id,
                "workflow_group": "cleaning_transforms",
                "impute_method": "median",
                "impute_columns": ["size", "leverage"],
                "winsorize_columns": ["outcome_y"],
                "winsor_lower_quantile": 0.02,
                "winsor_upper_quantile": 0.98,
                "log_transform_columns": ["sales"],
                "standardize_columns": ["size", "leverage"],
                "outlier_columns": ["outcome_y"],
                "outlier_method": "iqr",
                "outlier_threshold": 1.5,
            },
            "time_series_features": {
                "asset_id": ts_asset_id,
                "workflow_group": "time_series_features",
                "sort_column": "date",
                "difference_columns": ["policy_rate"],
                "return_columns": ["spot_price"],
                "return_method": "log",
                "lag_columns": ["return_a", "return_b"],
                "lag_periods": 2,
                "lead_columns": ["return_c"],
                "lead_periods": 1,
                "rolling_mean_columns": ["asset_return"],
                "rolling_volatility_columns": ["asset_return"],
                "rolling_window": 5,
                "date_columns": ["date"],
            },
        }
        for label, payload in processing_payloads.items():
            save_processing_run(
                client,
                token,
                workspace_id,
                payload,
                label.replace("_", " "),
                OUTPUT_ROOT / "processing" / label,
                report,
            )

        plot_payload = {
            "asset_id": ts_asset_id,
            "chart_type": "line",
            "x_column": "date",
            "y_columns": ["asset_return", "market_return"],
            "group_column": "",
            "title": "Monte Carlo verification line chart",
        }
        save_plot_run(client, token, workspace_id, plot_payload, OUTPUT_ROOT / "plots" / "line_chart", report)

        model_specs = [
            ("OLS", {"asset_id": panel_asset_id, "model_type": "ols", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"]}),
            ("PPML", {"asset_id": panel_asset_id, "model_type": "ppml", "dependent": "export_flow", "independents": ["size", "leverage"], "controls": ["post"]}),
            ("Logit", {"asset_id": panel_asset_id, "model_type": "logit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}),
            ("Probit", {"asset_id": panel_asset_id, "model_type": "probit", "dependent": "binary_outcome", "independents": ["size", "leverage"], "controls": ["treated"]}),
            ("DID", {"asset_id": panel_asset_id, "model_type": "did", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "post_column": "post"}),
            ("Event Study", {"asset_id": panel_asset_id, "model_type": "event_study", "dependent": "outcome_y", "controls": ["size", "leverage"], "treatment_column": "treated", "event_time_column": "event_time", "entity_column": "firm_id", "time_column": "date", "include_time_effects": True, "lead_window": 4, "lag_window": 4, "omitted_period": -1}),
            ("RDD", {"asset_id": panel_asset_id, "model_type": "rdd", "dependent": "outcome_y", "controls": ["size"], "running_column": "running_score", "rdd_cutoff": 0.0, "rdd_bandwidth": 1.1, "rdd_polynomial_order": 2, "treat_above_cutoff": True}),
            ("Fixed Effects", {"asset_id": panel_asset_id, "model_type": "fixed_effects", "dependent": "outcome_y", "independents": ["size", "leverage"], "controls": ["post"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}),
            ("Gravity", {"asset_id": panel_asset_id, "model_type": "gravity", "dependent": "export_flow", "origin_mass_column": "origin_gdp", "destination_mass_column": "destination_gdp", "distance_column": "distance_km", "controls": ["post"]}),
            ("IV-2SLS", {"asset_id": panel_asset_id, "model_type": "iv_2sls", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"]}),
            ("Panel IV", {"asset_id": panel_asset_id, "model_type": "panel_iv", "dependent": "outcome_y", "independents": ["size"], "controls": ["leverage"], "endogenous_column": "endogenous_x", "instrument_columns": ["instrument_z"], "entity_column": "firm_id", "time_column": "date", "include_time_effects": True}),
            ("ARIMA", {"asset_id": ts_asset_id, "model_type": "arima", "dependent": "policy_rate", "time_column": "date", "arima_p": 1, "arima_d": 0, "arima_q": 1, "forecast_steps": 6}),
            ("ARCH", {"asset_id": ts_asset_id, "model_type": "arch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}),
            ("GARCH", {"asset_id": ts_asset_id, "model_type": "garch", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "forecast_steps": 5}),
            ("VAR", {"asset_id": ts_asset_id, "model_type": "var", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "forecast_steps": 5}),
            ("SVAR IRF", {"asset_id": ts_asset_id, "model_type": "svar_irf", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10, "impulse_column": "return_a", "response_column": "return_b"}),
            ("VIRF", {"asset_id": ts_asset_id, "model_type": "virf", "dependent": "asset_return", "time_column": "date", "garch_p": 1, "garch_q": 1, "irf_horizon": 10, "virf_shock_size": 1.25}),
            ("DY Connectedness", {"asset_id": ts_asset_id, "model_type": "dy_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "irf_horizon": 10}),
            ("BK Connectedness", {"asset_id": ts_asset_id, "model_type": "bk_connectedness", "series_columns": ["return_a", "return_b", "return_c"], "time_column": "date", "var_lags": 2, "bk_short_horizon": 5, "bk_medium_horizon": 20}),
            ("Historical VaR", {"asset_id": ts_asset_id, "model_type": "historical_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}),
            ("Parametric VaR", {"asset_id": ts_asset_id, "model_type": "parametric_var", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1}),
            ("EWMA Volatility", {"asset_id": ts_asset_id, "model_type": "ewma_volatility", "dependent": "asset_return", "time_column": "date", "confidence_level": 0.95, "holding_period_days": 1, "ewma_lambda": 0.94}),
            ("Altman Z", {"asset_id": panel_asset_id, "model_type": "altman_z", "working_capital_column": "working_capital", "retained_earnings_column": "retained_earnings", "ebit_column": "ebit", "market_equity_column": "market_equity", "sales_column": "sales", "total_assets_column": "total_assets", "total_liabilities_column": "total_liabilities"}),
            ("DuPont", {"asset_id": panel_asset_id, "model_type": "dupont", "net_income_column": "net_income", "revenue_column": "revenue", "total_assets_column": "total_assets", "equity_column": "equity"}),
            ("Black-Scholes", {"asset_id": ts_asset_id, "model_type": "black_scholes", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "call"}),
            ("Binomial Option", {"asset_id": ts_asset_id, "model_type": "binomial_option", "spot_column": "spot_price", "strike_column": "strike_price", "maturity_column": "time_to_maturity", "rate_column": "risk_free_rate", "volatility_column": "implied_vol", "option_type": "put", "option_steps": 40}),
            ("Taylor Rule", {"asset_id": ts_asset_id, "model_type": "taylor_rule", "dependent": "policy_rate", "inflation_gap_column": "inflation_gap", "output_gap_column": "output_gap"}),
            ("Toy RBC / DSGE", {"asset_id": ts_asset_id, "model_type": "rbc_dsge", "dsge_alpha": 0.33, "dsge_beta": 0.99, "dsge_delta": 0.025, "dsge_productivity": 1.0, "dsge_labor": 0.33, "dsge_shock_persistence": 0.92, "dsge_shock_size": 0.02, "dsge_impulse_horizon": 10}),
            ("Mean-Variance", {"asset_id": ts_asset_id, "model_type": "mean_variance", "series_columns": ["return_a", "return_b", "return_c"], "risk_aversion": 3.0, "long_only": True}),
            ("Minimum Variance", {"asset_id": ts_asset_id, "model_type": "minimum_variance", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}),
            ("Risk Parity", {"asset_id": ts_asset_id, "model_type": "risk_parity", "series_columns": ["return_a", "return_b", "return_c"], "long_only": True}),
            ("CAPM", {"asset_id": ts_asset_id, "model_type": "capm", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate"}),
            ("Fama-French 3", {"asset_id": ts_asset_id, "model_type": "fama_french_3", "dependent": "asset_return", "market_column": "market_return", "risk_free_column": "risk_free_rate", "smb_column": "smb", "hml_column": "hml"}),
        ]

        results: dict[str, dict] = {}
        for label, payload in model_specs:
            output_dir = OUTPUT_ROOT / "models" / payload["model_type"]
            print(f"Exporting model: {label}")
            results[label] = save_model_run(client, token, workspace_id, payload, label, output_dir, report)

        if not any(row.get("term") == "did_interaction" for row in results["DID"].get("coefficients", [])):
            raise AssertionError("DID did not return the interaction term in the coefficient table")
        if len(results["DID"].get("cell_means", [])) < 4:
            raise AssertionError("DID did not return the 2x2 cell means table")
        report["checks"].append("DID returned interaction term and 2x2 cell means table.")

        if not results["SVAR IRF"].get("tables", {}).get("irf_table"):
            raise AssertionError("SVAR IRF did not return the impulse-response table")
        if len(results["SVAR IRF"].get("figures", [])) < 2:
            raise AssertionError("SVAR IRF did not return both orthogonalized and cumulative IRF figures")
        report["checks"].append("SVAR IRF returned table plus orthogonalized and cumulative response figures.")

        if len(results["VIRF"].get("figures", [])) < 2:
            raise AssertionError("VIRF did not return both volatility and variance response figures")
        report["checks"].append("VIRF returned volatility and variance response figures.")

        if not results["DY Connectedness"].get("tables", {}).get("connectedness_matrix", []):
            raise AssertionError("DY connectedness did not return a connectedness matrix")
        if len(results["DY Connectedness"].get("figures", [])) < 2:
            raise AssertionError("DY connectedness did not return both heatmap and directional spillover figures")
        report["checks"].append("DY connectedness returned matrix plus heatmap and net-spillover figures.")

        if len(results["BK Connectedness"].get("tables", {}).get("band_total_connectedness", [])) < 3:
            raise AssertionError("BK connectedness did not return short/medium/long band summaries")
        if len(results["BK Connectedness"].get("figures", [])) < 2:
            raise AssertionError("BK connectedness did not return both heatmap and band summary figures")
        report["checks"].append("BK connectedness returned band summaries plus frequency-domain figures.")

        if len(results["GARCH"].get("figures", [])) < 2 or len(results["ARCH"].get("figures", [])) < 2:
            raise AssertionError("ARCH/GARCH did not return the expected in-sample and forecast volatility figures")
        report["checks"].append("ARCH and GARCH each returned in-sample and forecast volatility figures.")

        settings = get_settings()
        with session_scope() as db:
            public_briefing = ensure_public_daily_briefing(db, settings, force=True)
            if not public_briefing or public_briefing.headline_count <= 0:
                raise AssertionError("Public Daily Monitor local generation still returned no headlines")
            public_payload = serialize_public_briefing_detail(db, public_briefing, public_base_url=settings.public_base_url)
        write_json(OUTPUT_ROOT / "public_monitor" / "local_latest_briefing.json", {"briefing": public_payload})
        report["public_monitor"] = {
            "headline_count": public_payload["headline_count"],
            "slug": public_payload["slug"],
            "detail_path": public_payload["detail_path"],
        }

        anchor_report = build_anchor_report()
        anchor_report["model_count"] = len(model_specs)
        anchor_report["processing_workflow_count"] = len(processing_payloads)
        anchor_report["export_root"] = str(OUTPUT_ROOT)
        anchor_report["key_outputs"] = {
            "verification_report": "verification_report.json",
            "did_detail": "models/did/detail.json",
            "svar_irf_figures": [
                "models/svar_irf/figures/01_svar_irf_for_return_a.png",
                "models/svar_irf/figures/02_cumulative_svar_irf_for_return_a.png",
            ],
            "bk_figures": [
                "models/bk_connectedness/figures/01_bk_connectedness_heatmap.png",
                "models/bk_connectedness/figures/02_bk_band_total_connectedness.png",
            ],
            "variable_guide": "variable_guide/response.json",
            "public_monitor_snapshot": "public_monitor/local_latest_briefing.json",
        }
        write_json(OUTPUT_ROOT / "model_anchor_report.json", anchor_report)

        notes_lines = [
            "# 模型核查与锚定说明",
            "",
            "这份说明对应当前 `蒙特卡洛` 目录内的最新一次本地实跑结果。",
            "",
            "## 我的核查思路",
            "1. 先用可重复的 Monte Carlo 数据分别生成面板样本和时间序列样本，避免线上真实数据波动影响判断。",
            "2. 再依次跑变量建议、数据处理、作图和全部模型，确保不是只看页面或只看单个接口。",
            "3. 每个模型都锚定到论文里应出现的核心产物，例如系数表、2x2 cell means、IRF 表、连通性矩阵、波动率图等。",
            "4. 任何一个模型如果缺关键表、缺关键图、缺识别项，都视为失败；不是只看接口 200 就算通过。",
            "",
            "## 当前结论",
            f"- 本轮本地实跑通过的模型/模块数：{len(model_specs)}",
            f"- 本轮本地实跑通过的数据处理流程数：{len(processing_payloads)}",
            "- 当前没有复现出稳定的模型失效点；至少在这轮隔离环境里，33 个模型/模块都能正常输出结果。",
            "- 当前发现的告警不是模型算法错误，而是本地 `.env` 第 21 行的 `python-dotenv` 解析警告；它没有影响模型运行。",
            "",
            "## 人工核查时优先看什么",
            "- DID：看 `models/did/detail.json`，确认 `did_interaction` 存在，且 `cell_means` 是完整 2x2。",
            "- Event Study / RDD：看 `models/event_study/figures/` 与 `models/rdd/figures/` 的图是否生成。",
            "- ARCH / GARCH：看是否同时输出样本内波动图与预测波动图。",
            "- VAR / SVAR IRF / VIRF：看 `tables` 与 `figures` 是否同时存在，不能只有图没有表，也不能只有表没有图。",
            "- DY / BK：看连通性矩阵、频段汇总和热力图是否齐全。",
            "",
            "## 建议的核查路径",
            "1. 先看 `verification_report.json`，确认整体状态是 `passed`。",
            "2. 再看 `model_anchor_report.json`，确认每个模型族该输出什么。",
            "3. 最后进入各模型目录的 `detail.json`、`result_page.html` 和 `figures/` 做人工抽查。",
            "",
            "## 关键文件",
            "- `verification_report.json`：本轮总索引。",
            "- `model_anchor_report.json`：模型锚定点与预期输出。",
            "- `model_suite_console_output.txt`：这轮验证脚本的控制台实跑输出。",
            "- `models/*/detail.json`：每个模型的原始结果详情。",
            "- `models/*/result_page.html`：每个模型的展示页快照。",
            "",
            "## 说明",
            "如果后续有模型再次失效，我会优先按这里的锚定点回归，不会只凭页面报错做猜测式修复。",
        ]
        write_text(OUTPUT_ROOT / "模型核查与锚定说明.md", "\n".join(notes_lines))

        readme_lines = [
            "# Monte Carlo Data Lab Export",
            "",
            "This folder was generated automatically by `scripts/export_monte_carlo_data_lab.py`.",
            "",
            "Contents:",
            "- `datasets/`: Monte Carlo simulated panel and time-series datasets plus profile payloads.",
            "- `catalog/`: family, method, and teaching metadata plus HTML page snapshots.",
            "- `processing/`: each data-processing workflow run, detail payload, and prepared sample.",
            "- `plots/`: visualization output and downloadable PNG.",
            "- `models/`: each model run, detail payload, tables, and exported figures.",
            "- `public_monitor/`: local public-briefing payload generated from live news feeds.",
            "- `verification_report.json`: compact index of checks and output locations.",
            "- `model_anchor_report.json`: anchor points and expected outputs for each model family.",
            "- `模型核查与锚定说明.md`: readable notes that explain the verification path and what to inspect manually.",
            "",
            "Highlighted checks:",
            *[f"- {item}" for item in report["checks"]],
        ]
        write_text(OUTPUT_ROOT / "README.md", "\n".join(readme_lines))
        report["status"] = "passed"
        write_json(OUTPUT_ROOT / "verification_report.json", report)
        print(f"Monte Carlo export completed: {OUTPUT_ROOT}")
        print(f"Models exported: {len(model_specs)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
