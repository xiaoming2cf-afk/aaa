from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_deploy_artifacts, verify_render_deploy, write_engineering_gate_artifact
from scripts.spa_dist_manifest import collect_spa_dist_manifest


COMMIT_SHA = "abc123def456"


class _Response:
    def __init__(self, *, status_code: int, content: bytes = b"", text: str = "", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = content or text.encode("utf-8")
        self.text = text or self.content.decode("utf-8", errors="replace")
        self.headers = headers or {}


class _FakeSession:
    def __init__(self, responses: dict[str, _Response]):
        self.responses = responses

    def get(self, url: str, **kwargs):  # noqa: ANN001
        del kwargs
        return self.responses[url]


def _write_valid_spa_dist(root: Path, *, js_text: str = 'import("./chunk-def456.js");\n') -> None:
    assets = root / "frontend-spa" / "dist" / "assets"
    assets.mkdir(parents=True)
    (root / "frontend-spa" / "dist" / "index.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<script type="module" crossorigin src="/app/assets/index-abc123.js"></script>',
                '<link rel="stylesheet" crossorigin href="/app/assets/index-abc123.css">',
            ]
        ),
        encoding="utf-8",
    )
    (assets / "index-abc123.js").write_text(js_text, encoding="utf-8")
    (assets / "index-abc123.css").write_text("body{color:#111;}\n", encoding="utf-8")
    (assets / "chunk-def456.js").write_text("export const chunk = true;\n", encoding="utf-8")


def _gate_payload(root: Path) -> dict[str, object]:
    manifest, failures = collect_spa_dist_manifest(root / "frontend-spa" / "dist", commit_sha=COMMIT_SHA)
    assert failures == []
    return {
        "artifact_schema": "engineering-gate.v1",
        "commit_sha": COMMIT_SHA,
        "passed": True,
        "checks": [{"key": "spa_dist_manifest_bound", "passed": True, "detail": "passed"}],
        "checked_at": "2026-01-01T00:00:00+00:00",
        "source": "test",
        "spa_dist": manifest,
    }


def test_spa_manifest_blocks_missing_referenced_asset_and_stale_assets(tmp_path: Path):
    dist = tmp_path / "frontend-spa" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<script type="module" src="/app/assets/index-missing.js"></script>\n',
        encoding="utf-8",
    )
    (assets / "index-old.js").write_text("console.log('old');\n", encoding="utf-8")

    manifest, failures = collect_spa_dist_manifest(dist, commit_sha=COMMIT_SHA)

    assert manifest is None
    failure_keys = {failure["key"] for failure in failures}
    assert "spa_dist_referenced_assets_exist" in failure_keys
    assert "spa_dist_no_stale_assets" in failure_keys


def test_engineering_gate_artifact_includes_spa_dist_manifest(monkeypatch, tmp_path: Path):
    _write_valid_spa_dist(tmp_path)
    monkeypatch.setattr(write_engineering_gate_artifact, "REPO_ROOT", tmp_path)

    payload = write_engineering_gate_artifact.build_artifact(commit_sha=COMMIT_SHA, source="test")

    assert payload["passed"] is True
    assert payload["spa_dist"]["commit_sha"] == COMMIT_SHA
    assert sorted(payload["spa_dist"]["entrypoints"]) == ["assets/index-abc123.css", "assets/index-abc123.js"]
    assert any(check["key"] == "spa_dist_manifest_bound" and check["passed"] for check in payload["checks"])


def test_spa_manifest_ignores_runtime_api_asset_paths(tmp_path: Path):
    _write_valid_spa_dist(
        tmp_path,
        js_text='import("./chunk-def456.js");fetch(`/api/data-lab/assets/${assetId}/profile`);fetch("/api/data-lab/assets/upload",{method:"POST"});\n',
    )

    manifest, failures = collect_spa_dist_manifest(tmp_path / "frontend-spa" / "dist", commit_sha=COMMIT_SHA)

    assert failures == []
    assert manifest is not None
    assert "assets/index-abc123.js" in manifest["entrypoints"]


def test_deploy_artifact_verifier_rejects_unbound_engineering_gate(tmp_path: Path):
    artifact = tmp_path / f"engineering-gate.{COMMIT_SHA}.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": COMMIT_SHA,
                "passed": True,
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    report = verify_deploy_artifacts.verify_artifacts(commit_sha=COMMIT_SHA, engineering_gate=artifact)

    assert report["passed"] is False
    assert any(failure["key"] == "spa_dist_manifest_present" for failure in report["failures"])


def test_deploy_artifact_verifier_detects_spa_dist_drift(tmp_path: Path):
    _write_valid_spa_dist(tmp_path)
    artifact = tmp_path / f"engineering-gate.{COMMIT_SHA}.json"
    artifact.write_text(json.dumps(_gate_payload(tmp_path)), encoding="utf-8")
    (tmp_path / "frontend-spa" / "dist" / "assets" / "stale-extra.js").write_text("old\n", encoding="utf-8")

    report = verify_deploy_artifacts.verify_artifacts(
        commit_sha=COMMIT_SHA,
        engineering_gate=artifact,
        spa_dist=tmp_path / "frontend-spa" / "dist",
    )

    assert report["passed"] is False
    assert any(failure["key"] == "spa_dist_no_stale_assets" for failure in report["failures"])


def test_render_deploy_spa_asset_verification_compares_remote_hashes(tmp_path: Path):
    _write_valid_spa_dist(tmp_path)
    manifest = _gate_payload(tmp_path)["spa_dist"]
    responses: dict[str, _Response] = {}
    base_url = "https://example.test"
    for entry in manifest["assets"]:
        path = entry["path"]
        content = (tmp_path / "frontend-spa" / "dist" / path).read_bytes()
        responses[f"{base_url}/app/{path}"] = _Response(status_code=200, content=content)
    responses[f"{base_url}/app"] = _Response(status_code=307, headers={"location": "/"})

    report = verify_render_deploy._verify_deployed_spa_assets(
        base_url=base_url,
        manifest=manifest,
        session=_FakeSession(responses),
    )

    assert report["passed"] is True

    broken_entry = manifest["assets"][0]
    responses[f"{base_url}/app/{broken_entry['path']}"] = _Response(
        status_code=200,
        content=b"stale bytes",
        text="stale bytes",
    )

    failed = verify_render_deploy._verify_deployed_spa_assets(
        base_url=base_url,
        manifest=manifest,
        session=_FakeSession(responses),
    )

    assert failed["passed"] is False
    assert any(
        check["key"] == "spa_asset_hash_matches_manifest"
        and check["path"] == f"/app/{broken_entry['path']}"
        and not check["passed"]
        for check in failed["checks"]
    )
