from __future__ import annotations

import fitz
from fastapi.testclient import TestClient


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "upload policy test")
    return document.tobytes()


def test_svg_upload_is_rejected_while_core_formats_remain_allowed(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    rejected = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "svg attack"},
        files={"file": ("malicious.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml")},
    )
    assert rejected.status_code == 400
    assert "svg" in rejected.text.lower()

    rejected_text_plain = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "svg attack via text/plain"},
        files={"file": ("malicious.svg", b"<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>", "text/plain")},
    )
    assert rejected_text_plain.status_code == 400
    assert "svg" in rejected_text_plain.text.lower()

    allowed_payloads = [
        ("dataset.csv", b"a,b\n1,2\n", "text/csv", "dataset_csv"),
        ("note.txt", b"plain note\n", "text/plain", "note_text"),
        ("note.md", b"# note\n", "text/markdown", "note_markdown"),
        ("paper.pdf", _pdf_bytes(), "application/pdf", "document_pdf"),
        ("chart.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png", "chart_png"),
        ("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg", "image_jpeg"),
    ]
    for filename, content, content_type, expected_kind in allowed_payloads:
        response = client.post(
            f"/api/workspaces/{workspace_id}/assets/upload",
            headers={"X-CSRF-Token": csrf_token},
            data={"description": f"allowed {filename}"},
            files={"file": (filename, content, content_type)},
        )
        assert response.status_code == 200, response.text
        assert response.json()["asset"]["kind"] == expected_kind


def test_upload_rejects_extension_content_type_and_magic_mismatches(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    mismatches = [
        ("csv with image mime", "data.csv", b"a,b\n1,2\n", "image/png"),
        ("png with csv bytes", "chart.png", b"a,b\n1,2\n", "image/png"),
        ("jpeg with text bytes", "photo.jpg", b"not really a jpeg", "image/jpeg"),
        ("json with invalid body", "data.json", b"{not-json}", "application/json"),
        ("html disguised as csv", "data.csv", b"<!doctype html><script>alert(1)</script>", "text/csv"),
        ("html disguised as txt", "note.txt", b"<html><body>owned</body></html>", "text/plain"),
    ]

    for label, filename, content, content_type in mismatches:
        response = client.post(
            f"/api/workspaces/{workspace_id}/assets/upload",
            headers={"X-CSRF-Token": csrf_token},
            data={"description": label},
            files={"file": (filename, content, content_type)},
        )

        assert response.status_code == 400, f"{label}: {response.text}"


def test_download_filename_header_is_sanitized_and_owner_scoped(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    upload = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "download name"},
        files={"file": ("..\\unsafe\r\nname.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    asset_id = upload.json()["asset"]["id"]

    download = client.get(f"/api/assets/{asset_id}/download")
    assert download.status_code == 200
    disposition = download.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "\\" not in disposition
    assert "/" not in disposition
    assert download.headers["x-content-type-options"] == "nosniff"

    other_client = TestClient(client.app)
    other = other_client.post(
        "/api/auth/register",
        headers={"Origin": "http://testserver"},
        json={"email": "download-other@example.com", "password": "StrongPass!2026", "full_name": "Other User"},
    )
    assert other.status_code == 200, other.text
    forbidden = other_client.get(f"/api/assets/{asset_id}/download")
    assert forbidden.status_code == 404
