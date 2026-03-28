from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import Settings
from .utils import slugify

try:
    from supabase import create_client
    from supabase.lib.client_options import ClientOptions
except ImportError:  # pragma: no cover - optional dependency for local-only setups
    create_client = None
    ClientOptions = None


SUPABASE_PREFIX = "supabase://"


@dataclass
class StoredAsset:
    reference: str
    filename: str
    metadata: dict[str, Any]


def is_remote_asset_reference(reference: str) -> bool:
    return reference.startswith(SUPABASE_PREFIX)


def parse_asset_reference(reference: str) -> tuple[str, str]:
    if not is_remote_asset_reference(reference):
        raise ValueError("Asset reference is not a remote object reference.")
    bucket_and_key = reference.removeprefix(SUPABASE_PREFIX)
    bucket, _, object_key = bucket_and_key.partition("/")
    if not bucket or not object_key:
        raise ValueError("Malformed remote asset reference.")
    return bucket, object_key


def build_asset_object_key(user_id: str, workspace_id: str, asset_id: str, filename: str) -> str:
    path = Path(filename)
    safe_stem = slugify(path.stem, max_length=48)
    return f"{user_id}/{workspace_id}/{asset_id}/{safe_stem}{path.suffix}"


@lru_cache(maxsize=4)
def _get_supabase_client(supabase_url: str, service_role_key: str):
    if create_client is None or ClientOptions is None:
        raise RuntimeError("Supabase support is not installed. Run `pip install -e .` again.")
    return create_client(
        supabase_url,
        service_role_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
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
    asset_dir = settings.storage_dir / "assets" / user_id / workspace_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    file_path = asset_dir / f"{asset_id}-{safe_name}{extension}"
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
        client = _get_supabase_client(settings.supabase_url, settings.supabase_service_role_key)
        return client.storage.from_(bucket).download(object_key)

    file_path = Path(reference)
    if not file_path.exists():
        raise FileNotFoundError("Asset file is missing from storage.")
    return file_path.read_bytes()
