from __future__ import annotations

from research_agent.entities import DataAsset, KnowledgeRecord


def _current_user_id(client) -> str:
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    return me.json()["user"]["id"]


def _upload_csv_asset(client, workspace_id: str, csrf_token: str, *, filename: str = "sample.csv", content: bytes | None = None) -> dict:
    payload = content or (
        b"date,y,x,z\n"
        b"2026-01-01,1,2,3\n"
        b"2026-01-02,2,3,4\n"
        b"2026-01-03,3,4,5\n"
        b"2026-01-04,4,5,6\n"
        b"2026-01-05,5,6,7\n"
        b"2026-01-06,6,7,8\n"
        b"2026-01-07,7,8,9\n"
        b"2026-01-08,8,9,10\n"
        b"2026-01-09,9,10,11\n"
        b"2026-01-10,10,11,12\n"
        b"2026-01-11,11,12,13\n"
        b"2026-01-12,12,13,14\n"
    )
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "test dataset"},
        files={"file": (filename, payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]


def _stub_macro_briefing_sources(monkeypatch):
    monkeypatch.setattr(
        "research_agent.platform_research.fetch_gdelt_hotspots",
        lambda settings, *, query_text="", max_records=None: {
            "query": query_text or "macro",
            "items": [
                {
                    "title": "Inflation cools",
                    "url": "https://example.com/inflation-cools",
                    "source_name": "Example",
                    "published_at": "2026-04-17T08:00:00Z",
                }
            ],
            "feed_status": [],
        },
    )
    monkeypatch.setattr(
        "research_agent.platform_research.fetch_fred_snapshots",
        lambda api_key, *, series_ids: [
            {
                "series_id": "FEDFUNDS",
                "label": "Federal Funds Rate",
                "latest_value": "5.25",
                "latest_date": "2026-04-01",
                "recent_observations": [],
            }
        ],
    )


def test_schedule_management_and_job_run_history(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    _stub_macro_briefing_sources(monkeypatch)

    created = client.post(
        f"/api/workspaces/{workspace_id}/schedules",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Daily Macro Watch",
            "job_type": "economic_briefing",
            "timezone_name": "UTC",
            "local_time": "08:00",
            "config": {
                "query_text": "inflation growth rates",
                "title": "Daily Macro Watch",
            },
        },
    )
    assert created.status_code == 200, created.text
    schedule = created.json()["schedule"]
    schedule_id = schedule["id"]
    assert schedule["next_run_at"]

    paused = client.patch(
        f"/api/workspaces/{workspace_id}/schedules/{schedule_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"enabled": False},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["schedule"]["status"] == "paused"
    assert paused.json()["schedule"]["next_run_at"] is None

    run_now = client.post(
        f"/api/workspaces/{workspace_id}/schedules/{schedule_id}/run-now",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert run_now.status_code == 200, run_now.text
    run_payload = run_now.json()["run"]
    assert run_payload["status"] == "completed"
    assert run_payload["briefing_id"]
    assert run_payload["knowledge_record_id"]
    assert run_payload["detail_path"] == "/knowledge-base"

    schedule_runs = client.get(f"/api/workspaces/{workspace_id}/schedules/{schedule_id}/runs")
    assert schedule_runs.status_code == 200, schedule_runs.text
    assert len(schedule_runs.json()["items"]) >= 1
    assert schedule_runs.json()["items"][0]["id"] == run_payload["id"]

    workspace_runs = client.get(f"/api/workspaces/{workspace_id}/job-runs")
    assert workspace_runs.status_code == 200, workspace_runs.text
    assert any(item["id"] == run_payload["id"] for item in workspace_runs.json()["items"])

    schedules = client.get(f"/api/workspaces/{workspace_id}/schedules")
    assert schedules.status_code == 200, schedules.text
    updated = next(item for item in schedules.json()["items"] if item["id"] == schedule_id)
    assert updated["run_count"] >= 1
    assert updated["latest_run"]["status"] == "completed"
    assert updated["last_run_summary"] == "Daily Macro Watch"

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/schedules/{schedule_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert deleted.status_code == 200, deleted.text

    remaining = client.get(f"/api/workspaces/{workspace_id}/schedules")
    assert remaining.status_code == 200, remaining.text
    assert all(item["id"] != schedule_id for item in remaining.json()["items"])


def test_briefing_generation_and_case_linking_closed_loop(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    _stub_macro_briefing_sources(monkeypatch)

    generated = client.post(
        f"/api/workspaces/{workspace_id}/briefings/generate",
        headers={"X-CSRF-Token": csrf_token},
        json={"query_text": "inflation growth rates", "title": "Manual Macro Briefing"},
    )
    assert generated.status_code == 200, generated.text
    briefing = generated.json()["briefing"]
    briefing_id = briefing["id"]
    knowledge_record_id = briefing["workspace_knowledge_record_id"]
    assert knowledge_record_id
    assert briefing["status"] == "ready"
    assert briefing["next_action"] == "open_knowledge_note"
    assert briefing["trigger"] == "manual"
    assert briefing["schedule_id"] == ""
    assert briefing["job_run_id"] == ""

    listed = client.get(f"/api/workspaces/{workspace_id}/briefings")
    assert listed.status_code == 200, listed.text
    listed_briefing = next(item for item in listed.json()["items"] if item["id"] == briefing_id)
    assert listed_briefing["workspace_knowledge_record_id"] == knowledge_record_id
    assert listed_briefing["workspace_knowledge_record_title"] == "Manual Macro Briefing"

    imported = client.post(
        f"/api/workspaces/{workspace_id}/briefings/{briefing_id}/import-knowledge",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert imported.status_code == 200, imported.text
    imported_payload = imported.json()
    assert imported_payload["imported"] is False
    assert imported_payload["record"]["id"] == knowledge_record_id
    assert imported_payload["briefing"]["workspace_knowledge_record_id"] == knowledge_record_id

    knowledge_detail = client.get(f"/api/workspaces/{workspace_id}/knowledge/{knowledge_record_id}")
    assert knowledge_detail.status_code == 200, knowledge_detail.text
    knowledge_record = knowledge_detail.json()["record"]
    assert knowledge_record["metadata"]["briefing_id"] == briefing_id
    assert knowledge_record["status"] == "ready"
    assert knowledge_record["detail_path"] == "/knowledge-base"

    created_case = client.post(
        f"/api/workspaces/{workspace_id}/knowledge-cases",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Macro Follow-up Case",
            "description": "Track the generated briefing and its linked note.",
            "tags": ["macro", "briefing"],
        },
    )
    assert created_case.status_code == 200, created_case.text
    case_id = created_case.json()["case"]["id"]

    added_note = client.post(
        f"/api/workspaces/{workspace_id}/knowledge-cases/{case_id}/items",
        headers={"X-CSRF-Token": csrf_token},
        json={"item_type": "knowledge_record", "ref_id": knowledge_record_id},
    )
    assert added_note.status_code == 200, added_note.text
    note_item = added_note.json()["item"]
    assert added_note.json()["created"] is True
    assert note_item["item_type"] == "knowledge_record"
    assert note_item["metadata"]["source_kind"] == "knowledge_record"
    assert note_item["metadata"]["knowledge_record_id"] == knowledge_record_id
    assert note_item["detail_path"] == "/knowledge-base"
    assert note_item["status"] == "ready"

    added_note_again = client.post(
        f"/api/workspaces/{workspace_id}/knowledge-cases/{case_id}/items",
        headers={"X-CSRF-Token": csrf_token},
        json={"item_type": "knowledge_record", "ref_id": knowledge_record_id},
    )
    assert added_note_again.status_code == 200, added_note_again.text
    assert added_note_again.json()["created"] is False
    assert added_note_again.json()["item"]["id"] == note_item["id"]

    added_briefing = client.post(
        f"/api/workspaces/{workspace_id}/knowledge-cases/{case_id}/items",
        headers={"X-CSRF-Token": csrf_token},
        json={"item_type": "briefing", "ref_id": briefing_id},
    )
    assert added_briefing.status_code == 200, added_briefing.text
    briefing_item = added_briefing.json()["item"]
    assert added_briefing.json()["created"] is True
    assert briefing_item["item_type"] == "briefing"
    assert briefing_item["metadata"]["source_kind"] == "briefing"
    assert briefing_item["metadata"]["briefing_id"] == briefing_id
    assert briefing_item["detail_path"] == "/knowledge-base"
    assert briefing_item["status"] == "ready"

    case_detail = client.get(f"/api/workspaces/{workspace_id}/knowledge-cases/{case_id}")
    assert case_detail.status_code == 200, case_detail.text
    detail_payload = case_detail.json()
    assert detail_payload["case"]["status"] == "ready"
    assert detail_payload["case"]["item_count"] == 2
    assert sorted(detail_payload["case"]["item_types"]) == ["briefing", "knowledge_record"]
    detail_items = {(item["item_type"], item["ref_id"]): item for item in detail_payload["items"]}
    assert detail_items[("knowledge_record", knowledge_record_id)]["title"] == "Manual Macro Briefing"
    assert detail_items[("briefing", briefing_id)]["title"] == "Manual Macro Briefing"


def test_data_lab_history_groups_processing_model_and_optimization(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)

    processing_asset = DataAsset(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        kind="dataset_csv",
        title="Prepared Sample",
        description="Prepared output",
        file_path="",
        content_type="text/csv",
        metadata_json={
            "processing_result": {
                "workflow_type": "data_processing",
                "processing_family": "sample_preparation",
                "summary": {"rows_after_prepare": 24},
                "result_detail_path": "/data-lab/results/processing/prepared-1",
            }
        },
    )
    model_record = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="OLS Summary",
        content="y = alpha + beta x",
        tags_json=["ols"],
        metadata_json={
            "workflow_type": "model",
            "model_type": "ols",
            "model_family": "econometrics_baseline",
            "result_detail_path": "/data-lab/results/models/model-1",
        },
    )
    optimization_record = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Optimization Suite",
        content="Optimization result",
        tags_json=["optimization"],
        metadata_json={
            "workflow_type": "optimization",
            "suite_label": "Optimization Suite",
            "result_detail_path": "/data-lab/results/optimization/opt-1",
        },
    )
    db_session.add_all([processing_asset, model_record, optimization_record])
    db_session.commit()

    response = client.get(f"/api/workspaces/{workspace_id}/data-lab/history")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert any(item["detail_path"] == "/data-lab/results/processing/prepared-1" for item in payload["processing"])
    assert any(item["status"] == "ready" for item in payload["processing"])
    assert any(item["detail_path"] == "/data-lab/results/models/model-1" for item in payload["models"])
    assert any(item["status"] == "ready" for item in payload["models"])
    assert any(item["detail_path"] == "/data-lab/results/optimization/opt-1" for item in payload["optimization"])
    assert any(item["status"] == "ready" for item in payload["optimization"])


def test_llm_integration_creation_is_blocked(client, auth_headers, db_session, monkeypatch):
    csrf_token = auth_headers["csrf"]

    integration_response = client.post(
        "/api/integrations",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "label": "Test OpenAI",
            "category": "llm",
            "kind": "openai",
            "api_key": "test-key-value",
            "base_url": "",
            "model": "gpt-4.1-mini",
            "is_default": True,
            "config": {},
        },
    )
    assert integration_response.status_code == 400, integration_response.text
    assert "not available in the current product scope" in integration_response.text


def test_workspace_memory_is_pruned_scoped_and_included_in_digest(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    second_workspace = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Secondary Workspace", "description": "Isolation target"},
    )
    assert second_workspace.status_code == 200, second_workspace.text
    second_workspace_id = second_workspace.json()["workspace"]["id"]

    for index in range(13):
        created = client.post(
            f"/api/workspaces/{workspace_id}/memories",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "title": f"Memory {index}",
                "content": f"Workspace memory chunk {index}",
                "metadata": {"index": index},
            },
        )
        assert created.status_code == 200, created.text

    listed = client.get(f"/api/workspaces/{workspace_id}/memories")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 12
    titles = [item["title"] for item in items]
    assert "Memory 12" in titles
    assert "Memory 0" not in titles

    digest = client.post(
        f"/api/workspaces/{workspace_id}/knowledge/digest",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert digest.status_code == 200, digest.text
    digest_record = digest.json()["record"]
    assert "## Workspace memories" in digest_record["content"]
    assert "Memory 12" in digest_record["content"]

    latest_memory_id = items[0]["id"]
    denied = client.delete(
        f"/api/workspaces/{second_workspace_id}/memories/{latest_memory_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert denied.status_code == 404, denied.text

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/memories/{latest_memory_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert deleted.status_code == 200, deleted.text

    remaining = client.get(f"/api/workspaces/{workspace_id}/memories")
    assert remaining.status_code == 200, remaining.text
    assert len(remaining.json()["items"]) == 11


def test_data_lab_history_keeps_failed_processing_runs_separate_from_success(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    asset = _upload_csv_asset(client, workspace_id, csrf_token)

    prepared = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": asset["id"],
            "workflow_group": "sample_preparation",
            "required_columns": ["y", "x"],
            "numeric_columns": ["y", "x", "z"],
        },
    )
    assert prepared.status_code == 200, prepared.text

    failed_prepare = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": asset["id"],
            "workflow_group": "sample_preparation",
            "required_columns": ["missing_column"],
        },
    )
    assert failed_prepare.status_code == 400, failed_prepare.text

    history = client.get(f"/api/workspaces/{workspace_id}/data-lab/history")
    assert history.status_code == 200, history.text
    processing_items = history.json()["processing"]

    ready_item = next((item for item in processing_items if item["status"] == "ready"), None)
    failed_item = next((item for item in processing_items if item["status"] == "failed"), None)
    assert ready_item is not None
    assert ready_item["detail_path"]
    assert failed_item is not None
    assert failed_item["workflow_type"] == "processing"
    assert failed_item["reason"]
    assert failed_item["detail_path"] == ""


def test_data_lab_history_keeps_failed_model_runs_separate_from_success(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    asset = _upload_csv_asset(client, workspace_id, csrf_token, filename="model.csv")

    modeled = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": asset["id"],
            "model_type": "ols",
            "dependent": "y",
            "independents": ["x"],
        },
    )
    assert modeled.status_code == 200, modeled.text

    failed_model = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": asset["id"],
            "model_type": "ols",
            "dependent": "missing_y",
            "independents": ["x"],
        },
    )
    assert failed_model.status_code == 400, failed_model.text

    history = client.get(f"/api/workspaces/{workspace_id}/data-lab/history")
    assert history.status_code == 200, history.text
    model_items = history.json()["models"]

    ready_item = next((item for item in model_items if item["status"] == "ready"), None)
    assert ready_item is not None
    assert ready_item["detail_path"]
    assert not [item for item in model_items if item["status"] == "ready" and item.get("metadata", {}).get("model_type") == "ols" and not item.get("detail_path")]
    assert not [item for item in model_items if item["status"] == "failed" and item.get("metadata", {}).get("model_type") == "ols"]


def test_data_lab_history_records_failed_optimization_runs(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    failed_optimization = client.post(
        f"/api/workspaces/{workspace_id}/optimization/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "suite_label": "Broken Suite",
            "optimizer_names": ["missing-optimizer"],
            "function_names": ["missing-function"],
            "dimension": 4,
            "epoch": 2,
            "pop_size": 3,
            "runs": 1,
        },
    )
    assert failed_optimization.status_code == 400, failed_optimization.text

    history = client.get(f"/api/workspaces/{workspace_id}/data-lab/history")
    assert history.status_code == 200, history.text
    optimization_items = history.json()["optimization"]

    failed_item = next((item for item in optimization_items if item["status"] == "failed"), None)
    assert failed_item is not None
    assert failed_item["workflow_type"] == "optimization"
    assert failed_item["reason"]
    assert failed_item["suite_label"] == "Broken Suite"
