from __future__ import annotations

from fastapi.testclient import TestClient


def _reset_app_caches() -> None:
    from research_agent.config import get_settings
    from research_agent.db import get_engine, get_session_factory

    for maybe_cached in (get_settings, get_engine, get_session_factory):
        cache_clear = getattr(maybe_cached, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


def _client_with_agent(monkeypatch, *, trusted_execution: bool) -> TestClient:
    monkeypatch.setenv("DATA_LAB_AGENT_ENABLED", "true")
    if trusted_execution:
        monkeypatch.setenv("DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED", "true")
    else:
        monkeypatch.delenv("DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED", raising=False)
    _reset_app_caches()
    from research_agent.webapp import create_app

    return TestClient(create_app())


def _register_workspace(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        headers={"Origin": "http://testserver"},
        json={"email": "risk@example.com", "password": "StrongPass!2026", "full_name": "Risk User"},
    )
    assert response.status_code == 200, response.text
    csrf_token = client.cookies.get("erp_csrf_token")
    assert csrf_token
    workspace = client.post(
        "/api/workspaces",
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Risk Workspace", "description": "Agent risk tests"},
    )
    assert workspace.status_code == 200, workspace.text
    return {"csrf": csrf_token, "workspace_id": workspace.json()["workspace"]["id"]}


def _upload_csv(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post(
        f"/api/workspaces/{auth['workspace_id']}/assets/upload",
        headers={"X-CSRF-Token": auth["csrf"]},
        data={"description": "agent dataset"},
        files={"file": ("risk.csv", b"y,x\n1,1\n2,2\n3,3\n", "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]["id"]


def test_agent_config_and_session_expose_public_risk_summary(monkeypatch, app_env):
    client = _client_with_agent(monkeypatch, trusted_execution=False)
    auth = _register_workspace(client)
    asset_id = _upload_csv(client, auth)

    config = client.get(f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/llm-config")
    assert config.status_code == 200, config.text
    assert config.json()["risk_summary"]["sandbox_claim"] == "none"
    assert config.json()["risk_summary"]["trusted_execution_enabled"] is False
    assert "not sandboxed" in config.json()["risk_summary"]["warning_message"].lower()
    assert "\\" not in config.text

    created = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"asset_ids": [asset_id], "title": "Risk Session", "language": "Chinese"},
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    assert session["risk_summary"]["sandbox_claim"] == "none"
    assert session["risk_summary"]["trusted_execution_enabled"] is False
    assert "work_dir" not in session
    assert ":/" not in created.text
    assert ":\\" not in created.text


def test_trusted_execution_disabled_blocks_user_code_and_notebook_requires_csrf(monkeypatch, app_env):
    client = _client_with_agent(monkeypatch, trusted_execution=False)
    auth = _register_workspace(client)
    asset_id = _upload_csv(client, auth)
    created = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"asset_ids": [asset_id], "title": "Blocked Code", "language": "Chinese"},
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["session"]["run_id"]

    blocked = client.post(
        f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/messages",
        headers={"X-CSRF-Token": auth["csrf"]},
        json={"message": "Count rows.", "user_code": "print(len(df))"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["message"]["execution"]["error_type"] == "trusted_execution_required"
    assert blocked.json()["message"]["execution"]["risk_audit"]["sandbox_claim"] == "none"

    no_csrf = client.post(f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/notebook")
    assert no_csrf.status_code == 403

    unauthenticated = TestClient(client.app)
    download = unauthenticated.get(f"/api/workspaces/{auth['workspace_id']}/data-lab/agent/sessions/{run_id}/notebook")
    assert download.status_code in {401, 404}
