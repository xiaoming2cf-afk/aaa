from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from pathlib import Path
from typing import Any

from .config import Settings
from .utils import slugify

try:
    from supabase import create_client
    from supabase.lib.client_options import ClientOptions, SyncClientOptions
except ImportError:  # pragma: no cover - optional dependency for local-only setups
    create_client = None
    ClientOptions = None
    SyncClientOptions = None


SUPABASE_PREFIX = "supabase://"
_REMOTE_OBJECT_KEY_MAX_BYTES = 1024
_REMOTE_OBJECT_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REMOTE_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class StoredAsset:
    reference: str
    filename: str
    metadata: dict[str, Any]


def is_remote_asset_reference(reference: str) -> bool:
    return reference.startswith(SUPABASE_PREFIX)


def local_asset_root(settings: Settings) -> Path:
    return (settings.storage_dir / "assets").resolve()


def resolve_local_asset_path(settings: Settings, reference: str) -> Path:
    file_path = Path(reference).resolve(strict=False)
    asset_root = local_asset_root(settings)
    if not file_path.is_relative_to(asset_root):
        raise FileNotFoundError("Asset file is missing from storage.")
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError("Asset file is missing from storage.")
    return file_path


def parse_asset_reference(reference: str) -> tuple[str, str]:
    if not is_remote_asset_reference(reference):
        raise ValueError("Asset reference is not a remote object reference.")
    bucket_and_key = reference.removeprefix(SUPABASE_PREFIX)
    bucket, _, object_key = bucket_and_key.partition("/")
    if not bucket or not object_key:
        raise ValueError("Malformed remote asset reference.")
    _validate_remote_path_parts(bucket, object_key)
    return bucket, object_key


def build_asset_object_key(user_id: str, workspace_id: str, asset_id: str, filename: str) -> str:
    safe_user_id = _validate_remote_object_segment(user_id, field_name="user_id")
    safe_workspace_id = _validate_remote_object_segment(workspace_id, field_name="workspace_id")
    safe_asset_id = _validate_remote_object_segment(asset_id, field_name="asset_id")
    path = Path(filename)
    safe_stem = slugify(path.stem, max_length=48)
    safe_filename = _validate_remote_filename(f"{safe_stem}{path.suffix}")
    return f"{safe_user_id}/{safe_workspace_id}/{safe_asset_id}/{safe_filename}"


def _validate_remote_object_segment(value: str, *, field_name: str) -> str:
    segment = str(value or "").strip()
    if not _REMOTE_OBJECT_SEGMENT.fullmatch(segment) or segment in {".", ".."}:
        raise ValueError(f"Unsafe remote asset {field_name}.")
    return segment


def _validate_remote_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if "/" in name or "\\" in name or _REMOTE_CONTROL_CHARS.search(name) or name in {"", ".", ".."}:
        raise ValueError("Unsafe remote asset filename.")
    return name


def _validate_remote_path_parts(bucket: str, object_key: str) -> None:
    _validate_remote_object_segment(bucket, field_name="bucket")
    if len(object_key.encode("utf-8")) > _REMOTE_OBJECT_KEY_MAX_BYTES:
        raise ValueError("Remote asset object key is too long.")
    if "\\" in object_key or _REMOTE_CONTROL_CHARS.search(object_key):
        raise ValueError("Malformed remote asset reference.")
    segments = object_key.split("/")
    if not segments or any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("Malformed remote asset reference.")


@lru_cache(maxsize=4)
def _get_supabase_client(supabase_url: str, service_role_key: str):
    if create_client is None or SyncClientOptions is None:
        raise RuntimeError("Supabase support is not installed. Run `pip install -e .` again.")
    return create_client(
        supabase_url,
        service_role_key,
        options=SyncClientOptions(auto_refresh_token=False, persist_session=False),
    )


def _store_locally(
    settings: Settings,
    *,
    user_id: str,
    workspace_id: str,
    asset_id: str,
    filename: str,
    content: bytes,
) -> StoredAsset:
    safe_name = slugify(Path(filename).stem, max_length=48)
    extension = Path(filename).suffix
    asset_root = local_asset_root(settings)
    asset_dir = (asset_root / user_id / workspace_id).resolve()
    if not asset_dir.is_relative_to(asset_root):
        raise ValueError("Resolved asset directory escaped the configured storage root.")
    asset_dir.mkdir(parents=True, exist_ok=True)
    file_path = (asset_dir / f"{asset_id}-{safe_name}{extension}").resolve()
    if not file_path.is_relative_to(asset_dir):
        raise ValueError("Resolved asset file path escaped the workspace asset directory.")
    file_path.write_bytes(content)
    return StoredAsset(
        reference=str(file_path),
        filename=Path(filename).name,
        metadata={"storage_backend": "local", "original_filename": Path(filename).name},
    )


def _store_in_supabase(
    settings: Settings,
    *,
    user_id: str,
    workspace_id: str,
    asset_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> StoredAsset:
    if not settings.has_supabase_storage_config:
        raise RuntimeError("Supabase asset storage is enabled, but SUPABASE_URL / SERVICE_ROLE / BUCKET are missing.")
    client = _get_supabase_client(settings.supabase_url, settings.supabase_service_role_key)
    bucket = settings.supabase_storage_bucket
    object_key = build_asset_object_key(user_id, workspace_id, asset_id, filename)
    client.storage.from_(bucket).upload(
        path=object_key,
        file=content,
        file_options={"content-type": content_type or "application/octet-stream", "upsert": "false"},
    )
    return StoredAsset(
        reference=f"{SUPABASE_PREFIX}{bucket}/{object_key}",
        filename=Path(filename).name,
        metadata={
            "storage_backend": "supabase",
            "original_filename": Path(filename).name,
            "bucket": bucket,
            "object_key": object_key,
        },
    )


def store_asset_content(
    settings: Settings,
    *,
    user_id: str,
    workspace_id: str,
    asset_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> StoredAsset:
    if settings.uses_supabase_asset_storage:
        return _store_in_supabase(
            settings,
            user_id=user_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
    return _store_locally(
        settings,
        user_id=user_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        filename=filename,
        content=content,
    )


def load_asset_bytes(settings: Settings, reference: str) -> bytes:
    if is_remote_asset_reference(reference):
        if not settings.has_supabase_storage_config:
            raise RuntimeError("Supabase asset storage is configured for this asset, but credentials are missing.")
        bucket, object_key = parse_asset_reference(reference)
        if bucket != settings.supabase_storage_bucket:
            raise FileNotFoundError("Asset file is missing from storage.")
        client = _get_supabase_client(settings.supabase_url, settings.supabase_service_role_key)
        return client.storage.from_(bucket).download(object_key)

    return resolve_local_asset_path(settings, reference).read_bytes()
