from __future__ import annotations

import json


def _upload_model_csv(client, auth_headers) -> str:
    workspace_id = auth_headers["workspace_id"]
    rows = ["y,x,group"]
    rows.extend(f"{2 + 3 * index},{index},a" for index in range(1, 31))
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        data={"description": "manifest source"},
        files={"file": ("manifest-source.csv", ("\n".join(rows) + "\n").encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]["id"]


def _assert_manifest_is_sanitized(manifest: dict) -> None:
    serialized = json.dumps(manifest, sort_keys=True)
    assert manifest["version"] == "datalab-manifest-v1"
    assert "file_path" not in serialized
    assert "download_path" not in serialized
    assert "/tmp" not in serialized
    assert "\\storage\\" not in serialized.lower()


def test_processing_result_detail_includes_reproducibility_manifest(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    asset_id = _upload_model_csv(client, auth_headers)
    prepare = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        json={
            "asset_id": asset_id,
            "workflow_group": "sample_preparation",
            "include_columns": ["y", "x", "group"],
            "required_columns": ["y", "x"],
            "numeric_columns": ["y", "x"],
        },
    )
    assert prepare.status_code == 200, prepare.text
    prepared_asset_id = prepare.json()["asset"]["id"]

    detail = client.get(f"/api/data-lab/results/processing/{prepared_asset_id}")
    assert detail.status_code == 200, detail.text
    manifest = detail.json()["result"]["reproducibility_manifest"]

    assert manifest["result_type"] == "processing"
    assert manifest["result_id"] == prepared_asset_id
    assert manifest["source_asset_id"] == asset_id
    assert manifest["workflow_group"] == "sample_preparation"
    assert "y" in manifest["selected_columns"]
    assert prepared_asset_id in manifest["generated_asset_ids"]
    _assert_manifest_is_sanitized(manifest)


def test_model_result_detail_includes_reproducibility_manifest(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    asset_id = _upload_model_csv(client, auth_headers)
    model = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        json={
            "asset_id": asset_id,
            "model_type": "ols",
            "dependent": "y",
            "independents": ["x"],
        },
    )
    assert model.status_code == 200, model.text
    record_id = model.json()["result_record_id"]

    detail = client.get(f"/api/data-lab/results/models/{record_id}")
    assert detail.status_code == 200, detail.text
    manifest = detail.json()["result"]["reproducibility_manifest"]

    assert manifest["result_type"] == "model"
    assert manifest["result_id"] == record_id
    assert manifest["source_asset_id"] == asset_id
    assert manifest["model_type"] == "ols"
    assert manifest["variable_roles"]["dependent"] == "y"
    assert "x" in manifest["variable_roles"]["independents"]
    _assert_manifest_is_sanitized(manifest)
