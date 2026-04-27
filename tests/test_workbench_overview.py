from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_agent.entities import AgentRun, DataLabRun, KnowledgeRecord


def _current_user_id(client) -> str:
    response = client.get("/api/auth/me")
    assert response.status_code == 200, response.text
    return response.json()["user"]["id"]


def _csrf_headers(client) -> dict[str, str]:
    token = client.cookies.get("erp_csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def test_workbench_overview_composes_read_only_sections(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)
    now = datetime.now(timezone.utc)

    team_response = client.post(
        "/api/teams",
        headers=_csrf_headers(client),
        json={"name": "Overview Team", "description": "Workbench overview test team."},
    )
    assert team_response.status_code == 200, team_response.text
    team_id = team_response.json()["team"]["id"]
    attach_response = client.post(
        f"/api/workspaces/{workspace_id}/team",
        headers=_csrf_headers(client),
        json={"team_id": team_id},
    )
    assert attach_response.status_code == 200, attach_response.text

    saved_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="overview-saved",
        topic="Publishable research",
        question="Can this run be published?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        queue_status="completed",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Topic\nPublishable research\n\n# References\n- [S1] Source",
        report_path="storage/reports/overview-saved/report.md",
        quality_json={},
        started_at=now - timedelta(minutes=15),
        finished_at=now - timedelta(minutes=14),
    )
    queued_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="overview-queued",
        topic="Active research",
        question="Is this still running?",
        language="Chinese",
        status="queued",
        current_stage="drafting",
        queue_status="queued",
        review_json={},
        metrics_json={},
        quality_json={},
        started_at=now - timedelta(minutes=5),
        queued_at=now - timedelta(minutes=5),
    )
    data_lab_run = DataLabRun(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        workflow_type="agent_session",
        family="data_lab_agent",
        method="notebook",
        title="Overview data session",
        status="completed",
        detail_path="/app/data-lab-agent?run=overview-data-session",
        summary="Explored the uploaded dataset.",
        output_json={
            "agent_session": {
                "summary": "Explored the uploaded dataset.",
                "messages": [{"role": "user", "content": "Summarize."}],
                "cells": [{"code": "df.describe()"}],
                "artifacts": [],
            }
        },
        started_at=now - timedelta(minutes=10),
        finished_at=now - timedelta(minutes=9),
    )
    knowledge = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Publishable note",
        content="A sourced workspace note ready for publication.",
        tags_json=["overview"],
        metadata_json={"source_type": "workspace_note"},
    )
    db_session.add_all([saved_run, queued_run, data_lab_run, knowledge])
    db_session.commit()

    response = client.get(f"/api/workspaces/{workspace_id}/workbench/overview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {
        "active_runs",
        "data_lab_sessions",
        "quality_blockers",
        "publish_queue",
        "recent_activity",
        "runtime_summary",
    }

    assert [item["id"] for item in payload["active_runs"]] == [queued_run.id]
    assert payload["data_lab_sessions"][0]["id"] == data_lab_run.id

    publish_by_ref = {(item["resource_type"], item["resource_id"]): item for item in payload["publish_queue"]}
    assert publish_by_ref[("agent_run", saved_run.id)]["publish_allowed"] is True
    assert publish_by_ref[("knowledge_record", knowledge.id)]["publish_allowed"] is True
    assert publish_by_ref[("agent_run", saved_run.id)]["delivery_review"]["publish_allowed"] is True

    activity_types = {item["activity_type"] for item in payload["recent_activity"]}
    assert {"research_run", "data_lab_session", "knowledge_record"}.issubset(activity_types)
    assert payload["runtime_summary"]["team"]["attached"] is True
    assert payload["runtime_summary"]["research_runtime"]["code"] == "feature_disabled"
    assert payload["quality_blockers"]

    db_session.expire_all()
    saved_after = db_session.get(AgentRun, saved_run.id)
    queued_after = db_session.get(AgentRun, queued_run.id)
    knowledge_after = db_session.get(KnowledgeRecord, knowledge.id)
    assert saved_after is not None
    assert queued_after is not None
    assert knowledge_after is not None
    assert saved_after.quality_json == {}
    assert queued_after.quality_json == {}
    assert saved_after.publish_status == "unpublished"
    assert knowledge_after.metadata_json == {"source_type": "workspace_note"}


def test_workbench_overview_empty_workspace_fails_closed(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]

    response = client.get(f"/api/workspaces/{workspace_id}/workbench/overview")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["active_runs"] == []
    assert payload["data_lab_sessions"] == []
    assert payload["publish_queue"] == []
    assert payload["quality_blockers"]
    assert payload["quality_blockers"][0]["publish_allowed"] is False
    assert payload["runtime_summary"]["quality"]["deliverable"] is False
    assert payload["runtime_summary"]["team"]["attached"] is False
    assert payload["runtime_summary"]["team"]["blocking_reasons"] == ["Workspace is not attached to a team."]


def test_workbench_overview_requires_workspace_access(client):
    response = client.get("/api/workspaces/not-a-workspace/workbench/overview")
    assert response.status_code == 401
