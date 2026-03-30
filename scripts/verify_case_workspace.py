from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

REPORT_DIR = REPO_ROOT / "蒙特卡洛" / "case_workspace"


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-case-workspace-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-case-workspace-encryption"
    os.environ["CRON_SECRET"] = "verify-case-workspace-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def expect_status(response, expected: int) -> None:
    assert response.status_code == expected, response.text


def build_case_dataset() -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for firm_idx, firm in enumerate(("firm_a", "firm_b", "firm_c", "firm_d"), start=1):
        treated = 1 if firm_idx <= 2 else 0
        for month_idx in range(1, 9):
            post = 1 if month_idx >= 5 else 0
            base_size = 8.5 + 0.18 * firm_idx
            leverage = 0.28 + 0.02 * firm_idx + 0.005 * month_idx
            outcome = 2.0 + 0.9 * base_size - 1.5 * leverage + 1.25 * treated * post + 0.08 * month_idx
            rows.append(
                {
                    "firm_id": firm,
                    "date": f"2024-{month_idx:02d}-01",
                    "treated": treated,
                    "post": post,
                    "size": round(base_size + 0.04 * month_idx, 4),
                    "leverage": round(leverage, 4),
                    "outcome_y": round(outcome, 4),
                }
            )
    return pd.DataFrame(rows)


def create_workspace(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/workspaces",
        json={"name": name, "description": "Verification workspace", "research_domain": "economics"},
        headers=auth_headers(token),
    )
    expect_status(response, 200)
    return response.json()["workspace"]["id"]


def upload_csv_asset(client: TestClient, token: str, workspace_id: str, filename: str, frame: pd.DataFrame) -> dict:
    payload = frame.to_csv(index=False).encode("utf-8")
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(payload), "text/csv")},
        data={"description": "Case workspace verification dataset"},
    )
    expect_status(response, 200)
    return response.json()["asset"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="erp-case-workspace-", ignore_cleanup_errors=True) as temp_dir:
        temp_root = Path(temp_dir)
        configure_test_environment(temp_root)

        from research_agent.webapp import create_app

        with TestClient(create_app()) as client:
            homepage = client.get("/")
            expect_status(homepage, 200)
            home_html = homepage.text
            assert 'id="active-case-select"' in home_html
            assert 'id="knowledge-case-list"' in home_html
            assert 'id="knowledge-case-preview"' in home_html

            data_lab_page = client.get("/data-lab")
            expect_status(data_lab_page, 200)
            lab_html = data_lab_page.text
            assert 'id="lab-case-select"' in lab_html
            assert 'id="lab-case-home-link"' in lab_html

            user_a_response = client.post(
                "/api/auth/register",
                json={"email": "case-a@example.com", "password": "StrongPass123!", "full_name": "Case User A"},
            )
            expect_status(user_a_response, 200)
            user_a_token = user_a_response.json()["session_token"]
            workspace_a = create_workspace(client, user_a_token, "Case Workspace A")

            user_b_response = client.post(
                "/api/auth/register",
                json={"email": "case-b@example.com", "password": "StrongPass123!", "full_name": "Case User B"},
            )
            expect_status(user_b_response, 200)
            user_b_token = user_b_response.json()["session_token"]
            workspace_b = create_workspace(client, user_b_token, "Case Workspace B")

            note_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge",
                headers=auth_headers(user_a_token),
                json={
                    "title": "Policy Transmission Research Note",
                    "content": "## Question\n\nHow do policy shocks transmit through firm outcomes?\n\n## Next step\n\nEstimate a DID baseline and compare treated vs. control firms.",
                    "tags": ["policy", "did", "workspace"],
                    "metadata": {"source_type": "manual_workspace", "note_template": "research_memo"},
                },
            )
            expect_status(note_response, 200)
            note_record = note_response.json()["record"]

            uploaded_asset = upload_csv_asset(client, user_a_token, workspace_a, "case_dataset.csv", build_case_dataset())

            profile_response = client.get(
                f"/api/workspaces/{workspace_a}/assets/{uploaded_asset['id']}/profile",
                headers=auth_headers(user_a_token),
            )
            expect_status(profile_response, 200)
            profile_payload = profile_response.json()
            assert profile_payload["asset"]["id"] == uploaded_asset["id"]

            prepare_response = client.post(
                f"/api/workspaces/{workspace_a}/analysis/prepare",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={
                    "asset_id": uploaded_asset["id"],
                    "workflow_group": "sample_preparation",
                    "include_columns": ["firm_id", "date", "treated", "post", "size", "leverage", "outcome_y"],
                    "required_columns": ["firm_id", "date", "treated", "post", "outcome_y"],
                    "numeric_columns": ["size", "leverage", "outcome_y"],
                    "binary_columns": ["treated", "post"],
                    "date_columns": ["date"],
                    "drop_duplicates": True,
                    "drop_missing_required": True,
                },
            )
            expect_status(prepare_response, 200)
            prepare_payload = prepare_response.json()
            prepared_asset = prepare_payload["asset"]
            prepared_detail_response = client.get(
                f"/api/data-lab/results/processing/{prepared_asset['id']}",
                headers=auth_headers(user_a_token),
            )
            expect_status(prepared_detail_response, 200)
            prepared_detail = prepared_detail_response.json()["result"]
            assert prepared_detail["workflow_type"] == "data_processing"
            assert prepared_detail["result_detail_path"] == f"/data-lab/results/processing/{prepared_asset['id']}"

            model_response = client.post(
                f"/api/workspaces/{workspace_a}/analysis/models",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={
                    "asset_id": prepared_asset["id"],
                    "model_type": "ols",
                    "dependent": "outcome_y",
                    "independents": ["treated", "post", "size", "leverage"],
                },
            )
            expect_status(model_response, 200)
            model_payload = model_response.json()
            model_record_id = model_payload["result_record_id"]
            model_detail_response = client.get(
                f"/api/data-lab/results/models/{model_record_id}",
                headers=auth_headers(user_a_token),
            )
            expect_status(model_detail_response, 200)
            model_detail = model_detail_response.json()["result"]
            assert model_detail["model_type"] == "ols"
            assert model_detail["result_record_id"] == model_record_id

            case_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge-cases",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={
                    "title": "Policy Shock Case File",
                    "description": "Collect the core note, prepared dataset, and baseline model output.",
                    "tags": ["policy", "did", "ols"],
                    "metadata": {"origin": "verify_case_workspace"},
                },
            )
            expect_status(case_response, 200)
            case_record = case_response.json()["case"]
            case_id = case_record["id"]

            add_note_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}/items",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={"item_type": "knowledge_record", "ref_id": note_record["id"]},
            )
            expect_status(add_note_response, 200)
            assert add_note_response.json()["created"] is True

            add_prepared_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}/items",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={"item_type": "data_asset", "ref_id": prepared_asset["id"]},
            )
            expect_status(add_prepared_response, 200)
            assert add_prepared_response.json()["created"] is True

            add_model_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}/items",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={"item_type": "knowledge_record", "ref_id": model_record_id},
            )
            expect_status(add_model_response, 200)
            assert add_model_response.json()["created"] is True

            duplicate_model_response = client.post(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}/items",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={"item_type": "knowledge_record", "ref_id": model_record_id},
            )
            expect_status(duplicate_model_response, 200)
            assert duplicate_model_response.json()["created"] is False

            case_list_response = client.get(
                f"/api/workspaces/{workspace_a}/knowledge-cases",
                headers=auth_headers(user_a_token),
            )
            expect_status(case_list_response, 200)
            case_list_items = case_list_response.json()["items"]
            assert len(case_list_items) == 1
            assert case_list_items[0]["item_count"] == 3
            assert sorted(case_list_items[0]["item_types"]) == ["data_asset", "knowledge_record"]

            case_detail_response = client.get(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}",
                headers=auth_headers(user_a_token),
            )
            expect_status(case_detail_response, 200)
            case_detail_payload = case_detail_response.json()
            case_items = case_detail_payload["items"]
            assert len(case_items) == 3

            note_case_item = next(item for item in case_items if item["ref_id"] == note_record["id"])
            prepared_case_item = next(item for item in case_items if item["ref_id"] == prepared_asset["id"])
            model_case_item = next(item for item in case_items if item["ref_id"] == model_record_id)

            assert note_case_item["item_type"] == "knowledge_record"
            assert note_case_item["detail_path"] == f"/data-lab/results/models/{model_record_id}" or note_case_item["detail_path"] == ""
            assert prepared_case_item["item_type"] == "data_asset"
            assert prepared_case_item["detail_path"] == f"/data-lab/results/processing/{prepared_asset['id']}"
            assert prepared_case_item["download_path"] == f"/api/assets/{prepared_asset['id']}/download"
            assert model_case_item["item_type"] == "knowledge_record"
            assert model_case_item["detail_path"] == f"/data-lab/results/models/{model_record_id}"

            download_prepared_response = client.get(
                prepared_case_item["download_path"],
                headers=auth_headers(user_a_token),
            )
            expect_status(download_prepared_response, 200)
            assert download_prepared_response.content.startswith(b"firm_id,date")

            update_case_response = client.patch(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}",
                headers={**auth_headers(user_a_token), "Content-Type": "application/json"},
                json={"title": "Policy Shock Case File Revised", "tags": ["policy", "baseline", "workspace"]},
            )
            expect_status(update_case_response, 200)
            assert update_case_response.json()["case"]["title"] == "Policy Shock Case File Revised"

            user_b_case_list = client.get(
                f"/api/workspaces/{workspace_b}/knowledge-cases",
                headers=auth_headers(user_b_token),
            )
            expect_status(user_b_case_list, 200)
            assert user_b_case_list.json()["items"] == []

            user_b_case_access = client.get(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}",
                headers=auth_headers(user_b_token),
            )
            expect_status(user_b_case_access, 404)

            user_b_add_foreign_item = client.post(
                f"/api/workspaces/{workspace_b}/knowledge-cases",
                headers={**auth_headers(user_b_token), "Content-Type": "application/json"},
                json={"title": "User B Case", "description": "Should not accept foreign refs."},
            )
            expect_status(user_b_add_foreign_item, 200)
            case_b_id = user_b_add_foreign_item.json()["case"]["id"]

            user_b_import_foreign_response = client.post(
                f"/api/workspaces/{workspace_b}/knowledge-cases/{case_b_id}/items",
                headers={**auth_headers(user_b_token), "Content-Type": "application/json"},
                json={"item_type": "data_asset", "ref_id": prepared_asset["id"]},
            )
            expect_status(user_b_import_foreign_response, 404)

            remove_prepared_response = client.delete(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}/items/{prepared_case_item['id']}",
                headers=auth_headers(user_a_token),
            )
            expect_status(remove_prepared_response, 200)

            case_after_remove_response = client.get(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}",
                headers=auth_headers(user_a_token),
            )
            expect_status(case_after_remove_response, 200)
            case_after_remove = case_after_remove_response.json()
            assert len(case_after_remove["items"]) == 2
            assert all(item["id"] != prepared_case_item["id"] for item in case_after_remove["items"])

            delete_case_response = client.delete(
                f"/api/workspaces/{workspace_a}/knowledge-cases/{case_id}",
                headers=auth_headers(user_a_token),
            )
            expect_status(delete_case_response, 200)
            assert delete_case_response.json()["status"] == "deleted"

            case_list_after_delete = client.get(
                f"/api/workspaces/{workspace_a}/knowledge-cases",
                headers=auth_headers(user_a_token),
            )
            expect_status(case_list_after_delete, 200)
            assert case_list_after_delete.json()["items"] == []

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "pages": {
            "homepage_has_case_workspace": True,
            "homepage_case_ids": ["active-case-select", "knowledge-case-list", "knowledge-case-preview"],
            "data_lab_case_ids": ["lab-case-select", "lab-case-home-link"],
        },
        "data_lab_flow": {
            "uploaded_asset_id": uploaded_asset["id"],
            "prepared_asset_id": prepared_asset["id"],
            "prepared_result_detail_path": prepared_detail["result_detail_path"],
            "model_record_id": model_record_id,
            "model_result_detail_path": model_detail["result_detail_path"],
        },
        "case_workspace": {
            "case_id": case_id,
            "updated_case_title": "Policy Shock Case File Revised",
            "linked_item_count_before_remove": 3,
            "linked_item_count_after_remove": 2,
            "duplicate_add_reused_existing_item": duplicate_model_response.json()["created"] is False,
        },
        "linked_items": {
            "note_ref_id": note_case_item["ref_id"],
            "prepared_asset_ref_id": prepared_case_item["ref_id"],
            "model_record_ref_id": model_case_item["ref_id"],
            "prepared_download_path": prepared_case_item["download_path"],
        },
        "isolation": {
            "user_b_case_count": len(user_b_case_list.json()["items"]),
            "user_b_cannot_open_user_a_case": user_b_case_access.status_code == 404,
            "user_b_cannot_add_user_a_asset": user_b_import_foreign_response.status_code == 404,
        },
    }
    (REPORT_DIR / "verification_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
