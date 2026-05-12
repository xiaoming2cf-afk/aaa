from __future__ import annotations

import json

from sqlalchemy import func, select

from research_agent.entities import DataAsset, KnowledgeRecord


def _count_rows(db_session, model) -> int:
    return int(db_session.scalar(select(func.count()).select_from(model)) or 0)


def test_preparation_preview_returns_transformation_summary_without_persisting_assets(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    upload = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "preview source"},
        files={"file": ("preview-source.csv", b"y,x,group\n1,10,a\n,20,b\n3,30,a\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    asset_id = upload.json()["asset"]["id"]
    asset_count_before = _count_rows(db_session, DataAsset)
    knowledge_count_before = _count_rows(db_session, KnowledgeRecord)

    response = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare/preview",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": asset_id,
            "workflow_group": "sample_preparation",
            "include_columns": ["y", "x", "group"],
            "required_columns": ["y"],
            "numeric_columns": ["y", "x"],
            "standardize_columns": ["x"],
        },
    )

    assert response.status_code == 200, response.text
    preview = response.json()["preview"]
    assert preview["source_asset_id"] == asset_id
    assert preview["workflow_group"] == "sample_preparation"
    assert preview["input_rows"] == 3
    assert preview["output_rows"] == 2
    assert preview["dropped_rows"] == 1
    assert preview["input_columns"] == ["y", "x", "group"]
    assert preview["output_columns"] == ["y", "x", "group"]
    assert preview["missing_before_by_column"]["y"] == 1
    assert preview["missing_after_by_column"]["y"] == 0
    assert "x" in preview["transformed_columns"]
    assert len(preview["preview_rows"]) == 2
    assert preview["specification_summary"]["request"]["required_columns"] == ["y"]

    serialized_preview = json.dumps(preview, sort_keys=True)
    assert "/tmp" not in serialized_preview
    assert "\\storage\\" not in serialized_preview.lower()
    assert _count_rows(db_session, DataAsset) == asset_count_before
    assert _count_rows(db_session, KnowledgeRecord) == knowledge_count_before
