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
                    "binary_y": 1 if ols_x + 0.45 * ((row_index % 5) - 2) > 0 else 0,
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


def _limited_response_rows(count: int = 120) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(count):
        x = (index - (count - 1) / 2) / 18.0
        z = ((index % 9) - 4) / 4.0
        latent = 0.8 * x + 0.5 * z + 0.9 * math.sin(index * 1.7)
        rows.append(
            {
                "x": x,
                "z": z,
                "binary_y": 1 if latent > 0 else 0,
                "count_y": math.exp(0.7 + 0.35 * x - 0.2 * z),
            }
        )
    return rows


def _gravity_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for origin_index in range(6):
        for destination_index in range(6):
            if origin_index == destination_index:
                continue
            origin_mass = 80.0 + 15.0 * origin_index
            destination_mass = 70.0 + 12.0 * destination_index
            distance = 30.0 + 5.0 * abs(origin_index - destination_index) + 3.0 * (origin_index + destination_index)
            ln_flow = 0.45 + 0.65 * math.log(origin_mass) + 0.55 * math.log(destination_mass) - 0.8 * math.log(distance)
            rows.append(
                {
                    "flow": math.exp(ln_flow) - 1.0,
                    "origin_mass": origin_mass,
                    "destination_mass": destination_mass,
                    "distance": distance,
                }
            )
    return rows


def _event_study_rows() -> list[dict[str, Any]]:
    effects = {-2: 0.0, -1: 0.0, 0: 2.0, 1: 3.0, 2: 4.0}
    rows: list[dict[str, Any]] = []
    for entity_index in range(10):
        treated = 1 if entity_index >= 4 else 0
        treatment_time = 3 if 4 <= entity_index < 7 else 4 if treated else 99
        entity = f"unit_{entity_index + 1}"
        entity_effect = 0.4 * entity_index
        for period in range(7):
            event_time = period - treatment_time
            time_effect = 0.25 * period
            rows.append(
                {
                    "entity": entity,
                    "period": period,
                    "treated": treated,
                    "treatment_time": treatment_time,
                    "event_time": event_time,
                    "event_y": 5.0 + entity_effect + time_effect + treated * effects.get(event_time, 0.0),
                }
            )
    return rows


def _macro_rows(count: int = 60) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(count):
        inflation_gap = -1.5 + index / 20.0
        output_gap = math.sin(index / 5.0) + 0.1 * ((index % 4) - 1.5)
        policy_rate = 1.0 + 1.5 * inflation_gap + 0.5 * output_gap
        rows.append({"inflation_gap": inflation_gap, "output_gap": output_gap, "policy_rate": policy_rate})
    return rows


def _corporate_rows(count: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(count):
        total_assets = 100.0 + 4.0 * index
        total_liabilities = 45.0 + 1.5 * index
        revenue = 130.0 + 5.0 * index
        net_income = 13.0 + 0.5 * index
        rows.append(
            {
                "working_capital": 18.0 + index,
                "retained_earnings": 22.0 + 0.8 * index,
                "ebit": 12.0 + 0.6 * index,
                "market_equity": 90.0 + 3.0 * index,
                "sales": revenue,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "net_income": net_income,
                "revenue": revenue,
                "equity": total_assets - total_liabilities,
            }
        )
    return rows


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

    for model_type in ("logit", "probit"):
        binary = _run_model(
            client,
            workspace_id,
            csrf_token,
            {
                "asset_id": asset["id"],
                "model_type": model_type,
                "dependent": "binary_y",
                "independents": ["ols_x"],
            },
        )
        assert _coefficient(binary, "ols_x") > 0
        assert binary["dependent"] == "binary_y"
        assert binary["observations"] == 80
        _assert_finite_tree(binary["coefficients"])

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

    panel_iv = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "panel_iv",
            "dependent": "iv_y",
            "endogenous_column": "endog_x",
            "instrument_columns": ["instrument_z"],
            "entity_column": "entity",
        },
    )
    assert _coefficient(panel_iv, "endog_x") == pytest.approx(2.5, abs=0.2)
    assert panel_iv["entity_count"] == 4
    assert panel_iv["instrument_columns"] == ["instrument_z"]


def test_limited_response_count_gravity_and_event_study_outputs_are_reasonable(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    limited_asset = _upload_csv_rows(client, workspace_id, csrf_token, "limited_correctness.csv", _limited_response_rows())

    logit_preflight = _preflight(
        client,
        workspace_id,
        csrf_token,
        {"asset_id": limited_asset["id"], "model_type": "logit", "dependent": "binary_y", "independents": ["x", "z"]},
    )
    assert logit_preflight["status"] == "ok"
    logit = _run_model(
        client,
        workspace_id,
        csrf_token,
        {"asset_id": limited_asset["id"], "model_type": "logit", "dependent": "binary_y", "independents": ["x", "z"]},
    )
    assert _coefficient(logit, "x") > 0
    assert _coefficient(logit, "z") > 0
    assert 0 <= float(logit["pseudo_r_squared"]) <= 1

    probit = _run_model(
        client,
        workspace_id,
        csrf_token,
        {"asset_id": limited_asset["id"], "model_type": "probit", "dependent": "binary_y", "independents": ["x", "z"]},
    )
    assert _coefficient(probit, "x") > 0
    assert _coefficient(probit, "z") > 0
    _assert_finite_tree({"logit": logit["coefficients"], "probit": probit["coefficients"]})

    ppml = _run_model(
        client,
        workspace_id,
        csrf_token,
        {"asset_id": limited_asset["id"], "model_type": "ppml", "dependent": "count_y", "independents": ["x", "z"]},
    )
    assert _coefficient(ppml, "x") == pytest.approx(0.35, abs=0.03)
    assert _coefficient(ppml, "z") == pytest.approx(-0.2, abs=0.03)
    assert ppml["mean_prediction"] > 0

    gravity_asset = _upload_csv_rows(client, workspace_id, csrf_token, "gravity_correctness.csv", _gravity_rows())
    gravity = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": gravity_asset["id"],
            "model_type": "gravity",
            "dependent": "flow",
            "origin_mass_column": "origin_mass",
            "destination_mass_column": "destination_mass",
            "distance_column": "distance",
        },
    )
    assert _coefficient(gravity, "ln_origin_mass") > 0
    assert _coefficient(gravity, "ln_destination_mass") > 0
    assert _coefficient(gravity, "ln_distance") < 0
    assert gravity["dropped_nonpositive_rows"] == 0

    event_asset = _upload_csv_rows(client, workspace_id, csrf_token, "event_study_correctness.csv", _event_study_rows())
    event = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": event_asset["id"],
            "model_type": "event_study",
            "dependent": "event_y",
            "treatment_column": "treated",
            "event_time_column": "event_time",
            "entity_column": "entity",
            "time_column": "period",
            "treatment_time_column": "treatment_time",
            "include_time_effects": True,
            "lead_window": 2,
            "lag_window": 2,
            "omitted_period": -1,
        },
    )
    event_rows = _table(event, "event_study_table")
    event_periods = [row.get("period", row.get("event_time")) for row in event_rows]
    assert event_periods == [-2, 0, 1, 2]
    coefficient_by_period = {row.get("period", row.get("event_time")): float(row["coefficient"]) for row in event_rows}
    assert set(coefficient_by_period) == {-2, 0, 1, 2}
    window_row = _table(event, "event_study_window")[0]
    assert window_row.get("periods_estimated", len(event_rows)) == 4
    _assert_finite_tree(event_rows)


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
    assert all(row.get("step") for row in arima_forecast)
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
    assert [row["step"] for row in _table(var, "forecast")] == [1, 2, 3]
    _assert_finite_tree({"forecast": _table(var, "forecast"), "metrics": var["metrics"]})

    arch = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "arch",
            "dependent": "ret_a",
            "time_column": "date",
            "garch_p": 1,
            "forecast_steps": 2,
        },
    )
    assert len(_table(arch, "volatility_forecast")) == 2
    assert all(
        float(row.get("forecast_volatility", row.get("forecast_variance", 0.0))) >= 0
        for row in _table(arch, "volatility_forecast")
    )

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

    svar = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "svar_irf",
            "series_columns": ["var_a", "var_b"],
            "time_column": "date",
            "var_lags": 1,
            "irf_horizon": 4,
            "impulse_column": "var_a",
            "response_column": "var_b",
        },
    )
    assert len(_table(svar, "irf_table")) == 5
    assert [row["horizon"] for row in _table(svar, "irf_table")] == [0, 1, 2, 3, 4]
    _assert_finite_tree({"irf": _table(svar, "irf_table"), "metrics": svar["metrics"]})

    virf = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "virf",
            "dependent": "ret_a",
            "time_column": "date",
            "garch_p": 1,
            "garch_q": 1,
            "irf_horizon": 4,
            "virf_shock_size": 1.25,
        },
    )
    assert len(_table(virf, "virf_path")) == 4
    assert [row["horizon"] for row in _table(virf, "virf_path")] == [1, 2, 3, 4]
    assert all(float(row["variance"]) >= 0 for row in _table(virf, "virf_path"))

    dy = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "dy_connectedness",
            "series_columns": ["var_a", "var_b"],
            "time_column": "date",
            "var_lags": 1,
            "irf_horizon": 5,
        },
    )
    connectedness = _table(dy, "connectedness_matrix")
    assert len(connectedness) == 2
    for row in connectedness:
        assert sum(float(row[column]) for column in ["var_a", "var_b"]) == pytest.approx(100.0, abs=1e-6)
    assert 0 <= float(dy["metrics"]["total_connectedness_index"]) <= 100

    bk = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "bk_connectedness",
            "series_columns": ["var_a", "var_b"],
            "time_column": "date",
            "var_lags": 1,
            "bk_short_horizon": 4,
            "bk_medium_horizon": 12,
        },
    )
    band_rows = _table(bk, "band_total_connectedness")
    assert len(band_rows) == 3
    assert all(0 <= float(row["total_connectedness_index"]) <= 100 for row in band_rows)
    _assert_finite_tree({"bk": bk["tables"], "metrics": bk["metrics"]})

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

    parametric = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "parametric_var",
            "dependent": "ret_a",
            "time_column": "date",
            "confidence_level": 0.95,
            "holding_period_days": 4,
        },
    )
    parametric_summary = _table(parametric, "risk_summary")[0]
    assert parametric_summary["holding_period_days"] == 4
    assert parametric_summary["var"] >= 0
    assert parametric_summary["expected_shortfall"] >= parametric_summary["var"]

    ewma = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "ewma_volatility",
            "dependent": "ret_a",
            "time_column": "date",
            "ewma_lambda": 0.9,
        },
    )
    ewma_summary = _table(ewma, "risk_summary")[0]
    assert ewma_summary["ewma_lambda"] == pytest.approx(0.9)
    assert ewma_summary["latest_volatility"] >= 0

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
    assert "not enough" in rejected.text.lower() or "need at least" in rejected.text.lower()


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

    for model_type in ["minimum_variance", "risk_parity"]:
        allocation = _run_model(
            client,
            workspace_id,
            csrf_token,
            {
                "asset_id": asset["id"],
                "model_type": model_type,
                "series_columns": ["ret_a", "ret_b", "ret_c"],
                "long_only": True,
            },
        )
        allocation_weights = _table(allocation, "weights_table")
        assert sum(float(row["weight"]) for row in allocation_weights) == pytest.approx(1.0, abs=1e-6)
        assert all(float(row["weight"]) >= -1e-12 for row in allocation_weights)
        _assert_finite_tree(allocation["metrics"])

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
    call_greeks = _table(call, "pricing_greeks_summary")[0]
    assert 0 <= float(call_greeks["delta"]) <= 1

    put = _run_model(client, workspace_id, csrf_token, {**option_payload, "option_type": "put"})
    put_rows = sorted(_table(put, "pricing_table"), key=lambda row: float(row["spot"]))
    put_prices = [float(row["price"]) for row in put_rows]
    assert min(put_prices) > 0
    assert put_prices[-1] < put_prices[0]
    put_greeks = _table(put, "pricing_greeks_summary")[0]
    assert -1 <= float(put_greeks["delta"]) <= 0
    _assert_finite_tree(put["metrics"])

    binomial = _run_model(
        client,
        workspace_id,
        csrf_token,
        {**option_payload, "model_type": "binomial_option", "option_type": "call", "option_steps": 25},
    )
    assert float(binomial["metrics"]["latest_price"]) > 0
    _assert_finite_tree({"metrics": binomial["metrics"], "pricing": _table(binomial, "pricing_table")})


def test_macro_and_corporate_finance_outputs_are_deterministic_and_finite(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    macro_asset = _upload_csv_rows(client, workspace_id, csrf_token, "macro_correctness.csv", _macro_rows())

    taylor = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": macro_asset["id"],
            "model_type": "taylor_rule",
            "dependent": "policy_rate",
            "inflation_gap_column": "inflation_gap",
            "output_gap_column": "output_gap",
        },
    )
    assert _coefficient(taylor, "inflation_gap") == pytest.approx(1.5, abs=0.01)
    assert _coefficient(taylor, "output_gap") == pytest.approx(0.5, abs=0.01)

    rbc = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": macro_asset["id"],
            "model_type": "rbc_dsge",
            "dsge_alpha": 0.33,
            "dsge_beta": 0.98,
            "dsge_delta": 0.04,
            "dsge_productivity": 1.0,
            "dsge_labor": 0.4,
            "dsge_shock_persistence": 0.8,
            "dsge_shock_size": 0.02,
            "dsge_impulse_horizon": 5,
        },
    )
    impulse = _table(rbc, "impulse_response_table")
    assert [row["step"] for row in impulse] == [0, 1, 2, 3, 4, 5]
    assert impulse[0]["output"] > impulse[-1]["output"] > 0
    assert rbc["metrics"]["steady_state_consumption"] > 0
    _assert_finite_tree({"rbc": rbc["metrics"], "impulse": impulse})

    corporate_asset = _upload_csv_rows(client, workspace_id, csrf_token, "corporate_correctness.csv", _corporate_rows())
    altman = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": corporate_asset["id"],
            "model_type": "altman_z",
            "working_capital_column": "working_capital",
            "retained_earnings_column": "retained_earnings",
            "ebit_column": "ebit",
            "market_equity_column": "market_equity",
            "sales_column": "sales",
            "total_assets_column": "total_assets",
            "total_liabilities_column": "total_liabilities",
        },
    )
    latest_corporate = _corporate_rows()[-1]
    expected_altman = (
        1.2 * latest_corporate["working_capital"] / latest_corporate["total_assets"]
        + 1.4 * latest_corporate["retained_earnings"] / latest_corporate["total_assets"]
        + 3.3 * latest_corporate["ebit"] / latest_corporate["total_assets"]
        + 0.6 * latest_corporate["market_equity"] / latest_corporate["total_liabilities"]
        + latest_corporate["sales"] / latest_corporate["total_assets"]
    )
    assert altman["metrics"]["latest_score"] == pytest.approx(expected_altman, abs=1e-12)
    assert _table(altman, "score_preview")[0]["distress_zone"] in {"distress", "grey", "safe"}

    dupont = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": corporate_asset["id"],
            "model_type": "dupont",
            "net_income_column": "net_income",
            "revenue_column": "revenue",
            "total_assets_column": "total_assets",
            "equity_column": "equity",
        },
    )
    expected_roe = latest_corporate["net_income"] / latest_corporate["equity"]
    assert dupont["metrics"]["latest_roe"] == pytest.approx(expected_roe, abs=1e-12)
    _assert_finite_tree({"altman": altman["metrics"], "dupont": dupont["metrics"]})


def test_corporate_finance_models_return_finite_accounting_metrics(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    rows = [
        {
            "working_capital": 24.0 + index,
            "retained_earnings": 12.0 + index * 0.5,
            "ebit": 18.0 + index * 0.7,
            "market_equity": 80.0 + index * 2.0,
            "sales": 120.0 + index * 3.0,
            "total_assets": 100.0 + index * 4.0,
            "total_liabilities": 50.0 + index * 1.5,
            "net_income": 10.0 + index,
            "revenue": 100.0 + index * 2.0,
            "equity": 45.0 + index,
        }
        for index in range(1, 16)
    ]
    asset = _upload_csv_rows(client, workspace_id, csrf_token, "corporate_finance_correctness.csv", rows)

    altman = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "altman_z",
            "working_capital_column": "working_capital",
            "retained_earnings_column": "retained_earnings",
            "ebit_column": "ebit",
            "market_equity_column": "market_equity",
            "sales_column": "sales",
            "total_assets_column": "total_assets",
            "total_liabilities_column": "total_liabilities",
        },
    )
    latest = rows[-1]
    expected_z = (
        1.2 * latest["working_capital"] / latest["total_assets"]
        + 1.4 * latest["retained_earnings"] / latest["total_assets"]
        + 3.3 * latest["ebit"] / latest["total_assets"]
        + 0.6 * latest["market_equity"] / latest["total_liabilities"]
        + latest["sales"] / latest["total_assets"]
    )
    assert altman["metrics"]["latest_score"] == pytest.approx(expected_z, abs=1e-9)
    _assert_finite_tree({"metrics": altman["metrics"], "preview": _table(altman, "score_preview")})

    dupont = _run_model(
        client,
        workspace_id,
        csrf_token,
        {
            "asset_id": asset["id"],
            "model_type": "dupont",
            "net_income_column": "net_income",
            "revenue_column": "revenue",
            "total_assets_column": "total_assets",
            "equity_column": "equity",
        },
    )
    expected_roe = latest["net_income"] / latest["equity"]
    assert dupont["metrics"]["latest_roe"] == pytest.approx(expected_roe, abs=1e-12)
    _assert_finite_tree({"metrics": dupont["metrics"], "preview": _table(dupont, "dupont_preview")})
