from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


SPA_DIST_MANIFEST_SCHEMA = "spa-dist.v1"
DEFAULT_BASE_PATH = "/app/"
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".map",
    ".svg",
    ".txt",
    ".webmanifest",
    ".xml",
}
MAX_TEXT_BYTES = 5_000_000
ASSET_REF_RE = re.compile(r"(?:/app/|/)?assets/[^\"'<>\s)]+")


def _posix(path: Path) -> str:
    return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_TEXT_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_asset_reference(reference: str) -> str:
    value = str(reference or "").strip().split("#", 1)[0].split("?", 1)[0]
    value = value.lstrip("./")
    if value.startswith("/"):
        value = value[1:]
    if value.startswith("app/"):
        value = value[4:]
    if not value.startswith("assets/"):
        return ""
    return value


def asset_references_from_text(text: str) -> set[str]:
    references: set[str] = set()
    for match in ASSET_REF_RE.finditer(text):
        normalized = normalize_asset_reference(match.group(0))
        if normalized:
            references.add(normalized)
    return references


def _asset_reference_tokens(relative_path: str, *, base_path: str) -> tuple[str, ...]:
    basename = Path(relative_path).name
    base = base_path.rstrip("/")
    return (
        relative_path,
        f"/{relative_path}",
        f"{base}/{relative_path}" if base else f"/{relative_path}",
        f"./{basename}",
        basename,
    )


def _file_entry(dist_dir: Path, relative_path: str) -> dict[str, Any]:
    path = dist_dir / relative_path
    stat = path.stat()
    return {
        "path": relative_path,
        "sha256": _sha256(path),
        "bytes": stat.st_size,
    }


def collect_spa_dist_manifest(
    dist_dir: Path,
    *,
    base_path: str = DEFAULT_BASE_PATH,
    commit_sha: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    root = dist_dir.expanduser().resolve()
    index_path = root / "index.html"
    failures: list[dict[str, Any]] = []
    if not index_path.exists():
        return None, [
            {
                "key": "spa_built_shell_present",
                "passed": False,
                "detail": f"{index_path} is missing. Run the frontend build before writing the engineering gate artifact.",
            }
        ]

    all_files = sorted(
        _posix(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    )
    asset_files = [relative for relative in all_files if relative.startswith("assets/")]
    if not asset_files:
        failures.append(
            {
                "key": "spa_dist_assets_present",
                "passed": False,
                "detail": f"{root} does not contain built files under assets/.",
            }
        )

    index_text = _read_text(index_path)
    if "/src/main.tsx" in index_text:
        failures.append(
            {
                "key": "spa_shell_uses_built_assets",
                "passed": False,
                "detail": f"{index_path} still references /src/main.tsx.",
            }
        )
    if f"{base_path.rstrip('/')}/assets/" not in index_text:
        failures.append(
            {
                "key": "spa_shell_uses_built_assets",
                "passed": False,
                "detail": f"{index_path} does not reference {base_path.rstrip('/')}/assets/ build outputs.",
            }
        )

    existing = set(all_files)
    reachable: set[str] = {"index.html"}
    direct_entrypoints = asset_references_from_text(index_text)
    missing_references: set[str] = {relative for relative in direct_entrypoints if relative not in existing}
    queue: list[str] = ["index.html"]

    while queue:
        current = queue.pop(0)
        path = root / current
        if not path.exists():
            continue
        text = _read_text(path)
        if not text:
            continue
        for referenced in asset_references_from_text(text):
            if referenced in existing:
                if referenced not in reachable:
                    reachable.add(referenced)
                    queue.append(referenced)
            else:
                missing_references.add(referenced)
        for asset in asset_files:
            if asset in reachable:
                continue
            if any(token and token in text for token in _asset_reference_tokens(asset, base_path=base_path)):
                reachable.add(asset)
                queue.append(asset)

    stale_assets = sorted(asset for asset in asset_files if asset not in reachable)
    if missing_references:
        failures.append(
            {
                "key": "spa_dist_referenced_assets_exist",
                "passed": False,
                "detail": "Built SPA shell or bundles reference missing asset files.",
                "missing_assets": sorted(missing_references),
            }
        )
    if stale_assets:
        failures.append(
            {
                "key": "spa_dist_no_stale_assets",
                "passed": False,
                "detail": "Built SPA dist contains asset files that are not reachable from index.html.",
                "stale_assets": stale_assets,
            }
        )

    if failures:
        return None, failures

    manifest = {
        "schema": SPA_DIST_MANIFEST_SCHEMA,
        "base_path": base_path,
        "commit_sha": commit_sha,
        "index": _file_entry(root, "index.html"),
        "entrypoints": sorted(direct_entrypoints),
        "assets": [_file_entry(root, relative) for relative in sorted(asset_files)],
        "files": [_file_entry(root, relative) for relative in all_files],
    }
    return manifest, []


def validate_spa_dist_manifest_payload(manifest: Any, *, commit_sha: str = "") -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not isinstance(manifest, dict):
        return [
            {
                "key": "spa_dist_manifest_present",
                "passed": False,
                "detail": "Engineering gate artifact must include a spa_dist manifest object.",
            }
        ]
    if manifest.get("schema") != SPA_DIST_MANIFEST_SCHEMA:
        failures.append(
            {
                "key": "spa_dist_manifest_schema",
                "passed": False,
                "detail": f"Expected {SPA_DIST_MANIFEST_SCHEMA}, found {manifest.get('schema')!r}.",
            }
        )
    if commit_sha and str(manifest.get("commit_sha") or "") != commit_sha:
        failures.append(
            {
                "key": "spa_dist_manifest_commit_match",
                "passed": False,
                "detail": f"SPA dist manifest commit {manifest.get('commit_sha') or '<missing>'} does not match expected {commit_sha}.",
            }
        )
    if not isinstance(manifest.get("index"), dict) or manifest["index"].get("path") != "index.html":
        failures.append(
            {
                "key": "spa_dist_manifest_index_bound",
                "passed": False,
                "detail": "SPA dist manifest must include index.html with a content hash.",
            }
        )
    entries = manifest.get("entrypoints")
    if not isinstance(entries, list) or not entries:
        failures.append(
            {
                "key": "spa_dist_manifest_entrypoints_bound",
                "passed": False,
                "detail": "SPA dist manifest must include the index.html asset entrypoints.",
            }
        )
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        failures.append(
            {
                "key": "spa_dist_manifest_assets_bound",
                "passed": False,
                "detail": "SPA dist manifest must include hashed asset file entries.",
            }
        )
    for collection_name in ("assets", "files"):
        collection = manifest.get(collection_name)
        if not isinstance(collection, list):
            continue
        for entry in collection:
            if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
                failures.append(
                    {
                        "key": "spa_dist_manifest_file_hashes_bound",
                        "passed": False,
                        "detail": f"SPA dist manifest {collection_name} entries must include path and sha256.",
                    }
                )
                break
    return failures


def compare_spa_dist_to_manifest(dist_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    expected_failures = validate_spa_dist_manifest_payload(manifest)
    if expected_failures:
        return expected_failures
    current, failures = collect_spa_dist_manifest(
        dist_dir,
        base_path=str(manifest.get("base_path") or DEFAULT_BASE_PATH),
        commit_sha=str(manifest.get("commit_sha") or ""),
    )
    if failures or current is None:
        return failures

    expected_files = {
        str(entry.get("path")): str(entry.get("sha256"))
        for entry in manifest.get("files", [])
        if isinstance(entry, dict)
    }
    current_files = {
        str(entry.get("path")): str(entry.get("sha256"))
        for entry in current.get("files", [])
        if isinstance(entry, dict)
    }
    missing = sorted(path for path in expected_files if path not in current_files)
    extra = sorted(path for path in current_files if path not in expected_files)
    mismatched = sorted(path for path, digest in expected_files.items() if current_files.get(path) not in {None, digest})
    failures = []
    if missing or extra or mismatched:
        failures.append(
            {
                "key": "spa_dist_manifest_matches_files",
                "passed": False,
                "detail": "SPA dist files do not match the manifest bound into the engineering gate artifact.",
                "missing_files": missing,
                "extra_files": extra,
                "mismatched_files": mismatched,
            }
        )
    if sorted(current.get("entrypoints", [])) != sorted(manifest.get("entrypoints", [])):
        failures.append(
            {
                "key": "spa_dist_manifest_matches_entrypoints",
                "passed": False,
                "detail": "SPA dist index.html entrypoints do not match the manifest bound into the engineering gate artifact.",
                "expected_entrypoints": sorted(manifest.get("entrypoints", [])),
                "actual_entrypoints": sorted(current.get("entrypoints", [])),
            }
        )
    return failures
