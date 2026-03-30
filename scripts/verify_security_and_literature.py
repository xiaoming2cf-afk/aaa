from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-security-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-security-encryption"
    os.environ["CRON_SECRET"] = "verify-security-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_pdf_bytes(title: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), title)
    return document.tobytes(garbage=3, deflate=True)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_payload: dict | None = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self.content = content
        self.headers = headers or {}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._json_payload


def fake_requests_get(url: str, *, headers: dict | None = None, params: dict | None = None, timeout: int = 30):  # noqa: ARG001
    if "api.openalex.org/works" in url:
        return FakeResponse(
            json_payload={
                "results": [
                    {
                        "id": "https://openalex.org/W1234567890",
                        "display_name": "Monetary Policy Spillovers and Capital Flows",
                        "abstract_inverted_index": {"Monetary": [0], "policy": [1], "spillovers": [2]},
                        "publication_year": 2024,
                        "doi": "https://doi.org/10.1234/example",
                        "cited_by_count": 42,
                        "authorships": [
                            {"author": {"display_name": "Alice Example"}},
                            {"author": {"display_name": "Bob Example"}},
                        ],
                        "keywords": [
                            {"display_name": "Monetary policy"},
                            {"display_name": "Capital flows"},
                        ],
                        "best_oa_location": {
                            "landing_page_url": "https://example.org/paper/landing",
                            "pdf_url": "",
                            "source": {"display_name": "Example Journal"},
                        },
                        "primary_location": {
                            "landing_page_url": "https://example.org/paper/landing",
                            "pdf_url": "",
                            "source": {"display_name": "Example Journal"},
                        },
                        "open_access": {
                            "is_oa": True,
                            "oa_url": "",
                        },
                    }
                ]
            },
            url=url,
        )
    if url == "https://example.org/paper/direct.pdf":
        return FakeResponse(
            content=build_pdf_bytes("Monetary Policy Spillovers and Capital Flows"),
            headers={"Content-Type": "application/pdf"},
            url=url,
        )
    if url == "https://example.org/paper/landing":
        return FakeResponse(
            content=(
                b'<html><head><meta name="citation_pdf_url" content="/paper/files/working-paper.pdf"></head>'
                b'<body><a href="/paper/files/working-paper.pdf">Download PDF</a></body></html>'
            ),
            headers={"Content-Type": "text/html"},
            url=url,
        )
    if url == "https://example.org/paper/files/working-paper.pdf":
        return FakeResponse(
            content=build_pdf_bytes("Monetary Policy Spillovers and Capital Flows"),
            headers={"Content-Type": "application/pdf"},
            url=url,
        )
    raise AssertionError(f"Unexpected URL: {url}")


def expect_status(response, expected: int) -> None:
    assert response.status_code == expected, response.text


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_root = Path(temp_dir)
        configure_test_environment(temp_root)

        from research_agent.webapp import create_app

        with patch("research_agent.platform_research.requests.get", side_effect=fake_requests_get):
            with TestClient(create_app()) as client:
                user_a_response = client.post(
                    "/api/auth/register",
                    json={
                        "email": "alice@example.com",
                        "password": "SecurePass123",
                        "full_name": "Alice Researcher",
                    },
                )
                expect_status(user_a_response, 200)
                user_a_payload = user_a_response.json()
                user_a_token = user_a_payload["session_token"]
                workspace_a = user_a_payload["workspaces"][0]

                user_b_response = client.post(
                    "/api/auth/register",
                    json={
                        "email": "bob@example.com",
                        "password": "SecurePass123",
                        "full_name": "Bob Researcher",
                    },
                )
                expect_status(user_b_response, 200)
                user_b_payload = user_b_response.json()
                user_b_token = user_b_payload["session_token"]
                workspace_b = user_b_payload["workspaces"][0]

                me_a = client.get("/api/auth/me", headers=auth_headers(user_a_token))
                me_b = client.get("/api/auth/me", headers=auth_headers(user_b_token))
                expect_status(me_a, 200)
                expect_status(me_b, 200)
                assert me_a.json()["user"]["email"] == "alice@example.com"
                assert me_b.json()["user"]["email"] == "bob@example.com"
                assert me_a.json()["workspaces"][0]["id"] != me_b.json()["workspaces"][0]["id"]

                search_response = client.get(
                    "/api/openalex/search",
                    params={"q": "monetary policy spillovers", "max_results": 3, "open_access_only": True},
                )
                expect_status(search_response, 200)
                search_items = search_response.json()["items"]
                assert len(search_items) == 1
                assert search_items[0]["landing_page_url"] == "https://example.org/paper/landing"
                assert search_items[0]["pdf_url"] == ""

                import_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/import",
                    headers=auth_headers(user_a_token),
                    json={"works": search_items},
                )
                expect_status(import_response, 200)
                imported_items = import_response.json()["items"]
                assert len(imported_items) == 1
                entry_a = imported_items[0]

                user_a_literature = client.get(
                    f"/api/workspaces/{workspace_a['id']}/literature",
                    headers=auth_headers(user_a_token),
                )
                user_b_literature = client.get(
                    f"/api/workspaces/{workspace_b['id']}/literature",
                    headers=auth_headers(user_b_token),
                )
                expect_status(user_a_literature, 200)
                expect_status(user_b_literature, 200)
                assert len(user_a_literature.json()["items"]) == 1
                assert len(user_b_literature.json()["items"]) == 0

                forbidden_literature = client.get(
                    f"/api/workspaces/{workspace_a['id']}/literature",
                    headers=auth_headers(user_b_token),
                )
                expect_status(forbidden_literature, 404)

                import_pdf_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-pdf",
                    headers=auth_headers(user_a_token),
                )
                expect_status(import_pdf_response, 200)
                import_pdf_payload = import_pdf_response.json()
                assert import_pdf_payload["asset"]["kind"] == "document_pdf"
                assert import_pdf_payload["entry"]["workspace_pdf_asset_id"]
                asset_id = import_pdf_payload["asset"]["id"]
                assert import_pdf_payload["source_url"] == "https://example.org/paper/files/working-paper.pdf"

                knowledge_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-knowledge",
                    headers=auth_headers(user_a_token),
                )
                expect_status(knowledge_response, 200)
                knowledge_payload = knowledge_response.json()
                assert knowledge_payload["entry"]["workspace_knowledge_record_id"]

                repeat_knowledge_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-knowledge",
                    headers=auth_headers(user_a_token),
                )
                expect_status(repeat_knowledge_response, 200)
                assert repeat_knowledge_response.json()["imported"] is False

                repeat_import_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-pdf",
                    headers=auth_headers(user_a_token),
                )
                expect_status(repeat_import_response, 200)
                assert repeat_import_response.json()["imported"] is False

                forbidden_import_pdf = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-pdf",
                    headers=auth_headers(user_b_token),
                )
                expect_status(forbidden_import_pdf, 404)

                forbidden_import_knowledge = client.post(
                    f"/api/workspaces/{workspace_a['id']}/literature/{entry_a['id']}/import-knowledge",
                    headers=auth_headers(user_b_token),
                )
                expect_status(forbidden_import_knowledge, 404)

                assets_a = client.get(
                    f"/api/workspaces/{workspace_a['id']}/assets",
                    headers=auth_headers(user_a_token),
                )
                assets_b = client.get(
                    f"/api/workspaces/{workspace_b['id']}/assets",
                    headers=auth_headers(user_b_token),
                )
                expect_status(assets_a, 200)
                expect_status(assets_b, 200)
                assert any(item["id"] == asset_id for item in assets_a.json()["items"])
                assert all(item["id"] != asset_id for item in assets_b.json()["items"])

                forbidden_assets = client.get(
                    f"/api/workspaces/{workspace_a['id']}/assets",
                    headers=auth_headers(user_b_token),
                )
                expect_status(forbidden_assets, 404)

                download_a = client.get(
                    f"/api/assets/{asset_id}/download",
                    headers=auth_headers(user_a_token),
                )
                expect_status(download_a, 200)
                assert download_a.content.startswith(b"%PDF")

                download_b = client.get(
                    f"/api/assets/{asset_id}/download",
                    headers=auth_headers(user_b_token),
                )
                expect_status(download_b, 404)

                knowledge_a = client.get(
                    f"/api/workspaces/{workspace_a['id']}/knowledge",
                    headers=auth_headers(user_a_token),
                )
                knowledge_b = client.get(
                    f"/api/workspaces/{workspace_b['id']}/knowledge",
                    headers=auth_headers(user_b_token),
                )
                expect_status(knowledge_a, 200)
                expect_status(knowledge_b, 200)
                assert len(knowledge_a.json()["items"]) == 1
                assert len(knowledge_b.json()["items"]) == 0

                large_note_content = "capacity-check-" * 30000
                large_note_response = client.post(
                    f"/api/workspaces/{workspace_a['id']}/knowledge",
                    headers=auth_headers(user_a_token),
                    json={
                        "title": "Knowledge Capacity Check",
                        "content": large_note_content,
                        "tags": ["capacity", "stress"],
                        "metadata": {"source": "verification"},
                    },
                )
                expect_status(large_note_response, 200)

                knowledge_after_capacity = client.get(
                    f"/api/workspaces/{workspace_a['id']}/knowledge",
                    headers=auth_headers(user_a_token),
                )
                expect_status(knowledge_after_capacity, 200)
                capacity_record = next(
                    item for item in knowledge_after_capacity.json()["items"] if item["title"] == "Knowledge Capacity Check"
                )
                assert len(capacity_record["content"]) == len(large_note_content)

                refreshed_literature = client.get(
                    f"/api/workspaces/{workspace_a['id']}/literature",
                    headers=auth_headers(user_a_token),
                )
                expect_status(refreshed_literature, 200)
                refreshed_entry = refreshed_literature.json()["items"][0]
                assert refreshed_entry["workspace_pdf_asset_id"] == asset_id
                assert refreshed_entry["workspace_pdf_download_url"].endswith(f"/api/assets/{asset_id}/download")
                assert refreshed_entry["workspace_knowledge_record_id"] == knowledge_payload["record"]["id"]
                assert "Monetary Policy Spillovers and Capital Flows" in refreshed_entry["citation_text"]

                report = {
                    "security": {
                        "user_a_email": me_a.json()["user"]["email"],
                        "user_b_email": me_b.json()["user"]["email"],
                        "workspace_ids_are_distinct": me_a.json()["workspaces"][0]["id"] != me_b.json()["workspaces"][0]["id"],
                        "user_b_cannot_open_user_a_workspace": forbidden_literature.status_code == 404,
                        "user_b_cannot_import_user_a_literature_pdf": forbidden_import_pdf.status_code == 404,
                        "user_b_cannot_import_user_a_literature_note": forbidden_import_knowledge.status_code == 404,
                        "user_b_cannot_download_user_a_asset": download_b.status_code == 404,
                    },
                    "paper_library": {
                        "openalex_search_result_count": len(search_items),
                        "imported_literature_count": len(imported_items),
                        "private_pdf_asset_id": asset_id,
                        "private_pdf_filename": import_pdf_payload["asset"]["title"],
                        "private_pdf_download_url": import_pdf_payload["download_url"],
                        "repeat_import_reused_existing_asset": repeat_import_response.json()["imported"] is False,
                        "knowledge_record_id": knowledge_payload["record"]["id"],
                        "knowledge_record_title": knowledge_payload["record"]["title"],
                        "repeat_knowledge_reused_existing_record": repeat_knowledge_response.json()["imported"] is False,
                        "citation_text": refreshed_entry["citation_text"],
                        "knowledge_capacity_chars_written": len(large_note_content),
                        "knowledge_capacity_chars_read_back": len(capacity_record["content"]),
                    },
                    "samples": {
                        "openalex_result": search_items[0],
                        "literature_entry": refreshed_entry,
                        "knowledge_record": knowledge_a.json()["items"][0],
                    },
                }
                report_dir = REPO_ROOT / "蒙特卡洛" / "security_literature"
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / "verification_report.json").write_text(
                    json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
