from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _reset_app_caches() -> None:
    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


def _new_client_with_agent_enabled(
    monkeypatch,
    app_env: Path,
    *,
    math_mode: str = "off",
    trusted_execution: bool = True,
) -> TestClient:
    del app_env
    monkeypatch.setenv("DATA_LAB_AGENT_ENABLED", "true")
    if trusted_execution:
        monkeypatch.setenv("DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED", "true")
    else:
        monkeypatch.delenv("DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("DATA_LAB_AGENT_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("AGENT_MATH_MODE", math_mode)
    _reset_app_caches()
    from research_agent.webapp import create_app

    return TestClient(create_app())


def _register_workspace(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        headers={"Origin": "http://testserver"},
        json={
            "email": "agent@example.com",
            "password": "StrongPass!2026",
            "full_name": "Agent User",
        },
    )
    assert response.status_code == 200, response.text
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token
    workspace = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Agent Workspace", "description": "Data Lab Agent tests"},
    )
    assert workspace.status_code == 200, workspace.text
    return {"csrf": csrf_token, "workspace_id": workspace.json()["workspace"]["id"]}


def _upload_agent_csv(client: TestClient, *, workspace_id: str, csrf_token: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "agent dataset"},
        files={
            "file": (
                "agent-sample.csv",
                b"date,y,x,group\n2026-01-01,1,2,A\n2026-01-02,2,3,A\n2026-01-03,3,5,B\n2026-01-04,4,8,B\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]


def test_data_lab_agent_feature_flag_is_disabled_by_default(client, auth_headers):
    response = client.post(
        f"/api/workspaces/{auth_headers['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth_headers["csrf"]},
        json={"asset_ids": ["asset-does-not-matter"], "title": "Disabled"},
    )

    assert response.status_code == 401
    assert "Data Lab Agent is disabled" in response.text


def test_data_lab_agent_refuses_code_without_trusted_execution(monkeypatch, app_env):
    client = _new_client_with_agent_enabled(monkeypatch, app_env, trusted_execution=False)
    auth = _register_workspace(client)
    asset = _upload_agent_csv(client, workspace_id=auth["workspace_id"], csrf_token=auth["csrf"])

    created = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"asset_ids": [asset["id"]], "title": "Untrusted Session", "language": "Chinese"},
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    assert session["executor"]["trusted_execution_enabled"] is False
    assert session["executor"]["trusted_execution"]["flag"] == "DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED"
    assert session["executor"]["trusted_execution"]["enabled"] is False
    run_id = session["run_id"]

    response = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Count rows.", "user_code": "print(len(df))"},
    )
    assert response.status_code == 200, response.text
    message = response.json()["message"]
    assert message["status"] == "blocked"
    assert message["execution"]["error_type"] == "trusted_execution_required"
    assert message["execution"]["execution_mode"] == "not_executed"
    assert message["execution"]["trace"]["trusted_execution_enabled"] is False
    assert message["execution"]["risk_audit"]["sandbox_claim"] == "none"
    assert response.json()["session"]["cells"] == []


def test_data_lab_agent_session_repair_manual_code_report_and_notebook(monkeypatch, app_env):
    client = _new_client_with_agent_enabled(monkeypatch, app_env, math_mode="shadow")
    auth = _register_workspace(client)
    asset = _upload_agent_csv(client, workspace_id=auth["workspace_id"], csrf_token=auth["csrf"])

    created = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"asset_ids": [asset["id"]], "title": "Clean-room Session", "language": "Chinese"},
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    run_id = session["run_id"]
    assert session["assets"][0]["profile"]["rows"] == 4
    assert "y" in session["assets"][0]["profile"]["column_names"]
    assert session["assets"][0]["profile"]["profile_version"] == 2
    assert session["assets"][0]["profile"]["schema_fingerprint"]

    repaired = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Plot a histogram of `missing_column`."},
    )
    assert repaired.status_code == 200, repaired.text
    repaired_message = repaired.json()["message"]
    assert repaired_message["status"] == "success"
    assert repaired_message["repair_trace"]
    assert repaired_message["execution_mode"] == "subprocess_replay"
    assert repaired_message["execution"]["risk_audit"]["trusted_execution_enabled"] is True
    assert repaired_message["execution"]["risk_audit"]["trusted_execution_flag"] == "DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED"
    assert repaired_message["execution"]["risk_audit"]["artifact_quota"]["max_count"] >= 1
    assert repaired_message["execution"]["risk_audit"]["output_dir_validated"] is True
    assert repaired_message["execution"]["risk_audit"]["sandbox_claim"] == "none"
    assert repaired_message["artifact_manifest"]["count"] >= 0
    assert repaired_message["knowledge_cards"]
    assert repaired_message["profile_snapshot"]["schema_fingerprint"]
    assert repaired_message["math_trace"]["mode"] == "shadow"
    assert repaired_message["math_trace"]["override_margin"] == 0.05
    assert repaired_message["math_trace"]["retrieval"]["candidate_count"] >= repaired_message["math_trace"]["retrieval"]["selected_count"]
    assert repaired_message["math_trace"]["retrieval"]["v2"]["comparison"]["fallback_reason"] == "shadow_mode_preserves_baseline"
    assert repaired_message["math_trace"]["repair_decisions"]
    assert repaired_message["math_trace"]["repair_decisions"][0]["v2"]["comparison"]["fallback_reason"] == "shadow_mode_preserves_baseline"
    assert repaired_message["math_trace"]["v2_state_summary"]["successful_cell_count"] >= 1
    assert "Available columns" in repaired_message["execution"]["stdout"]

    outside_write = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Attempt outside output write.", "user_code": "np.save('outside-output.npy', df[['y']].to_numpy())"},
    )
    assert outside_write.status_code == 200, outside_write.text
    outside_message = outside_write.json()["message"]
    assert outside_message["status"] == "needs_human_intervention"
    assert outside_message["execution"]["error_type"] == "file_write_outside_output"
    assert outside_message["execution"]["trace"]["error_type"] == "file_write_outside_output"

    manual = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Manual correlation check.", "user_code": "print(df[['y', 'x']].corr().round(3).to_string())"},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["message"]["status"] == "success"
    assert "1.000" in manual.json()["message"]["execution"]["stdout"]
    assert manual.json()["message"]["execution"]["error_type"] == "none"

    blocked = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Try unsafe code.", "user_code": "import os\nos.system('echo blocked')"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["message"]["status"] == "blocked"
    assert blocked.json()["message"]["execution"]["error_type"] == "safety_policy_violation"
    assert "not allowed" in blocked.json()["message"]["execution"]["error"]

    syntax_error = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Manual syntax check.", "user_code": "print("},
    )
    assert syntax_error.status_code == 200, syntax_error.text
    assert syntax_error.json()["message"]["status"] == "needs_human_intervention"
    assert syntax_error.json()["message"]["human_intervention"]["required"] is True

    report = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/report",
        headers={"X-CSRF-Token": auth["csrf"]},
    )
    assert report.status_code == 200, report.text
    assert "Analysis Steps" in report.json()["report"]["markdown"]

    notebook = client.get(f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/notebook")
    assert notebook.status_code == 200, notebook.text
    assert notebook.headers["X-Content-Type-Options"] == "nosniff"
    assert notebook.json()["nbformat"] == 4

    detail = client.get(f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}")
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["session"]["cells"]) >= 2
    assert detail.json()["session"]["profile_snapshots"]
    assert detail.json()["session"]["safety_events"]
    assert detail.json()["session"]["math"]["mode"] == "shadow"
    assert detail.json()["session"]["math"]["v2_state_summary"]["run_status"] in {"ready", "blocked", "needs_human_intervention"}

    history = client.get(f"/api/workspaces/{auth['workspace_id']}/data-lab/history")
    assert history.status_code == 200, history.text
    assert any(item["id"] == run_id for item in history.json()["agent_sessions"])


def test_data_lab_agent_scoped_llm_config_endpoints(client, auth_headers, monkeypatch):
    csrf_token = auth_headers["csrf"]
    workspace_id = auth_headers["workspace_id"]

    def fake_post(*args, **kwargs):
        del args, kwargs

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": json.dumps({"status": "ok", "note": "pong"})}}]}

        return FakeResponse()

    monkeypatch.setattr("research_agent.data_lab_agent_llm.requests.post", fake_post)

    saved = client.put(
        f"/api/workspaces/{workspace_id}/data-lab/agent/llm-config",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "enabled": True,
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "workspace-secret",
            "coder_model": "coder-model",
            "reviewer_model": "reviewer-model",
            "report_model": "report-model",
            "label": "Scoped Agent LLM",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["workspace"]["api_key_configured"] is True
    assert "workspace-secret" not in saved.text
    assert saved.json()["resolved"]["source"] == "workspace"
    assert saved.json()["resolved"]["coder_model"] == "coder-model"

    fetched = client.get(f"/api/workspaces/{workspace_id}/data-lab/agent/llm-config")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["workspace"]["base_url"] == "http://127.0.0.1:1234/v1"
    assert "workspace-secret" not in fetched.text

    tested = client.post(
        f"/api/workspaces/{workspace_id}/data-lab/agent/llm-config/test",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["status"] == "ok"


def test_data_lab_agent_uses_env_llm_with_rule_fallback_available(monkeypatch, app_env):
    monkeypatch.setenv("DATA_LAB_AGENT_ENABLED", "true")
    monkeypatch.setenv("DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("DATA_LAB_AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("DATA_LAB_AGENT_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("DATA_LAB_AGENT_CODER_MODEL", "env-coder")
    monkeypatch.setenv("DATA_LAB_AGENT_REVIEWER_MODEL", "env-reviewer")
    monkeypatch.setenv("DATA_LAB_AGENT_REPORT_MODEL", "env-report")
    monkeypatch.setenv("DATA_LAB_AGENT_TIMEOUT_SECONDS", "15")
    calls: list[dict] = []

    def fake_post(*args, **kwargs):
        del args
        calls.append(kwargs.get("json") or {})

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "code": "print('llm rows', len(df))",
                                        "explanation": "LLM generated a safe row-count cell.",
                                        "risk_notes": [],
                                    }
                                )
                            }
                        }
                    ]
                }

        return FakeResponse()

    monkeypatch.setattr("research_agent.data_lab_agent_llm.requests.post", fake_post)
    _reset_app_caches()
    from research_agent.webapp import create_app

    client = TestClient(create_app())
    auth = _register_workspace(client)
    asset = _upload_agent_csv(client, workspace_id=auth["workspace_id"], csrf_token=auth["csrf"])
    created = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"asset_ids": [asset["id"]], "title": "LLM Session", "language": "Chinese"},
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["session"]["run_id"]

    response = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Count rows with the configured LLM."},
    )
    assert response.status_code == 200, response.text
    message = response.json()["message"]
    assert message["status"] == "success"
    assert message["coder_source"] == "llm"
    assert "llm rows 4" in message["execution"]["stdout"]
    assert any(item["source"] == "llm" for item in message["llm_trace_summary"])
    assert calls[0]["model"] == "env-coder"
