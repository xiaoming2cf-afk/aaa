from __future__ import annotations

import fitz


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
