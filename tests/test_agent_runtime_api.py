from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_agent.agent_diagnostics import build_agent_eval_candidate, serialize_agent_run_detail
from research_agent.entities import AgentRun, DataAsset, KnowledgeCase, KnowledgeRecord


def _current_user_id(client) -> str:
    response = client.get("/api/auth/me")
    assert response.status_code == 200, response.text
    return response.json()["user"]["id"]


def _csrf_headers(client) -> dict[str, str]:
    token = client.cookies.get("erp_csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def test_agent_run_diagnostics_endpoints(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)
    now = datetime.now(timezone.utc)

    saved_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="saved-session",
        topic="Inflation persistence",
        question="What explains inflation persistence after supply shocks?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        context_json={"summary": "Selected two relevant workspace snippets."},
        plan_json={
            "required_sections": [
                "Topic",
                "Research Question",
                "Executive Summary",
                "Key Papers",
                "Methodological Patterns",
                "Research Gaps",
                "Suggested Next Reads",
                "References",
            ]
        },
        evidence_json={
            "included_source_ids": ["S1", "S2"],
            "items": [
                {"source_id": "S1", "title": "Inflation paper"},
                {"source_id": "S2", "title": "Wage paper"},
            ],
        },
        review_json={
            "status": "approved",
            "summary": "Approved after revision.",
            "findings": [],
            "missing_sections": [],
            "invalid_source_ids": [],
            "unsupported_claim_count": 0,
        },
        trace_json=[
            {"stage": "planned", "event": "stage_started"},
            {"stage": "researching", "event": "evidence_snapshot_saved"},
            {"stage": "reviewing", "event": "review_snapshot_saved"},
        ],
        metrics_json={
            "draft_attempts": 2,
            "citation_coverage": 1.0,
            "unsupported_claim_count": 0,
            "missing_section_count": 0,
            "invalid_source_id_count": 0,
            "review_status": "approved",
            "previous_response_ids": {
                "planner": "resp-planner-1",
                "researcher": "resp-researcher-1",
                "writer": "resp-writer-2",
                "reviewer": "resp-reviewer-2",
            },
        },
        final_text="# Topic\nInflation persistence\n\n# References\n- [S1] Inflation paper",
        report_path="storage/reports/saved/report.md",
        bibtex_path="storage/reports/saved/references.bib",
        sources_path="storage/reports/saved/sources.json",
        started_at=now - timedelta(seconds=20),
        finished_at=now - timedelta(seconds=5),
    )
    blocked_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="blocked-session",
        topic="Trade fragmentation",
        question="How does trade fragmentation affect inflation?",
        language="Chinese",
        status="blocked",
        current_stage="blocked",
        context_json={"summary": "Selected one relevant workspace snippet."},
        plan_json={"required_sections": ["Topic", "Executive Summary", "References"]},
        evidence_json={"included_source_ids": ["S3"], "items": [{"source_id": "S3", "title": "Trade paper"}]},
        review_json={
            "status": "blocked",
            "summary": "Blocked due to unsupported claims.",
            "findings": [{"code": "unsupported_claims", "severity": "high", "message": "Missing citations."}],
            "missing_sections": ["References"],
            "invalid_source_ids": ["S9"],
            "unsupported_claim_count": 2,
        },
        trace_json=[{"stage": "reviewing", "event": "review_snapshot_saved"}],
        metrics_json={
            "draft_attempts": 1,
            "citation_coverage": 0.0,
            "unsupported_claim_count": 2,
            "missing_section_count": 1,
            "invalid_source_id_count": 1,
            "review_status": "blocked",
        },
        final_text="# Topic\nTrade fragmentation",
        started_at=now - timedelta(seconds=60),
        finished_at=now - timedelta(seconds=40),
    )
    db_session.add_all([saved_run, blocked_run])
    db_session.commit()

    listed = client.get(f"/api/workspaces/{workspace_id}/agent-runs")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) >= 2
    listed_saved = next(item for item in items if item["id"] == saved_run.id)
    assert listed_saved["status"] == "saved"
    assert listed_saved["queue_status"] == "idle"
    assert listed_saved["review_status"] == "approved"
    assert listed_saved["source_count"] == 2
    assert listed_saved["draft_attempts"] == 2
    assert listed_saved["trace_event_count"] == 3

    filtered = client.get(f"/api/workspaces/{workspace_id}/agent-runs", params={"status": "saved"})
    assert filtered.status_code == 200, filtered.text
    filtered_ids = {item["id"] for item in filtered.json()["items"]}
    assert saved_run.id in filtered_ids
    assert blocked_run.id not in filtered_ids

    detail = client.get(f"/api/workspaces/{workspace_id}/agent-runs/{saved_run.id}")
    assert detail.status_code == 200, detail.text
    run_payload = detail.json()["run"]
    assert run_payload["id"] == saved_run.id
    assert run_payload["plan"]["required_sections"][-1] == "References"
    assert run_payload["evidence"]["included_source_ids"] == ["S1", "S2"]
    assert run_payload["metrics"]["previous_response_ids"]["writer"] == "resp-writer-2"
    assert run_payload["runtime_profile"] == {}
    assert run_payload["stage_providers"] == {}
    assert run_payload["publish_allowed"] is True
    assert run_payload["delivery_review"]["deliverable"] is True
    assert len(run_payload["trace"]) == 3

    eval_candidates = client.get(f"/api/workspaces/{workspace_id}/agent-runs/eval-candidates")
    assert eval_candidates.status_code == 200, eval_candidates.text
    eval_payload = eval_candidates.json()
    assert eval_payload["summary"]["count"] >= 2
    assert eval_payload["summary"]["ready_for_prompt_optimizer_count"] >= 1
    assert eval_payload["summary"]["needs_human_annotation_count"] >= 1

    saved_candidate = next(item for item in eval_payload["items"] if item["run_id"] == saved_run.id)
    assert saved_candidate["grader_scores"]["reviewer_approved"] is True
    assert saved_candidate["grader_labels"]["ready_for_prompt_optimizer"] is True
    assert saved_candidate["item"]["allowed_source_ids"] == ["S1", "S2"]

    blocked_candidate = next(item for item in eval_payload["items"] if item["run_id"] == blocked_run.id)
    assert blocked_candidate["grader_scores"]["unsupported_claim_count"] == 2
    assert blocked_candidate["grader_labels"]["needs_human_annotation"] is True


def test_research_run_create_returns_typed_503_when_runtime_disabled(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    before_count = db_session.query(AgentRun).count()

    capability = client.get(f"/api/workspaces/{workspace_id}/research/runtime")
    assert capability.status_code == 200, capability.text
    runtime = capability.json()["research_runtime"]
    assert runtime["enabled"] is False
    assert runtime["code"] == "feature_disabled"
    assert runtime["trace"]["queue_created"] is False

    created = client.post(
        f"/api/workspaces/{workspace_id}/research/runs",
        headers=_csrf_headers(client),
        json={
            "topic": "Runtime unavailable",
            "question": "Should this enqueue?",
            "instructions": "Do not create a doomed queue item.",
        },
    )

    assert created.status_code == 503, created.text
    detail = created.json()["detail"]
    assert detail["code"] == "feature_disabled"
    assert detail["feature"] == "research_runtime"
    assert detail["trace"]["runtime_available"] is False
    assert detail["trace"]["queue_created"] is False
    db_session.expire_all()
    assert db_session.query(AgentRun).count() == before_count


def test_research_run_product_endpoints(client, auth_headers, db_session, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)
    now = datetime.now(timezone.utc)

    asset = DataAsset(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        kind="document_pdf",
        title="Inflation appendix",
        description="Supporting PDF pages.",
        file_path="assets/inflation-appendix.pdf",
        content_type="application/pdf",
        extracted_text="Appendix excerpt",
        metadata_json={"original_filename": "inflation-appendix.pdf"},
    )
    extra_asset = DataAsset(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        kind="chart_png",
        title="Inflation chart",
        description="Supporting chart image.",
        file_path="assets/inflation-chart.png",
        content_type="image/png",
        extracted_text="Chart caption",
        metadata_json={"original_filename": "inflation-chart.png"},
    )
    case = KnowledgeCase(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Inflation Case",
        description="Case for research report linkage.",
    )
    blocked_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="blocked-retry-session",
        topic="Trade fragmentation",
        question="How does trade fragmentation affect inflation?",
        language="Chinese",
        status="blocked",
        current_stage="blocked",
        input_json={
            "topic": "Trade fragmentation",
            "question": "How does trade fragmentation affect inflation?",
            "instructions": "Tighten citations.",
            "asset_ids": [],
            "case_id": "",
            "draft_variants": 1,
            "mode": "standard",
        },
        attachment_json=[],
        plan_json={"required_sections": ["Topic", "Executive Summary", "References"]},
        evidence_json={"included_source_ids": ["S3"], "items": [{"source_id": "S3", "title": "Trade paper"}]},
        review_json={
            "status": "blocked",
            "summary": "Blocked due to unsupported claims.",
            "findings": [{"code": "unsupported_claims", "severity": "high", "message": "Missing citations."}],
            "missing_sections": ["References"],
            "invalid_source_ids": ["S9"],
            "unsupported_claim_count": 2,
        },
        metrics_json={
            "draft_attempts": 1,
            "citation_coverage": 0.2,
            "unsupported_claim_count": 2,
            "review_status": "blocked",
        },
        candidate_drafts_json=[
            {
                "draft_id": "D1-1",
                "variant_index": 1,
                "status": "blocked",
                "score": 12.0,
                "summary": "Missing citations.",
                "cited_source_ids": [],
                "missing_sections": ["References"],
                "invalid_source_ids": ["S9"],
                "unsupported_claim_count": 2,
                "finding_count": 1,
                "draft_preview": "# Topic\nTrade fragmentation",
            }
        ],
        selected_draft_id="D1-1",
        final_text="# Topic\nTrade fragmentation",
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=4),
    )
    db_session.add_all([asset, extra_asset, case, blocked_run])
    db_session.commit()

    def fake_start_workspace_research_run(*, settings, db, user, workspace, request):
        assert workspace.id == workspace_id
        assert user.id == user_id
        assert request.asset_ids == [asset.id]
        assert request.case_id == case.id
        run = AgentRun(
            owner_user_id=user.id,
            workspace_id=workspace.id,
            session_id="research-run-session",
            topic=request.topic,
            question=request.question or "",
            language="Chinese",
            status="queued",
            current_stage="planned",
            queue_status="queued",
            input_json=request.model_dump(mode="json"),
            attachment_json=[
                {
                    "source_id": "A1",
                    "asset_id": asset.id,
                    "title": asset.title,
                    "kind": asset.kind,
                    "mime_type": asset.content_type,
                    "caption": asset.description,
                    "usable_by_vision_model": True,
                }
            ],
            runtime_profile_json={},
            stage_provider_json={},
            queued_at=now - timedelta(minutes=2),
            started_at=now - timedelta(minutes=2),
        )
        db.add(run)
        db.flush()
        payload = serialize_agent_run_detail(run)
        payload["publish_allowed"] = False
        payload["blocking_reasons"] = ["Run is not saved yet."]
        payload["delivery_review"] = {
            "resource_type": "agent_run",
            "resource_id": run.id,
            "deliverable": False,
            "publish_allowed": False,
            "blocking_reasons": ["Run is not saved yet."],
        }
        return {"run": payload, "eval_candidate": None, "poll": {"run_id": run.id, "queue_status": "queued", "status": "queued"}}

    def fake_retry_workspace_research_run(*, settings, db, user, workspace, run, request):
        assert workspace.id == workspace_id
        assert user.id == user_id
        assert run.id == blocked_run.id
        assert request.asset_ids == [extra_asset.id]
        run.status = "queued"
        run.current_stage = "drafting"
        run.queue_status = "queued"
        run.attachment_json = [
            {
                "source_id": "A1",
                "asset_id": extra_asset.id,
                "title": extra_asset.title,
                "kind": extra_asset.kind,
                "mime_type": extra_asset.content_type,
                "caption": extra_asset.description,
                "usable_by_vision_model": True,
            }
        ]
        run.queued_at = now
        db.flush()
        payload = serialize_agent_run_detail(run)
        payload["publish_allowed"] = False
        payload["blocking_reasons"] = ["Run is not saved yet."]
        payload["delivery_review"] = {
            "resource_type": "agent_run",
            "resource_id": run.id,
            "deliverable": False,
            "publish_allowed": False,
            "blocking_reasons": ["Run is not saved yet."],
        }
        return {"run": payload, "eval_candidate": None, "poll": {"run_id": run.id, "queue_status": "queued", "status": "queued"}}

    monkeypatch.setattr("research_agent.webapp.start_workspace_research_run", fake_start_workspace_research_run)
    monkeypatch.setattr("research_agent.webapp.retry_workspace_research_run", fake_retry_workspace_research_run)

    created = client.post(
        f"/api/workspaces/{workspace_id}/research/runs",
        headers=_csrf_headers(client),
        json={
            "topic": "Inflation persistence",
            "question": "What explains inflation persistence?",
            "instructions": "Focus on wage dynamics.",
            "asset_ids": [asset.id],
            "case_id": case.id,
            "draft_variants": 2,
            "mode": "deep_research",
        },
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()
    created_run = created_payload["run"]
    assert created_run["status"] == "queued"
    assert created_run["queue_status"] == "queued"
    assert created_run["attachment_count"] == 1
    assert created_run["publish_allowed"] is False
    assert created_payload["eval_candidate"] is None
    assert created_payload["poll"]["queue_status"] == "queued"

    listed = client.get(f"/api/workspaces/{workspace_id}/research/runs")
    assert listed.status_code == 200, listed.text
    listed_items = {item["id"]: item for item in listed.json()["items"]}
    assert created_run["id"] in listed_items
    assert listed_items[created_run["id"]]["queue_status"] == "queued"
    assert listed_items[created_run["id"]]["attachment_count"] == 1

    detail = client.get(f"/api/workspaces/{workspace_id}/research/runs/{created_run['id']}")
    assert detail.status_code == 200, detail.text
    detail_payload = detail.json()
    assert detail_payload["run"]["attachments"][0]["asset_id"] == asset.id
    assert detail_payload["run"]["queue_status"] == "queued"
    assert detail_payload["run"]["publish_allowed"] is False
    assert detail_payload["eval_candidate"] is None

    eval_candidates = client.get(f"/api/workspaces/{workspace_id}/research/runs/eval-candidates")
    assert eval_candidates.status_code == 200, eval_candidates.text
    eval_payload = eval_candidates.json()
    assert eval_payload["dataset_version"] == "research-agent-v2"
    assert all(item["run_id"] != created_run["id"] for item in eval_payload["items"])

    retried = client.post(
        f"/api/workspaces/{workspace_id}/research/runs/{blocked_run.id}/retry",
        headers=_csrf_headers(client),
        json={
            "instructions": "Use the chart evidence and fix missing citations.",
            "asset_ids": [extra_asset.id],
            "draft_variants": 1,
        },
    )
    assert retried.status_code == 200, retried.text
    retried_payload = retried.json()
    assert retried_payload["run"]["id"] == blocked_run.id
    assert retried_payload["run"]["status"] == "queued"
    assert retried_payload["run"]["queue_status"] == "queued"
    assert retried_payload["eval_candidate"] is None

    retried_detail = client.get(f"/api/workspaces/{workspace_id}/research/runs/{blocked_run.id}")
    assert retried_detail.status_code == 200, retried_detail.text
    assert retried_detail.json()["run"]["status"] == "queued"

    filtered_queued = client.get(f"/api/workspaces/{workspace_id}/research/runs", params={"status": "queued"})
    assert filtered_queued.status_code == 200, filtered_queued.text
    filtered_ids = {item["id"] for item in filtered_queued.json()["items"]}
    assert created_run["id"] in filtered_ids
    assert blocked_run.id in filtered_ids


def test_team_library_endpoints(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)
    now = datetime.now(timezone.utc)

    team_response = client.post(
        "/api/teams",
        headers=_csrf_headers(client),
        json={"name": "Research Team", "description": "Shared publication library."},
    )
    assert team_response.status_code == 200, team_response.text
    team_id = team_response.json()["team"]["id"]

    attach_response = client.post(
        f"/api/workspaces/{workspace_id}/team",
        headers=_csrf_headers(client),
        json={"team_id": team_id},
    )
    assert attach_response.status_code == 200, attach_response.text
    assert attach_response.json()["workspace"]["team_id"] == team_id

    run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="publishable-run",
        topic="Industrial policy",
        question="What makes industrial policy effective?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        queue_status="completed",
        final_text="# Topic\nIndustrial policy\n\n# References\n- [S1] Policy paper",
        review_json={"status": "approved", "summary": "Approved.", "findings": []},
        evidence_json={"included_source_ids": ["S1"], "items": [{"source_id": "S1", "title": "Policy paper"}]},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0, "review_status": "approved"},
        report_path="storage/reports/publishable-run/report.md",
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=4),
    )
    knowledge = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Policy Note",
        content="Team-ready knowledge note.",
        tags_json=["policy"],
        metadata_json={"source_type": "workspace_note"},
    )
    db_session.add_all([run, knowledge])
    db_session.commit()

    publish_run_response = client.post(
        f"/api/workspaces/{workspace_id}/research/runs/{run.id}/publish",
        headers=_csrf_headers(client),
        json={"team_id": team_id, "title": "Industrial Policy Report", "summary": "Approved team report."},
    )
    assert publish_run_response.status_code == 200, publish_run_response.text
    published_run_record = publish_run_response.json()["record"]
    assert published_run_record["source_type"] == "agent_run"
    assert publish_run_response.json()["delivery_review"]["publish_allowed"] is True

    publish_knowledge_response = client.post(
        f"/api/workspaces/{workspace_id}/knowledge/{knowledge.id}/publish",
        headers=_csrf_headers(client),
        json={"team_id": team_id, "title": "Policy Knowledge", "summary": "Useful note."},
    )
    assert publish_knowledge_response.status_code == 200, publish_knowledge_response.text
    published_knowledge_record = publish_knowledge_response.json()["record"]
    assert published_knowledge_record["source_type"] == "knowledge_record"
    assert publish_knowledge_response.json()["delivery_review"]["publish_allowed"] is True

    team_library_response = client.get(f"/api/teams/{team_id}/library")
    assert team_library_response.status_code == 200, team_library_response.text
    team_items = team_library_response.json()["items"]
    assert len(team_items) >= 2

    detail_response = client.get(f"/api/teams/{team_id}/library/{published_run_record['id']}")
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["record"]["content"].startswith("# Topic")

    clone_response = client.post(
        f"/api/teams/{team_id}/library/{published_run_record['id']}/clone",
        headers=_csrf_headers(client),
        json={"workspace_id": workspace_id, "title": "Cloned Industrial Policy Report", "include_source_metadata": True},
    )
    assert clone_response.status_code == 200, clone_response.text
    cloned_record = clone_response.json()["record"]
    assert cloned_record["title"] == "Cloned Industrial Policy Report"
    assert cloned_record["metadata"]["team_library_record_id"] == published_run_record["id"]


def test_quality_and_spa_routes(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)
    run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="quality-api-run",
        topic="Quality API",
        question="Does the API expose business scorecards?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        queue_status="completed",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Topic\nQuality API\n\n# References\n- [S1] Quality paper",
        report_path="storage/reports/quality-api-run/report.md",
        quality_json={"quality_score": 100},
    )
    db_session.add(run)
    db_session.commit()

    scorecard = client.get(f"/api/workspaces/{workspace_id}/quality/scorecard")
    assert scorecard.status_code == 200, scorecard.text
    assert scorecard.json()["total_score"] == 500
    assert scorecard.json()["active_bundle"] is None
    assert scorecard.json()["business_deliverable"] is True
    assert scorecard.json()["deliverable"] is True

    quality_runs = client.get(f"/api/workspaces/{workspace_id}/quality/runs")
    assert quality_runs.status_code == 200, quality_runs.text
    assert quality_runs.json()["items"][0]["run_id"] == run.id
    assert quality_runs.json()["items"][0]["runtime_bundle_version"] == ""
    assert quality_runs.json()["items"][0]["publish_allowed"] is True

    spa_root = client.get("/app", follow_redirects=False)
    assert spa_root.status_code == 200
    assert "text/html" in spa_root.headers["content-type"]

    spa_research = client.get("/app/research", follow_redirects=False)
    assert spa_research.status_code == 200
    assert "text/html" in spa_research.headers["content-type"]

    provider_center = client.get("/provider-center", follow_redirects=False)
    assert provider_center.status_code == 200
    assert "not part of the current product scope" in provider_center.text.lower()


def test_spa_routes_require_auth(client):
    response = client.get("/app", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_publish_endpoints_block_non_deliverable_artifacts(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)

    team_response = client.post(
        "/api/teams",
        headers=_csrf_headers(client),
        json={"name": "Blocked Team", "description": "Delivery gate test."},
    )
    assert team_response.status_code == 200, team_response.text
    team_id = team_response.json()["team"]["id"]

    attach_response = client.post(
        f"/api/workspaces/{workspace_id}/team",
        headers=_csrf_headers(client),
        json={"team_id": team_id},
    )
    assert attach_response.status_code == 200, attach_response.text

    blocked_run = AgentRun(
        owner_user_id=user_id,
        workspace_id=workspace_id,
        session_id="blocked-publish-run",
        topic="Blocked publish",
        question="Should publishing be blocked?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        queue_status="completed",
        review_json={"status": "blocked", "summary": "Blocked.", "missing_sections": ["References"], "invalid_source_ids": [], "unsupported_claim_count": 1},
        metrics_json={"citation_coverage": 0.5, "unsupported_claim_count": 1},
        final_text="# Topic\nBlocked publish",
        report_path="storage/reports/blocked-publish/report.md",
    )
    blocked_record = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Blocked note",
        content="",
        tags_json=["blocked"],
        metadata_json={},
    )
    db_session.add_all([blocked_run, blocked_record])
    db_session.commit()

    publish_run_response = client.post(
        f"/api/workspaces/{workspace_id}/research/runs/{blocked_run.id}/publish",
        headers=_csrf_headers(client),
        json={"team_id": team_id},
    )
    assert publish_run_response.status_code == 409, publish_run_response.text
    assert publish_run_response.json()["detail"]["delivery_review"]["publish_allowed"] is False

    publish_knowledge_response = client.post(
        f"/api/workspaces/{workspace_id}/knowledge/{blocked_record.id}/publish",
        headers=_csrf_headers(client),
        json={"team_id": team_id},
    )
    assert publish_knowledge_response.status_code == 409, publish_knowledge_response.text
    assert publish_knowledge_response.json()["detail"]["delivery_review"]["publish_allowed"] is False
