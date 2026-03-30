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

    from research_agent.db import session_scope
    from research_agent.entities import EconomicBriefing
    from research_agent.webapp import create_app

    app = create_app()

    with TestClient(app) as client:
        index_response = client.get("/")
        expect_status(index_response, 200)
        html = index_response.text
        assert "Workspace Cockpit" in html
        assert "Research Flow Lane" in html
        assert "Cross-Module Surface Map" in html
        assert 'id="cockpit-flow-list"' in html
        assert 'id="cockpit-linkage-grid"' in html
        assert 'id="knowledge-search-form"' in html
        assert 'id="knowledge-status-filter"' in html
        assert 'id="knowledge-preview"' in html
        assert 'id="knowledge-form-title"' in html
        assert 'id="knowledge-cancel-button"' in html
        assert "Knowledge Linkage Board" in html
        assert 'id="knowledge-linkage-grid"' in html

        result_page_response = client.get("/data-lab/results/models/demo-model-result")
        expect_status(result_page_response, 200)
        result_html = result_page_response.text
        assert "Export & Reuse Board" in result_html
        assert 'id="lab-result-export-board"' in result_html

        register_response = client.post(
            "/api/auth/register",
            json={"email": "workbench@example.com", "password": "test-pass-123", "full_name": "Workbench User"},
        )
        expect_status(register_response, 200)
        register_payload = register_response.json()
        token = register_payload["session_token"]
        user_id = register_payload["user"]["id"]

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

        related_note_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge",
            headers=auth_headers(token),
            json={
                "title": "FX Spillover Checklist",
                "content": "## Checklist\n\n- Compare FX and bond reactions.\n- Track spillover persistence.\n- Note identification caveats.",
                "tags": ["fx", "spillover", "checklist"],
                "metadata": {"source_type": "manual_workspace", "note_template": "hypothesis_log"},
            },
        )
        expect_status(related_note_response, 200)
        related_record_id = related_note_response.json()["record"]["id"]

        summary_list = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary&status=all",
            headers=auth_headers(token),
        )
        expect_status(summary_list, 200)
        summary_items = summary_list.json()["items"]
        assert len(summary_items) == 3
        memo_summary = next(item for item in summary_items if item["id"] == record_id)
        large_summary = next(item for item in summary_items if item["id"] == large_record_id)
        assert memo_summary["content"] == ""
        assert memo_summary["content_excerpt"]
        assert large_summary["content"] == ""
        assert large_summary["content_length"] == len(large_content)

        update_response = client.patch(
            f"/api/workspaces/{workspace_id}/knowledge/{record_id}",
            headers=auth_headers(token),
            json={
                "title": "Research Memo: FX Spillovers Revised",
                "content": "## Updated question\n\nHow do rate shocks transmit into Asian FX and bond markets?\n\n## Manual checks\n\n- Rebuild the baseline VAR.\n- Compare pre/post subsamples.",
                "tags": ["memo", "fx", "spillover", "revised"],
                "metadata": {"editor": "qa-script"},
            },
        )
        expect_status(update_response, 200)
        updated_record = update_response.json()["record"]
        assert updated_record["title"] == "Research Memo: FX Spillovers Revised"
        assert "bond markets" in updated_record["content"]
        assert "revised" in updated_record["tags"]
        assert updated_record["metadata"]["editor"] == "qa-script"

        detail_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{record_id}",
            headers=auth_headers(token),
        )
        expect_status(detail_response, 200)
        detail_record = detail_response.json()["record"]
        assert detail_record["title"] == "Research Memo: FX Spillovers Revised"
        assert "bond markets" in detail_record["content"]

        large_detail_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{large_record_id}",
            headers=auth_headers(token),
        )
        expect_status(large_detail_response, 200)
        large_detail = large_detail_response.json()["record"]
        assert len(large_detail["content"]) == len(large_content)

        archive_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge/{record_id}/archive",
            headers=auth_headers(token),
            json={"reason": "Covered by a later synthesis note."},
        )
        expect_status(archive_response, 200)
        archived_record = archive_response.json()["record"]
        assert archived_record["is_archived"] is True
        assert archived_record["archived_reason"] == "Covered by a later synthesis note."

        active_list_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary&status=active",
            headers=auth_headers(token),
        )
        expect_status(active_list_response, 200)
        active_items = active_list_response.json()["items"]
        assert {item["id"] for item in active_items} == {large_record_id, related_record_id}

        archived_list_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary&status=archived",
            headers=auth_headers(token),
        )
        expect_status(archived_list_response, 200)
        archived_items = archived_list_response.json()["items"]
        assert len(archived_items) == 1
        assert archived_items[0]["id"] == record_id
        assert archived_items[0]["is_archived"] is True

        restore_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge/{record_id}/restore",
            headers=auth_headers(token),
        )
        expect_status(restore_response, 200)
        restored_record = restore_response.json()["record"]
        assert restored_record["is_archived"] is False

        restored_active_list = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary&status=active",
            headers=auth_headers(token),
        )
        expect_status(restored_active_list, 200)
        restored_active_items = restored_active_list.json()["items"]
        assert {item["id"] for item in restored_active_items} == {record_id, large_record_id, related_record_id}

        search_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?q=bond markets&view=summary&status=all",
            headers=auth_headers(token),
        )
        expect_status(search_response, 200)
        search_items = search_response.json()["items"]
        assert len(search_items) == 1
        assert search_items[0]["id"] == record_id

        related_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{record_id}/related?limit=4",
            headers=auth_headers(token),
        )
        expect_status(related_response, 200)
        related_items = related_response.json()["items"]
        assert related_items
        assert related_items[0]["id"] == related_record_id
        assert "Shared tags" in " | ".join(related_items[0]["relation_reasons"])

        with session_scope() as db:
            briefing = EconomicBriefing(
                workspace_id=workspace_id,
                owner_user_id=user_id,
                integration_id=None,
                title="QA Briefing",
                summary_markdown="## Overnight signal\n\nTreasury yields rose while Asia FX softened.\n\n## Checks\n\n- Review policy headlines.\n- Compare with the previous close.",
                query_text="treasury yields asia fx",
                headline_count=2,
                items_json=[
                    {"title": "Fed signal firms yields", "url": "https://example.com/fed", "domain": "example.com"},
                    {"title": "Asia FX softens overnight", "url": "https://example.com/fx", "domain": "example.com"},
                ],
                raw_json={},
            )
            db.add(briefing)
            db.flush()
            briefing_id = briefing.id

        import_briefing_response = client.post(
            f"/api/workspaces/{workspace_id}/briefings/{briefing_id}/import-knowledge",
            headers=auth_headers(token),
        )
        expect_status(import_briefing_response, 200)
        briefing_import_payload = import_briefing_response.json()
        briefing_record_id = briefing_import_payload["record"]["id"]
        assert briefing_import_payload["briefing"]["workspace_knowledge_record_id"] == briefing_record_id

        briefing_list_response = client.get(
            f"/api/workspaces/{workspace_id}/briefings",
            headers=auth_headers(token),
        )
        expect_status(briefing_list_response, 200)
        briefing_item = next(item for item in briefing_list_response.json()["items"] if item["id"] == briefing_id)
        assert briefing_item["workspace_knowledge_record_id"] == briefing_record_id
        assert briefing_item["workspace_knowledge_record_title"] == briefing_import_payload["record"]["title"]

        digest_response = client.post(
            f"/api/workspaces/{workspace_id}/knowledge/digest",
            headers=auth_headers(token),
        )
        expect_status(digest_response, 200)
        digest_record = digest_response.json()["record"]
        assert digest_record["metadata"]["source_type"] == "workspace_digest"
        digest_detail_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{digest_record['id']}",
            headers=auth_headers(token),
        )
        expect_status(digest_detail_response, 200)
        digest_detail = digest_detail_response.json()["record"]
        assert "Workspace Digest: Workbench QA" in digest_detail["title"]
        assert "QA Briefing" in digest_detail["content"]
        assert "Research Memo: FX Spillovers Revised" in digest_detail["content"]

        delete_briefing_record_response = client.delete(
            f"/api/workspaces/{workspace_id}/knowledge/{briefing_record_id}",
            headers=auth_headers(token),
        )
        expect_status(delete_briefing_record_response, 200)
        detach_payload = delete_briefing_record_response.json()
        assert detach_payload["status"] == "deleted"
        assert detach_payload["detached_references"]["briefings"] == 1

        briefing_list_after_delete = client.get(
            f"/api/workspaces/{workspace_id}/briefings",
            headers=auth_headers(token),
        )
        expect_status(briefing_list_after_delete, 200)
        detached_briefing = next(item for item in briefing_list_after_delete.json()["items"] if item["id"] == briefing_id)
        assert detached_briefing["workspace_knowledge_record_id"] == ""

        delete_large_note_response = client.delete(
            f"/api/workspaces/{workspace_id}/knowledge/{large_record_id}",
            headers=auth_headers(token),
        )
        expect_status(delete_large_note_response, 200)

        all_after_delete = client.get(
            f"/api/workspaces/{workspace_id}/knowledge?view=summary&status=all",
            headers=auth_headers(token),
        )
        expect_status(all_after_delete, 200)
        remaining_items = all_after_delete.json()["items"]
        remaining_ids = {item["id"] for item in remaining_items}
        assert remaining_ids == {record_id, related_record_id, digest_record["id"]}

        deleted_detail_response = client.get(
            f"/api/workspaces/{workspace_id}/knowledge/{large_record_id}",
            headers=auth_headers(token),
        )
        assert deleted_detail_response.status_code == 404

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_payload = {
        "homepage": {
            "contains_workspace_cockpit": True,
            "contains_research_flow_lane": True,
            "contains_cross_module_surface_map": True,
            "contains_knowledge_status_filter": True,
            "contains_knowledge_preview": True,
            "contains_editable_knowledge_form": True,
            "contains_knowledge_linkage_board": True,
        },
        "result_page_template": {
            "contains_export_reuse_board": True,
        },
        "knowledge_summary_view": {
            "record_count_before_delete": 3,
            "summary_omits_full_content": memo_summary["content"] == "",
            "large_note_content_length": large_summary["content_length"],
        },
        "knowledge_detail_view": {
            "updated_record_title": detail_record["title"],
            "large_note_chars_read_back": len(large_detail["content"]),
        },
        "knowledge_lifecycle": {
            "archive_reason": archived_record["archived_reason"],
            "active_after_archive": [item["id"] for item in active_items],
            "archived_after_archive": [item["id"] for item in archived_items],
            "active_after_restore": [item["id"] for item in restored_active_items],
            "remaining_after_delete": [item["id"] for item in remaining_items],
        },
        "knowledge_search": {
            "query": "bond markets",
            "match_count": len(search_items),
            "matched_record_id": search_items[0]["id"],
        },
        "knowledge_related": {
            "source_record_id": record_id,
            "top_related_record_id": related_items[0]["id"],
            "top_related_score": related_items[0]["relation_score"],
            "top_related_reasons": related_items[0]["relation_reasons"],
        },
        "workspace_digest": {
            "digest_record_id": digest_record["id"],
            "digest_title": digest_detail["title"],
            "contains_briefing_title": "QA Briefing" in digest_detail["content"],
            "contains_updated_note_title": "Research Memo: FX Spillovers Revised" in digest_detail["content"],
        },
        "briefing_to_knowledge_flow": {
            "briefing_id": briefing_id,
            "imported_record_id": briefing_record_id,
            "linked_before_delete": briefing_item["workspace_knowledge_record_id"],
            "linked_after_delete": detached_briefing["workspace_knowledge_record_id"],
            "detached_references": detach_payload["detached_references"],
        },
    }
    (REPORT_DIR / "verification_report.json").write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
