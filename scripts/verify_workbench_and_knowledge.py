from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "蒙特卡洛" / "workbench_knowledge"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def expect_status(response, expected: int) -> None:
    assert response.status_code == expected, response.text


def main() -> None:
    temp_dir = ROOT / "storage" / "verify_workbench"
    temp_dir.mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "platform.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["APP_SECRET"] = "verify-workbench-secret"
    os.environ["STORAGE_DIR"] = str(temp_dir)
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str(temp_dir / "reports")
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"

    from research_agent.webapp import create_app

    app = create_app()

    with TestClient(app) as client:
        index_response = client.get("/")
        expect_status(index_response, 200)
        html = index_response.text
        assert "Workspace Cockpit" in html
        assert 'id="cockpit-stat-grid"' in html
        assert 'id="knowledge-search-form"' in html
        assert 'id="knowledge-preview"' in html

        register_response = client.post(
            "/api/auth/register",
            json={"email": "workbench@example.com", "password": "test-pass-123", "full_name": "Workbench User"},
        )
        expect_status(register_response, 200)
        token = register_response.json()["session_token"]

        workspace_response = client.post(
            "/api/workspaces",
            headers=auth_headers(token),
            json={"name": "Workbench QA", "description": "Verify cockpit and private knowledge features."},
        )
        expect_status(workspace_response, 200)
        workspace_id = workspace_response.json()["workspace"]["id"]

        note_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge",
            headers=auth_headers(token),
            json={
                "title": "Research Memo: FX Spillovers",
                "content": "## Question\n\nHow do U.S. rate shocks affect Asian FX returns?\n\n## Next step\n\nEstimate a baseline VAR.",
                "tags": ["memo", "fx", "spillover"],
                "metadata": {"source_type": "manual_workspace", "note_template": "research_memo"},
            },
        )
        expect_status(note_response, 200)
        record_id = note_response.json()["record"]["id"]

        large_content = "capacity-check-" * 20000
        large_note_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge",
            headers=auth_headers(token),
            json={
                "title": "Knowledge Capacity Stress",
                "content": large_content,
                "tags": ["capacity", "stress"],
                "metadata": {"source_type": "manual_workspace"},
            },
        )
        expect_status(large_note_response, 200)
        large_record_id = large_note_response.json()["record"]["id"]

        summary_list = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary",
            headers=auth_headers(token),
        )
        expect_status(summary_list, 200)
        summary_items = summary_list.json()["items"]
        assert len(summary_items) == 2
        memo_summary = next(item for item in summary_items if item["id"] == record_id)
        large_summary = next(item for item in summary_items if item["id"] == large_record_id)
        assert memo_summary["content"] == ""
        assert memo_summary["content_excerpt"]
        assert large_summary["content"] == ""
        assert large_summary["content_length"] == len(large_content)

        detail_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{large_record_id}",
            headers=auth_headers(token),
        )
        expect_status(detail_response, 200)
        detail_record = detail_response.json()["record"]
        assert len(detail_record["content"]) == len(large_content)

        search_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?q=spillovers&view=summary",
            headers=auth_headers(token),
        )
        expect_status(search_response, 200)
        search_items = search_response.json()["items"]
        assert len(search_items) == 1
        assert search_items[0]["id"] == record_id

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "verification_report.json").write_text(
        json.dumps(
            {
                "homepage": {
                    "contains_workspace_cockpit": True,
                    "contains_knowledge_search_form": True,
                    "contains_knowledge_preview": True,
                },
                "knowledge_summary_view": {
                    "record_count": 2,
                    "summary_omits_full_content": memo_summary["content"] == "",
                    "large_note_content_length": large_summary["content_length"],
                },
                "knowledge_detail_view": {
                    "large_note_chars_read_back": len(detail_record["content"]),
                },
                "knowledge_search": {
                    "query": "spillovers",
                    "match_count": len(search_items),
                    "matched_record_id": search_items[0]["id"],
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
