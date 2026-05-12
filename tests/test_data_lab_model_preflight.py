from __future__ import annotations

from sqlalchemy import select

from research_agent.entities import DataLabRun


def _upload_csv(client, auth_headers, filename: str, content: str) -> str:
    workspace_id = auth_headers["workspace_id"]
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        data={"description": filename},
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]["id"]


def _preflight(client, auth_headers, payload: dict) -> dict:
    workspace_id = auth_headers["workspace_id"]
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models/preflight",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["preflight"]


def _has_check(preflight: dict, key: str, status: str) -> bool:
    return any(check.get("key") == key and check.get("status") == status for check in preflight.get("checks", []))


def test_model_preflight_ols_ok(client, auth_headers):
    rows = ["y,x"]
    rows.extend(f"{2 + 3 * index},{index}" for index in range(1, 31))
    asset_id = _upload_csv(client, auth_headers, "ols.csv", "\n".join(rows) + "\n")

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "ols",
            "dependent": "y",
            "independents": ["x"],
        },
    )

    assert preflight["status"] == "ok"
    assert preflight["sample"]["row_count"] == 30
    assert preflight["sample"]["missing_required_columns"] == []


def test_model_preflight_did_blocks_missing_treatment(client, auth_headers):
    rows = ["y,post,x"]
    rows.extend(f"{index},{index % 2},{index / 10}" for index in range(1, 25))
    asset_id = _upload_csv(client, auth_headers, "did-missing.csv", "\n".join(rows) + "\n")

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "did",
            "dependent": "y",
            "treatment_column": "treated",
            "post_column": "post",
        },
    )

    assert preflight["status"] == "blocked"
    assert "treated" in preflight["sample"]["missing_required_columns"]


def test_model_preflight_did_blocks_when_interaction_has_no_variation(client, auth_headers):
    rows = ["y,treated,post"]
    rows.extend(f"{index},1,0" for index in range(1, 13))
    rows.extend(f"{index},0,1" for index in range(13, 25))
    asset_id = _upload_csv(client, auth_headers, "did-no-interaction.csv", "\n".join(rows) + "\n")

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "did",
            "dependent": "y",
            "treatment_column": "treated",
            "post_column": "post",
        },
    )

    assert preflight["status"] == "blocked"
    assert _has_check(preflight, "did_interaction_variation", "blocked")


def test_model_preflight_rdd_blocks_one_side_of_cutoff(client, auth_headers):
    rows = ["y,running"]
    rows.extend(f"{index},{0.1 + index / 10}" for index in range(1, 25))
    asset_id = _upload_csv(client, auth_headers, "rdd-one-side.csv", "\n".join(rows) + "\n")

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "rdd",
            "dependent": "y",
            "running_column": "running",
            "rdd_cutoff": 0,
        },
    )

    assert preflight["status"] == "blocked"
    assert _has_check(preflight, "rdd_cutoff_sides", "blocked")


def test_model_preflight_iv_warns_when_instrument_has_no_variance(client, auth_headers):
    rows = ["y,x,z,w"]
    rows.extend(f"{index * 2},{index},1,{index / 5}" for index in range(1, 31))
    asset_id = _upload_csv(client, auth_headers, "iv-constant-instrument.csv", "\n".join(rows) + "\n")

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "iv_2sls",
            "dependent": "y",
            "independents": ["w"],
            "endogenous_column": "x",
            "instrument_columns": ["z"],
        },
    )

    assert preflight["status"] == "warning"
    assert any("Instrument has no variation" in reason for reason in preflight["warnings"])


def test_model_preflight_arima_blocks_too_short_series(client, auth_headers):
    asset_id = _upload_csv(
        client,
        auth_headers,
        "short-arima.csv",
        "date,y\n2026-01-01,1\n2026-01-02,2\n2026-01-03,3\n2026-01-04,4\n2026-01-05,5\n",
    )

    preflight = _preflight(
        client,
        auth_headers,
        {
            "asset_id": asset_id,
            "model_type": "arima",
            "dependent": "y",
            "time_column": "date",
            "arima_p": 2,
            "arima_d": 1,
            "arima_q": 2,
            "forecast_steps": 5,
        },
    )

    assert preflight["status"] == "blocked"
    assert _has_check(preflight, "time_series_length", "blocked")


def test_model_run_rejects_blocked_preflight_without_ready_record(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    rows = ["y,post,x"]
    rows.extend(f"{index},{index % 2},{index / 10}" for index in range(1, 25))
    asset_id = _upload_csv(client, auth_headers, "blocked-run.csv", "\n".join(rows) + "\n")

    before = list(
        db_session.scalars(
            select(DataLabRun).where(
                DataLabRun.workspace_id == workspace_id,
                DataLabRun.workflow_type == "model",
                DataLabRun.status == "ready",
            )
        )
    )
    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        json={
            "asset_id": asset_id,
            "model_type": "did",
            "dependent": "y",
            "treatment_column": "treated",
            "post_column": "post",
        },
    )

    assert response.status_code == 400
    assert "preflight blocked" in response.text.lower()
    after = list(
        db_session.scalars(
            select(DataLabRun).where(
                DataLabRun.workspace_id == workspace_id,
                DataLabRun.workflow_type == "model",
                DataLabRun.status == "ready",
            )
        )
    )
    assert len(after) == len(before)
