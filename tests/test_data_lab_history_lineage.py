from __future__ import annotations

from research_agent.entities import DataLabRun


def test_data_lab_history_returns_best_effort_pipeline_chains(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    upload = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "lineage dataset"},
        files={"file": ("lineage.csv", b"y,x\n1,1\n2,2\n3,3\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    asset_id = upload.json()["asset"]["id"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    user_id = me.json()["user"]["id"]

    processing = DataLabRun(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        workflow_type="processing",
        family="sample_preparation",
        method="clean",
        title="Prepared lineage sample",
        status="ready",
        source_asset_id=asset_id,
        output_json={"summary": "prepared"},
    )
    model = DataLabRun(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        workflow_type="model",
        family="econometrics_baseline",
        method="ols",
        title="OLS lineage model",
        status="ready",
        source_asset_id=asset_id,
        output_json={"summary": "model"},
    )
    db_session.add_all([processing, model])
    db_session.commit()

    response = client.get(f"/api/workspaces/{workspace_id}/data-lab/history")
    assert response.status_code == 200, response.text
    payload = response.json()
    chains = payload.get("pipeline_chains") or []
    assert chains
    chain = next(item for item in chains if item.get("source_asset_id") == asset_id)
    assert chain["stages"]["processing_count"] >= 1
    assert chain["stages"]["model_count"] >= 1
    assert chain["processing"]
    assert chain["models"]
