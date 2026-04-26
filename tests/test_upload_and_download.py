from __future__ import annotations

from pathlib import Path

from research_agent.entities import DataAsset
from research_agent.asset_storage import build_asset_object_key, load_asset_bytes, store_asset_content
from research_agent.config import Settings


def test_upload_validation_and_safe_download_headers(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    invalid = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "bad file"},
        files={"file": ("payload.csv", b"MZ-binary", "text/csv")},
    )
    assert invalid.status_code == 400

    valid = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "valid csv", "source_url": "https://example.com/data"},
        files={"file": ('报告 "sample".csv', b"col_a,col_b\n1,2\n", "text/csv")},
    )
    assert valid.status_code == 200, valid.text
    asset_id = valid.json()["asset"]["id"]

    download = client.get(f"/api/assets/{asset_id}/download")
    assert download.status_code == 200
    header = download.headers["Content-Disposition"]
    assert header.startswith("attachment;")
    assert "filename*=UTF-8''" in header
    assert "\n" not in header
    assert download.headers["X-Content-Type-Options"] == "nosniff"


def test_upload_rejects_html_disguised_as_text_formats(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    payloads = [
        ("bad.csv", b"<!doctype html><html><body>x</body></html>", "text/csv"),
        ("bad.txt", b"<script>alert(1)</script>", "text/plain"),
        ("bad.md", b"<html><body>fake markdown</body></html>", "text/markdown"),
        ("bad.svg", b"<html><body>fake svg</body></html>", "image/svg+xml"),
        ("bad.json", b"{not-json}", "application/json"),
    ]
    for name, content, content_type in payloads:
        response = client.post(
            f"/api/workspaces/{workspace_id}/assets/upload",
            headers={"X-CSRF-Token": csrf_token},
            data={"description": f"reject {name}"},
            files={"file": (name, content, content_type)},
        )
        assert response.status_code == 400, response.text


def test_local_asset_storage_rejects_resolved_path_escape(tmp_path: Path):
    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        storage_dir=tmp_path / "storage",
    )
    try:
        store_asset_content(
            settings,
            user_id="..",
            workspace_id="workspace",
            asset_id="asset-id",
            filename="sample.csv",
            content=b"col\n1\n",
            content_type="text/csv",
        )
    except ValueError:
        return
    raise AssertionError("Resolved storage path escape should be rejected")


def test_download_rejects_local_asset_path_outside_storage_root(client, auth_headers, db_session, tmp_path: Path):
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    user_id = me.json()["user"]["id"]
    rogue_file = tmp_path / "outside-storage.txt"
    rogue_file.write_text("top-secret", encoding="utf-8")

    asset = DataAsset(
        workspace_id=auth_headers["workspace_id"],
        owner_user_id=user_id,
        kind="note_text",
        title="outside-storage.txt",
        file_path=str(rogue_file.resolve()),
        content_type="text/plain",
        metadata_json={"original_filename": "outside-storage.txt"},
    )
    db_session.add(asset)
    db_session.commit()

    download = client.get(f"/api/assets/{asset.id}/download")
    assert download.status_code == 404


def test_remote_asset_download_requires_configured_bucket(tmp_path: Path):
    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        storage_dir=tmp_path / "storage",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-key",
        supabase_storage_bucket="research-assets",
    )

    try:
        load_asset_bytes(settings, "supabase://other-bucket/user/workspace/asset/file.csv")
    except FileNotFoundError:
        return
    raise AssertionError("Remote asset references outside the configured bucket should be rejected")


def test_remote_asset_object_keys_reject_traversal_segments():
    unsafe_values = ["..", "user/other", "user\\other", "user\nother"]

    for value in unsafe_values:
        try:
            build_asset_object_key(value, "workspace", "asset-id", "sample.csv")
        except ValueError:
            continue
        raise AssertionError(f"Unsafe remote asset object key segment should be rejected: {value!r}")
