from __future__ import annotations

import csv
import io
import math
from datetime import date, timedelta
from typing import Any

import pytest


def _upload_csv_rows(client, workspace_id: str, csrf_token: str, filename: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    assert rows
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": filename},
        files={"file": (filename, buffer.getvalue().encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]


def _run_model(client, workspace_id: str, csrf_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    assert result["result_record_id"]
    return result


def _preflight(client, workspace_id: str, csrf_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models/preflight",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["preflight"]


def _coefficient(result: dict[str, Any], term: str) -> float:
    for row in result.get("coefficients", []):
        if row.get("term") == term:
            value = float(row["coefficient"])
            assert math.isfinite(value)
            return value
    raise AssertionError(f"Missing coefficient {term!r} in {result.get('coefficients')}")


def _table(result: dict[str, Any], name: str) -> list[dict[str, Any]]:
    rows = (result.get("tables") or {}).get(name)
    assert isinstance(rows, list), f"Missing table {name!r}"
    return rows


def _forecast_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("forecast")
    if rows is None:
        rows = (result.get("tables") or {}).get("forecast")
    if rows is None:
        rows = (result.get("tables") or {}).get("forecast_summary")
    assert isinstance(rows, list), "Missing forecast rows"
    return rows


def _assert_finite_tree(value: Any) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        assert math.isfinite(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _assert_finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite_tree(item)


def _econometric_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_index in range(4):
        entity = f"firm_{entity_index + 1}"
        treated = 1 if entity_index >= 2 else 0
        entity_effect = float(entity_index - 1.5) * 1.7
        for period in range(20):
            row_index = entity_index * 20 + period
            post = 1 if period >= 10 else 0
            ols_x = (row_index - 39.5) / 8.0
            running = (row_index - 39.5) / 10.0
            iv_control = float(entity_index - 1.5)
            instrument_z = float((period % 10) - 4.5) + 0.15 * entity_index
            endog_x = 1.4 * instrument_z + 0.35 * iv_control + 0.02 * ((period % 3) - 1)
            fe_x = float(((period + entity_index) % 7) - 3)
            time_effect = 0.25 * post + 0.03 * period
            rows.append(
                {
                    "entity": entity,
                    "period": period,
                    "ols_x": ols_x,
                    "ols_y": 2.0 + 3.0 * ols_x + 0.001 * ((row_index % 3) - 1),
                    "treated": treated,
                    "post": post,
                    "did_y": 10.0 + 1.5 * treated + 0.8 * post + 4.0 * treated * post + 0.02 * iv_control,
                    "running": running,
                    "rdd_y": -1.0 + 0.6 * running + (5.0 if running >= 0 else 0.0),
                    "instrument_z": instrument_z,
                    "endog_x": endog_x,
                    "iv_control": iv_control,
                    "iv_y": 0.5 + 2.5 * endog_x + 0.8 * iv_control + 0.001 * period,
                    "fe_x": fe_x,
                    "fe_y": 2.0 + 1.1 * fe_x + entity_effect + time_effect,
                }
            )
    return rows


def _time_series_rows(count: int = 90) -> list[dict[str, Any]]:
    start = date(2026, 1, 1)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        market = 0.004 * math.sin(index / 5.0) + 0.001 * ((index % 6) - 2)
        smb = 0.002 * math.cos(index / 7.0)
        hml = 0.0025 * math.sin(index / 8.0)
        risk_free = 0.0001
        ret_a = 0.003 * math.sin(index / 3.0) + 0.001 * ((index % 5) - 2)
        ret_b = 0.0025 * math.cos(index / 4.0) + 0.0008 * ((index % 7) - 3)
        ret_c = 0.002 * math.sin(index / 6.0 + 0.4) - 0.0005 * ((index % 4) - 1)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "ts_y": 1.0 + 0.03 * index + 0.4 * math.sin(index / 5.0),
                "var_a": 0.4 * math.sin(index / 4.0) + 0.015 * index,
                "var_b": 0.25 * math.cos(index / 6.0) + 0.2 * math.sin(index / 4.0) + 0.01 * index,
                "ret_a": ret_a,
                "ret_b": ret_b,
                "ret_c": ret_c,
                "market_return": market,
                "risk_free_rate": risk_free,
                "asset_return": risk_free + 1.4 * (market - risk_free) + 0.0004 * math.cos(index / 4.0),
                "smb": smb,
                "hml": hml,
                "ff_asset_return": risk_free + 1.2 * (market - risk_free) + 0.6 * smb - 0.4 * hml,
                "spot": 80.0 + index * 0.8,
                "strike": 100.0,
                "maturity": 1.0,
                "rate": 0.03,
                "volatility": 0.22,
            }
        )
    return list(reversed(rows))


def test_econometric_models_return_reasonable_coefficients_and_design_metadata(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    asset = _upload_csv_rows(client, workspace_id, csrf_token, "econometric_correctness.csv", _econometric_rows())

    ols = _run_model(
        client,
        workspace_id,
        csrf_token,
        {"asset_id": asset["id"], "model_type": "ols", "dependent": "ols_y", "independents": ["ols_x"]},
    )
    assert _coefficient(ols, "ols_x") == pytest.approx(3.0, abs=0.01)
    assert _coefficient(ols, "const") == pytest.approx(2.0, abs=0.01)
    assert ols["observations"] == 80

    did_payload = {
        "asset_id": asset["id"],
        "model_type": "did",
        "dependent": "did_y",
        "treatment_column": "treated",
        "post_column": "post",
    }
    did_preflight = _preflight(client, workspace_id, csrf_token, did_payload)
    assert did_preflight["status"] == "ok"
    did = _run_model(client, workspace_id, csrf_token, did_payload)
    assert did["did_effect"] == pytest.approx(4.0, abs=0.05)
    assert _coefficient(did, "did_interaction") == pytest.approx(4.0, abs=0.05)
    assert len(did["cell_means"]) == 4

    rdd = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "rdd",
            "dependent": "rdd_y",
            "running_column": "running",
            "cutoff": 0.0,
            "bandwidth": 4.0,
            "polynomial_order": 1,
        },
    )
    assert rdd["local_effect"] == pytest.approx(5.0, abs=0.05)
    assert _coefficient(rdd, "rdd_treatment") == pytest.approx(5.0, abs=0.05)
    assert rdd.get("figures")
    assert _table(rdd, "rdd_design_audit")[0]["observations"] == 80

    iv = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "iv_2sls",
            "dependent": "iv_y",
            "independents": ["iv_control"],
            "endogenous_column": "endog_x",
            "instrument_columns": ["instrument_z"],
        },
    )
    assert _coefficient(iv, "endog_x") > 2.0
    assert _coefficient(iv, "endog_x") == pytest.approx(2.5, abs=0.15)
    assert iv["instrument_columns"] == ["instrument_z"]
    # First-stage diagnostics are not yet exposed; the run still records the instrument specification.
    assert iv["covariance_type"] in {"HC1", "nonrobust"}

    fixed_effects = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "fixed_effects",
            "dependent": "fe_y",
            "independents": ["fe_x"],
            "entity_column": "entity",
            "time_column": "period",
            "include_time_effects": True,
        },
    )
    assert fixed_effects["entity_column"] == "entity"
    assert fixed_effects["time_column"] == "period"
    assert fixed_effects["entity_count"] == 4
    assert fixed_effects["time_count"] == 20
    assert set(fixed_effects["audit_trail"]["fixed_effects"]) == {"entity", "period"}


def test_time_series_and_risk_models_return_finite_ordered_outputs(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    asset = _upload_csv_rows(client, workspace_id, csrf_token, "time_series_correctness.csv", _time_series_rows())

    arima = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "arima",
            "dependent": "ts_y",
            "time_column": "date",
            "forecast_steps": 4,
            "arima_p": 1,
            "arima_d": 0,
            "arima_q": 0,
        },
    )
    arima_forecast = _forecast_rows(arima)
    assert len(arima_forecast) == 4
    _assert_finite_tree(arima_forecast)
    preview_dates = [row["date"] for row in arima["sample_preview"]]
    assert preview_dates == sorted(preview_dates)

    var = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "var",
            "series_columns": ["var_a", "var_b"],
            "time_column": "date",
            "var_lags": 1,
            "forecast_steps": 3,
        },
    )
    assert len(_table(var, "forecast")) == 3
    _assert_finite_tree({"forecast": _table(var, "forecast"), "metrics": var["metrics"]})

    garch = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "garch",
            "dependent": "ret_a",
            "time_column": "date",
            "garch_p": 1,
            "garch_q": 1,
            "forecast_steps": 3,
        },
    )
    assert len(_table(garch, "volatility_forecast")) == 3
    _assert_finite_tree({"forecast": _table(garch, "volatility_forecast"), "metrics": garch["metrics"]})

    risk = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "historical_var",
            "dependent": "ret_a",
            "time_column": "date",
            "confidence_level": 0.95,
        },
    )
    risk_summary = _table(risk, "risk_summary")[0]
    # The implementation reports VaR/ES as positive loss magnitudes after negating lower-tail returns.
    assert risk_summary["var"] >= 0
    assert risk_summary["expected_shortfall"] >= 0
    _assert_finite_tree(risk_summary)

    short_asset = _upload_csv_rows(client, workspace_id, csrf_token, "short_series.csv", _time_series_rows(count=10))
    rejected = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": short_asset["id"],
            "model_type": "arima",
            "dependent": "ts_y",
            "time_column": "date",
            "forecast_steps": 2,
        },
    )
    assert rejected.status_code == 400
    assert "not enough" in rejected.text.lower()


def test_asset_pricing_portfolio_and_derivatives_outputs_are_reasonable(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    asset = _upload_csv_rows(client, workspace_id, csrf_token, "finance_correctness.csv", _time_series_rows())

    capm = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "capm",
            "dependent": "asset_return",
            "market_column": "market_return",
            "risk_free_column": "risk_free_rate",
        },
    )
    assert _coefficient(capm, "market_excess") == pytest.approx(1.4, abs=0.08)
    assert capm["risk_free_column"] == "risk_free_rate"

    ff3 = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "fama_french_3",
            "dependent": "ff_asset_return",
            "market_column": "market_return",
            "risk_free_column": "risk_free_rate",
            "smb_column": "smb",
            "hml_column": "hml",
        },
    )
    assert _coefficient(ff3, "market_excess") > 0
    assert _coefficient(ff3, "smb") > 0
    assert _coefficient(ff3, "hml") < 0

    portfolio = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "mean_variance",
            "series_columns": ["ret_a", "ret_b", "ret_c"],
            "long_only": True,
        },
    )
    weights = _table(portfolio, "weights_table")
    assert len(weights) == 3
    assert sum(float(row["weight"]) for row in weights) == pytest.approx(1.0, abs=1e-6)
    assert all(float(row["weight"]) >= -1e-12 for row in weights)

    option_payload = {
        "asset_id": asset["id"],
        "model_type": "black_scholes",
        "spot_column": "spot",
        "strike_column": "strike",
        "maturity_column": "maturity",
        "rate_column": "rate",
        "volatility_column": "volatility",
    }
    call = _run_model(client, workspace_id, csrf_token, {**option_payload, "option_type": "call"})
    call_rows = sorted(_table(call, "pricing_table"), key=lambda row: float(row["spot"]))
    call_prices = [float(row["price"]) for row in call_rows]
    assert min(call_prices) > 0
    assert call_prices[-1] > call_prices[0]

    put = _run_model(client, workspace_id, csrf_token, {**option_payload, "option_type": "put"})
    put_prices = [float(row["price"]) for row in _table(put, "pricing_table")]
    assert min(put_prices) > 0
    _assert_finite_tree(put["metrics"])

    binomial = _run_model(
        client,
        workspace_id,
        csrf_token,
        {**option_payload, "model_type": "binomial_option", "option_type": "call", "option_steps": 25},
    )
    assert float(binomial["metrics"]["latest_price"]) > 0
    _assert_finite_tree({"metrics": binomial["metrics"], "pricing": _table(binomial, "pricing_table")})
