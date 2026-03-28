from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .asset_storage import load_asset_bytes, store_asset_content
from .config import Settings
from .entities import DataAsset, IntegrationCredential, KnowledgeRecord, User, UserSession, Workspace
from .provider_gateway import ProviderGateway
from .security import (
    build_session_expiry,
    decrypt_secret,
    encrypt_secret,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from .utils import slugify, truncate_text


DATASET_KINDS = {"dataset_csv", "dataset_excel", "dataset_json"}


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_preview_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _normalize_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in {"", "nan", "none", "nat", "null"}:
            return pd.NA
        return cleaned
    return value


def _unique_clean_columns(columns: list[Any]) -> tuple[list[str], dict[str, str]]:
    seen: dict[str, int] = {}
    cleaned_columns: list[str] = []
    source_map: dict[str, str] = {}
    for raw_column in columns:
        raw_text = str(raw_column).strip()
        base = slugify(raw_text or "column", max_length=48).replace("-", "_").strip("_") or "column"
        count = seen.get(base, 0)
        seen[base] = count + 1
        candidate = base if count == 0 else f"{base}_{count + 1}"
        cleaned_columns.append(candidate)
        source_map[candidate] = raw_text or candidate
    return cleaned_columns, source_map


def normalize_dataset_frame(frame: pd.DataFrame, *, drop_duplicates: bool = True) -> tuple[pd.DataFrame, dict[str, Any]]:
    prepared = frame.copy()
    cleaned_columns, source_map = _unique_clean_columns(list(prepared.columns))
    prepared.columns = cleaned_columns
    duplicate_rows = int(prepared.duplicated().sum())
    if drop_duplicates:
        prepared = prepared.drop_duplicates().copy()

    for column in prepared.columns:
        prepared[column] = prepared[column].map(_normalize_scalar)

    summary = {
        "source_columns": source_map,
        "duplicate_rows_detected": duplicate_rows,
        "rows_after_standardization": int(len(prepared)),
        "columns_after_standardization": list(prepared.columns),
    }
    return prepared, summary


def infer_column_role(series: pd.Series) -> str:
    if is_datetime64_any_dtype(series):
        return "date"
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    if is_numeric_dtype(non_null):
        unique_count = int(non_null.nunique(dropna=True))
        if unique_count <= 2:
            return "binary"
        return "numeric"

    numeric_candidate = pd.to_numeric(non_null, errors="coerce")
    numeric_share = float(numeric_candidate.notna().mean()) if len(non_null) else 0.0
    if numeric_share >= 0.9:
        unique_count = int(numeric_candidate.dropna().nunique())
        if unique_count <= 2:
            return "binary"
        return "numeric"

    text_values = non_null.astype(str).str.strip()
    lowered = text_values.str.lower()
    binary_tokens = {"0", "1", "true", "false", "yes", "no", "y", "n", "treated", "control", "pre", "post"}
    if text_values.nunique() <= 2 or set(lowered.unique()).issubset(binary_tokens):
        return "binary"

    date_candidate = pd.to_datetime(text_values, errors="coerce")
    date_share = float(date_candidate.notna().mean()) if len(text_values) else 0.0
    if date_share >= 0.8:
        return "date"

    unique_count = int(text_values.nunique())
    if unique_count <= min(20, max(3, len(text_values) // 2)):
        return "categorical"
    return "text"


def _column_profile(frame: pd.DataFrame, source_map: dict[str, str], column: str) -> dict[str, Any]:
    series = frame[column]
    role = infer_column_role(series)
    non_null = series.dropna()
    profile = {
        "name": column,
        "source_name": source_map.get(column, column),
        "role": role,
        "dtype": str(series.dtype),
        "missing_count": int(series.isna().sum()),
        "non_null_count": int(non_null.shape[0]),
        "unique_count": int(non_null.nunique(dropna=True)),
        "sample_values": [_serialize_preview_value(value) for value in non_null.head(4).tolist()],
    }

    numeric_series = pd.to_numeric(series, errors="coerce")
    if role in {"numeric", "binary"} and numeric_series.notna().any():
        clean_numeric = numeric_series.dropna()
        profile.update(
            {
                "mean": _safe_float(clean_numeric.mean()),
                "std": _safe_float(clean_numeric.std()),
                "min": _safe_float(clean_numeric.min()),
                "max": _safe_float(clean_numeric.max()),
            }
        )
    elif role == "date":
        date_series = pd.to_datetime(series, errors="coerce").dropna()
        if not date_series.empty:
            profile.update(
                {
                    "min": date_series.min().isoformat(),
                    "max": date_series.max().isoformat(),
                }
            )
    return profile


def _frame_preview_rows(frame: pd.DataFrame, *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {column: _serialize_preview_value(value) for column, value in row.items()}
        for row in frame.head(limit).to_dict(orient="records")
    ]


def validate_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        raise ValueError("A valid email address is required.")
    return email


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at.isoformat(),
    }


def serialize_workspace(workspace: Workspace) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "research_domain": workspace.research_domain,
        "created_at": workspace.created_at.isoformat(),
    }


def serialize_integration(integration: IntegrationCredential) -> dict[str, Any]:
    return {
        "id": integration.id,
        "label": integration.label,
        "category": integration.category,
        "kind": integration.kind,
        "base_url": integration.base_url,
        "model": integration.model,
        "is_default": integration.is_default,
        "config": integration.config_json,
        "created_at": integration.created_at.isoformat(),
    }


def serialize_knowledge_record(record: KnowledgeRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "content": record.content,
        "tags": record.tags_json,
        "metadata": record.metadata_json,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def serialize_asset(asset: DataAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "kind": asset.kind,
        "title": asset.title,
        "description": asset.description,
        "content_type": asset.content_type,
        "source_url": asset.source_url,
        "metadata": asset.metadata_json,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }


def register_user(db: Session, *, email: str, password: str, full_name: str) -> User:
    normalized_email = validate_email(email)
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise ValueError("This email is already registered.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    user = User(
        email=normalized_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    db.add(
        Workspace(
            owner_user_id=user.id,
            name="Economic Research Workspace",
            slug="economic-research-workspace",
            description="Primary private workspace for economics research operations.",
            research_domain="economics",
        )
    )
    db.flush()
    return user


def login_user(db: Session, settings: Settings, *, email: str, password: str) -> tuple[User, str]:
    normalized_email = validate_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password.")
    token = generate_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=build_session_expiry(settings),
        )
    )
    db.flush()
    return user, token


def get_current_user(db: Session, token: str) -> User:
    session_row = db.scalar(
        select(UserSession).where(
            and_(
                UserSession.token_hash == hash_token(token),
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
    )
    if not session_row:
        raise PermissionError("Invalid or expired session token.")
    session_row.last_seen_at = datetime.now(timezone.utc)
    user = db.get(User, session_row.user_id)
    if not user or not user.is_active:
        raise PermissionError("The account is inactive.")
    return user


def create_workspace(
    db: Session,
    *,
    user: User,
    name: str,
    description: str = "",
    research_domain: str = "economics",
) -> Workspace:
    workspace = Workspace(
        owner_user_id=user.id,
        name=name.strip(),
        slug=slugify(name),
        description=description.strip(),
        research_domain=research_domain.strip() or "economics",
    )
    db.add(workspace)
    db.flush()
    return workspace


def list_workspaces(db: Session, *, user: User) -> list[Workspace]:
    return list(
        db.scalars(
            select(Workspace)
            .where(Workspace.owner_user_id == user.id)
            .order_by(Workspace.created_at.desc())
        )
    )


def get_workspace_for_user(db: Session, *, user: User, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    return workspace


def create_integration(
    db: Session,
    settings: Settings,
    *,
    user: User,
    label: str,
    category: str,
    kind: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    is_default: bool = False,
    config: dict[str, Any] | None = None,
) -> IntegrationCredential:
    if not api_key.strip():
        raise ValueError("API key is required.")
    if is_default:
        for current in db.scalars(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == category.strip(),
                    IntegrationCredential.is_default.is_(True),
                )
            )
        ):
            current.is_default = False
    integration = IntegrationCredential(
        owner_user_id=user.id,
        label=label.strip(),
        category=category.strip(),
        kind=kind.strip(),
        api_key_encrypted=encrypt_secret(settings, api_key.strip()),
        base_url=base_url.strip(),
        model=model.strip(),
        is_default=is_default,
        config_json=config or {},
    )
    db.add(integration)
    db.flush()
    return integration


def list_integrations(db: Session, *, user: User) -> list[IntegrationCredential]:
    return list(
        db.scalars(
            select(IntegrationCredential)
            .where(IntegrationCredential.owner_user_id == user.id)
            .order_by(IntegrationCredential.category.asc(), IntegrationCredential.created_at.desc())
        )
    )


def resolve_integration(
    db: Session,
    *,
    user: User,
    integration_id: str | None = None,
    category: str = "llm",
) -> IntegrationCredential:
    if integration_id:
        integration = db.get(IntegrationCredential, integration_id)
        if not integration or integration.owner_user_id != user.id:
            raise FileNotFoundError("Integration not found.")
        return integration
    integration = db.scalar(
        select(IntegrationCredential).where(
            and_(
                IntegrationCredential.owner_user_id == user.id,
                IntegrationCredential.category == category,
                IntegrationCredential.is_default.is_(True),
            )
        )
    )
    if not integration:
        raise FileNotFoundError(f"No default {category} integration is configured.")
    return integration


def test_integration(db: Session, settings: Settings, *, user: User, integration_id: str) -> dict[str, Any]:
    integration = db.get(IntegrationCredential, integration_id)
    if not integration or integration.owner_user_id != user.id:
        raise FileNotFoundError("Integration not found.")
    if integration.category == "llm":
        return ProviderGateway(settings).test_integration(integration)
    if integration.kind == "fred":
        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "FEDFUNDS",
                "api_key": decrypt_secret(settings, integration.api_key_encrypted),
                "file_type": "json",
                "limit": 1,
            },
            timeout=20,
        )
        response.raise_for_status()
        return {"status": "ok", "preview": "FRED API key is valid."}
    return {"status": "ok", "preview": "Integration stored successfully."}


def delete_integration(db: Session, *, user: User, integration_id: str) -> None:
    integration = db.get(IntegrationCredential, integration_id)
    if not integration or integration.owner_user_id != user.id:
        raise FileNotFoundError("Integration not found.")
    db.delete(integration)


def create_knowledge_record(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    title: str,
    content: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeRecord:
    record = KnowledgeRecord(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title=title.strip(),
        content=content.strip(),
        tags_json=[tag.strip() for tag in (tags or []) if tag.strip()],
        metadata_json=metadata or {},
    )
    db.add(record)
    db.flush()
    return record


def list_knowledge_records(db: Session, *, user: User, workspace: Workspace) -> list[KnowledgeRecord]:
    return list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc())
        )
    )


def search_knowledge_records(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    query: str,
) -> list[KnowledgeRecord]:
    search_value = f"%{query.strip()}%"
    return list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                    or_(
                        KnowledgeRecord.title.ilike(search_value),
                        KnowledgeRecord.content.ilike(search_value),
                    ),
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc())
        )
    )


def classify_asset_kind(filename: str, content_type: str) -> str:
    lowered_name = filename.lower()
    lowered_type = content_type.lower()
    if lowered_name.endswith(".csv") or "csv" in lowered_type:
        return "dataset_csv"
    if lowered_name.endswith(".xlsx") or lowered_name.endswith(".xls") or "excel" in lowered_type:
        return "dataset_excel"
    if lowered_name.endswith(".json") or "json" in lowered_type:
        return "dataset_json"
    if lowered_name.endswith(".pdf") or "pdf" in lowered_type:
        return "document_pdf"
    if lowered_name.endswith(".md"):
        return "note_markdown"
    if lowered_name.endswith(".txt") or lowered_type.startswith("text/"):
        return "note_text"
    if lowered_name.endswith(".png") or "image/png" in lowered_type:
        return "chart_png"
    if lowered_name.endswith(".jpg") or lowered_name.endswith(".jpeg") or "image/jpeg" in lowered_type:
        return "image_jpeg"
    if lowered_name.endswith(".svg") or "image/svg" in lowered_type:
        return "image_svg"
    return "binary_file"


def extract_text_from_bytes(content: bytes, *, filename: str, content_type: str) -> str:
    kind = classify_asset_kind(filename, content_type)
    if kind == "document_pdf":
        document = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in document[: min(8, len(document))])
        return truncate_text(text, 20000)
    if kind in {"dataset_csv", "dataset_json", "note_markdown", "note_text"}:
        return truncate_text(content.decode("utf-8", errors="ignore"), 20000)
    return ""


def save_upload_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    filename: str,
    content: bytes,
    content_type: str,
    description: str = "",
    source_url: str = "",
) -> DataAsset:
    asset = DataAsset(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        kind=classify_asset_kind(filename, content_type),
        title=Path(filename).name,
        description=description.strip(),
        content_type=content_type.strip(),
        source_url=source_url.strip(),
        extracted_text=extract_text_from_bytes(content, filename=filename, content_type=content_type),
        metadata_json={"size_bytes": len(content), "original_filename": Path(filename).name},
    )
    db.add(asset)
    db.flush()

    stored = store_asset_content(
        settings,
        user_id=user.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        filename=filename,
        content=content,
        content_type=content_type,
    )
    asset.file_path = stored.reference
    asset.metadata_json = {
        **asset.metadata_json,
        **stored.metadata,
    }
    db.flush()
    return asset


def list_assets(db: Session, *, user: User, workspace: Workspace) -> list[DataAsset]:
    return list(
        db.scalars(
            select(DataAsset)
            .where(
                and_(
                    DataAsset.owner_user_id == user.id,
                    DataAsset.workspace_id == workspace.id,
                )
            )
            .order_by(DataAsset.updated_at.desc())
        )
    )


def search_assets(db: Session, *, user: User, workspace: Workspace, query: str) -> list[DataAsset]:
    search_value = f"%{query.strip()}%"
    return list(
        db.scalars(
            select(DataAsset)
            .where(
                and_(
                    DataAsset.owner_user_id == user.id,
                    DataAsset.workspace_id == workspace.id,
                    or_(
                        DataAsset.title.ilike(search_value),
                        DataAsset.description.ilike(search_value),
                        DataAsset.extracted_text.ilike(search_value),
                    ),
                )
            )
            .order_by(DataAsset.updated_at.desc())
        )
    )


def load_dataset_frame(settings: Settings, asset: DataAsset) -> pd.DataFrame:
    raw_bytes = load_asset_bytes(settings, asset.file_path)
    if asset.kind == "dataset_csv":
        return pd.read_csv(BytesIO(raw_bytes))
    if asset.kind == "dataset_excel":
        return pd.read_excel(BytesIO(raw_bytes))
    if asset.kind == "dataset_json":
        raw = json.loads(raw_bytes.decode("utf-8"))
        return pd.DataFrame(raw)
    raise ValueError("This asset is not a structured dataset.")


def _analysis_asset_or_raise(db: Session, *, user: User, workspace: Workspace, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")
    if asset.kind not in DATASET_KINDS:
        raise ValueError("This asset is not a structured dataset.")
    return asset


def _load_analysis_frame(
    settings: Settings,
    asset: DataAsset,
    *,
    drop_duplicates: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw_frame = load_dataset_frame(settings, asset)
    return normalize_dataset_frame(raw_frame, drop_duplicates=drop_duplicates)


def _coerce_binary_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum():
        return numeric.apply(lambda value: np.nan if pd.isna(value) else (1.0 if float(value) > 0 else 0.0))

    mapping = {
        "true": 1.0,
        "yes": 1.0,
        "y": 1.0,
        "1": 1.0,
        "treated": 1.0,
        "post": 1.0,
        "false": 0.0,
        "no": 0.0,
        "n": 0.0,
        "0": 0.0,
        "control": 0.0,
        "pre": 0.0,
    }
    return series.astype(str).str.strip().str.lower().map(mapping)


def _coerce_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _prepare_selected_sample(
    frame: pd.DataFrame,
    *,
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    drop_duplicates: bool = True,
    drop_missing_required: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sample = frame.copy()
    duplicate_count = int(sample.duplicated().sum()) if drop_duplicates else 0
    if drop_duplicates:
        sample = sample.drop_duplicates().copy()

    include_columns = [column for column in (include_columns or []) if column]
    required_columns = [column for column in (required_columns or []) if column]
    numeric_columns = [column for column in (numeric_columns or []) if column]
    binary_columns = [column for column in (binary_columns or []) if column]
    date_columns = [column for column in (date_columns or []) if column]

    requested_columns = {*(include_columns or []), *required_columns, *numeric_columns, *binary_columns, *date_columns}
    missing_columns = [column for column in requested_columns if column not in sample.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    if include_columns:
        sample = sample[include_columns].copy()

    for column in numeric_columns:
        if column in sample.columns:
            sample[column] = pd.to_numeric(sample[column], errors="coerce")
    for column in binary_columns:
        if column in sample.columns:
            sample[column] = _coerce_binary_series(sample[column])
    for column in date_columns:
        if column in sample.columns:
            sample[column] = _coerce_date_series(sample[column])

    rows_before_missing_drop = int(len(sample))
    if drop_missing_required and required_columns:
        sample = sample.dropna(subset=required_columns).copy()
    rows_after_missing_drop = int(len(sample))

    csv_ready = sample.copy()
    for column in csv_ready.columns:
        if is_datetime64_any_dtype(csv_ready[column]):
            csv_ready[column] = csv_ready[column].dt.strftime("%Y-%m-%dT%H:%M:%S")

    summary = {
        "rows_initial": int(len(frame)),
        "rows_after_prepare": int(len(sample)),
        "rows_removed_for_missing_required": int(rows_before_missing_drop - rows_after_missing_drop),
        "duplicate_rows_removed": duplicate_count,
        "columns": list(sample.columns),
        "required_columns": required_columns,
        "numeric_columns": numeric_columns,
        "binary_columns": binary_columns,
        "date_columns": date_columns,
        "missing_by_column": {column: int(value) for column, value in sample.isna().sum().to_dict().items()},
    }
    return csv_ready, summary


def profile_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, meta = _load_analysis_frame(settings, asset, drop_duplicates=False)
    column_profiles = [_column_profile(frame, meta["source_columns"], column) for column in frame.columns]
    role_map: dict[str, list[str]] = {
        "numeric": [],
        "binary": [],
        "date": [],
        "categorical": [],
        "text": [],
        "empty": [],
    }
    for item in column_profiles:
        role_map.setdefault(item["role"], []).append(item["name"])

    suggested_models = ["ols"]
    if role_map["numeric"] and len(role_map["binary"]) >= 2:
        suggested_models.append("did")
    if len(role_map["numeric"]) >= 4:
        suggested_models.append("gravity")

    return {
        "asset": serialize_asset(asset),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows_detected": int(meta["duplicate_rows_detected"]),
        "column_profiles": column_profiles,
        "column_roles": role_map,
        "preview_rows": _frame_preview_rows(frame),
        "suggested_models": suggested_models,
        "source_columns": meta["source_columns"],
    }


def prepare_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    drop_duplicates: bool = True,
    drop_missing_required: bool = True,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    prepared_frame, summary = _prepare_selected_sample(
        frame,
        include_columns=include_columns,
        required_columns=required_columns,
        numeric_columns=numeric_columns,
        binary_columns=binary_columns,
        date_columns=date_columns,
        drop_duplicates=drop_duplicates,
        drop_missing_required=drop_missing_required,
    )
    csv_bytes = prepared_frame.to_csv(index=False).encode("utf-8")
    prepared_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-prepared.csv",
        content=csv_bytes,
        content_type="text/csv",
        description=f"Prepared analysis sample derived from {asset.title}",
    )
    prepared_asset.metadata_json = {
        **prepared_asset.metadata_json,
        "preparation_summary": summary,
        "source_asset_id": asset.id,
    }
    db.flush()
    return {"asset": serialize_asset(prepared_asset), "summary": summary}


def _serialize_model_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    sample = frame[columns].copy()
    for column in columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    return sample.dropna().copy()


def _serialize_coefficients(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in result.params.index.tolist():
        rows.append(
            {
                "term": name,
                "coefficient": float(result.params[name]),
                "std_error": float(result.bse[name]) if name in result.bse.index else None,
                "t_stat": float(result.tvalues[name]) if name in result.tvalues.index else None,
                "p_value": float(result.pvalues[name]) if name in result.pvalues.index else None,
            }
        )
    return rows


def _fit_ols(sample: pd.DataFrame, dependent: str, regressors: list[str], *, robust_covariance: bool = True) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(10, len(regressors) + 4):
        raise ValueError("Not enough complete observations for the selected model.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    return sm.OLS(sample[dependent], design).fit(cov_type="HC1" if robust_covariance else "nonrobust")


def _model_result_payload(
    *,
    model_type: str,
    model_label: str,
    asset: DataAsset,
    dependent: str,
    regressors: list[str],
    sample: pd.DataFrame,
    result: Any,
    narrative_lines: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "model_type": model_type,
        "model_label": model_label,
        "asset": serialize_asset(asset),
        "dependent": dependent,
        "regressors": regressors,
        "observations": int(result.nobs),
        "r_squared": float(result.rsquared) if getattr(result, "rsquared", None) is not None else None,
        "adj_r_squared": float(result.rsquared_adj) if getattr(result, "rsquared_adj", None) is not None else None,
        "aic": float(result.aic) if getattr(result, "aic", None) is not None else None,
        "bic": float(result.bic) if getattr(result, "bic", None) is not None else None,
        "coefficients": _serialize_coefficients(result),
        "narrative": narrative_lines,
        "sample_columns": list(sample.columns),
        "sample_preview": _frame_preview_rows(sample, limit=5),
    }
    if extra:
        payload.update(extra)
    return payload


def clean_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, meta = _load_analysis_frame(settings, asset, drop_duplicates=True)
    summary = {
        "original_rows": int(meta["rows_after_standardization"] + meta["duplicate_rows_detected"]),
        "cleaned_rows": int(len(frame)),
        "dropped_rows": int(meta["duplicate_rows_detected"]),
        "columns_before": list(meta["source_columns"].values()),
        "columns_after": list(frame.columns),
        "missing_by_column": {column: int(value) for column, value in frame.isna().sum().to_dict().items()},
    }

    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    cleaned_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-cleaned.csv",
        content=csv_bytes,
        content_type="text/csv",
        description=f"Cleaned derivative of {asset.title}",
    )
    cleaned_asset.metadata_json = {
        **cleaned_asset.metadata_json,
        "cleaning_summary": summary,
        "source_asset_id": asset.id,
    }
    db.flush()
    return {"asset": serialize_asset(cleaned_asset), "summary": summary}


def run_ols_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str],
    robust_covariance: bool = True,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)

    required_columns = [dependent, *independents]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = _serialize_model_frame(frame, required_columns)
    fitted = _fit_ols(sample, dependent, independents, robust_covariance=robust_covariance)
    summary_lines = [
        f"OLS run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Regressors: {', '.join(independents)}.",
        f"Observations used: {int(fitted.nobs)}.",
        f"R-squared: {float(fitted.rsquared):.4f}.",
    ]
    payload = _model_result_payload(
        model_type="ols",
        model_label="Ordinary Least Squares",
        asset=asset,
        dependent=dependent,
        regressors=independents,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={"residual_sum_squares": float(np.sum(np.square(fitted.resid)))},
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"OLS summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["ols", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_did_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    treatment_column: str,
    post_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, treatment_column, post_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = pd.to_numeric(sample[dependent], errors="coerce")
    sample[treatment_column] = _coerce_binary_series(sample[treatment_column])
    sample[post_column] = _coerce_binary_series(sample[post_column])
    for column in controls:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    sample = sample.dropna().copy()
    sample["did_interaction"] = sample[treatment_column] * sample[post_column]

    regressors = [treatment_column, post_column, "did_interaction", *controls]
    fitted = _fit_ols(sample, dependent, regressors, robust_covariance=robust_covariance)
    did_effect = float(fitted.params.get("did_interaction", np.nan))
    cell_means = []
    grouped = sample.groupby([treatment_column, post_column])[dependent].agg(["mean", "count"]).reset_index()
    for _, row in grouped.iterrows():
        cell_means.append(
            {
                "treatment": int(row[treatment_column]),
                "post": int(row[post_column]),
                "mean": float(row["mean"]),
                "count": int(row["count"]),
            }
        )

    summary_lines = [
        f"DID run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Treatment indicator: {treatment_column}.",
        f"Post indicator: {post_column}.",
        f"Estimated DID effect: {did_effect:.4f}.",
    ]
    payload = _model_result_payload(
        model_type="did",
        model_label="Difference-in-Differences",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "treatment_column": treatment_column,
            "post_column": post_column,
            "did_effect": did_effect,
            "cell_means": cell_means,
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"DID summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["did", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_gravity_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    flow_column: str,
    origin_mass_column: str,
    destination_mass_column: str,
    distance_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [flow_column, origin_mass_column, destination_mass_column, distance_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    sample = sample.dropna().copy()
    positive_mask = (
        (sample[flow_column] >= 0)
        & (sample[origin_mass_column] > 0)
        & (sample[destination_mass_column] > 0)
        & (sample[distance_column] > 0)
    )
    dropped_nonpositive = int((~positive_mask).sum())
    sample = sample.loc[positive_mask].copy()
    if len(sample) < max(12, len(controls) + 5):
        raise ValueError("Not enough positive, complete observations for the gravity model.")

    sample["ln_flow"] = np.log1p(sample[flow_column])
    sample["ln_origin_mass"] = np.log(sample[origin_mass_column])
    sample["ln_destination_mass"] = np.log(sample[destination_mass_column])
    sample["ln_distance"] = np.log(sample[distance_column])

    regressors = ["ln_origin_mass", "ln_destination_mass", "ln_distance", *controls]
    fitted = _fit_ols(sample, "ln_flow", regressors, robust_covariance=robust_covariance)
    summary_lines = [
        f"Gravity model run on {asset.title}.",
        f"Flow variable: {flow_column}.",
        f"Mass variables: {origin_mass_column}, {destination_mass_column}.",
        f"Distance variable: {distance_column}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="gravity",
        model_label="Gravity Model",
        asset=asset,
        dependent="ln_flow",
        regressors=regressors,
        sample=sample[["ln_flow", *regressors]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "flow_column": flow_column,
            "origin_mass_column": origin_mass_column,
            "destination_mass_column": destination_mass_column,
            "distance_column": distance_column,
            "dropped_nonpositive_rows": dropped_nonpositive,
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Gravity model summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["gravity", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_model_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    model_type: str,
    asset_id: str,
    dependent: str = "",
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    treatment_column: str = "",
    post_column: str = "",
    origin_mass_column: str = "",
    destination_mass_column: str = "",
    distance_column: str = "",
    robust_covariance: bool = True,
) -> dict[str, Any]:
    normalized_model = model_type.strip().lower()
    if normalized_model == "ols":
        return run_ols_analysis(
            settings,
            db,
            user=user,
            workspace=workspace,
            asset_id=asset_id,
            dependent=dependent,
            independents=independents or [],
            robust_covariance=robust_covariance,
        )
    if normalized_model == "did":
        return run_did_analysis(
            settings,
            db,
            user=user,
            workspace=workspace,
            asset_id=asset_id,
            dependent=dependent,
            treatment_column=treatment_column,
            post_column=post_column,
            controls=controls or [],
            robust_covariance=robust_covariance,
        )
    if normalized_model == "gravity":
        return run_gravity_analysis(
            settings,
            db,
            user=user,
            workspace=workspace,
            asset_id=asset_id,
            flow_column=dependent,
            origin_mass_column=origin_mass_column,
            destination_mass_column=destination_mass_column,
            distance_column=distance_column,
            controls=controls or [],
            robust_covariance=robust_covariance,
        )
    raise ValueError("Unsupported model type.")


def create_plot_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    chart_type: str,
    x_column: str,
    y_columns: list[str] | None = None,
    group_column: str = "",
    title: str = "",
    max_points: int = 400,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    normalized_chart_type = chart_type.strip().lower()
    y_columns = [column for column in (y_columns or []) if column]
    if x_column and x_column not in frame.columns:
        raise ValueError(f"Missing X column: {x_column}")
    for column in [*y_columns, group_column]:
        if column and column not in frame.columns:
            raise ValueError(f"Missing column: {column}")

    figure, axis = plt.subplots(figsize=(10, 6), dpi=160)
    figure.patch.set_facecolor("#fffdf8")
    axis.set_facecolor("#fffdf8")
    summary = ""

    if normalized_chart_type == "histogram":
        if not x_column:
            raise ValueError("Histogram requires one numeric column.")
        numeric = pd.to_numeric(frame[x_column], errors="coerce").dropna()
        if numeric.empty:
            raise ValueError("Selected histogram variable has no numeric observations.")
        axis.hist(numeric, bins=min(24, max(8, int(np.sqrt(len(numeric))))), color="#0b5f45", alpha=0.85, edgecolor="#f4efe6")
        axis.set_xlabel(x_column)
        axis.set_ylabel("Count")
        summary = f"Histogram of {x_column} using {len(numeric)} observations."
    elif normalized_chart_type == "bar":
        if not x_column or not y_columns:
            raise ValueError("Bar chart requires both X and Y columns.")
        y_column = y_columns[0]
        plot_frame = frame[[x_column, y_column]].copy()
        plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna().copy()
        grouped = plot_frame.groupby(x_column, dropna=False)[y_column].mean().sort_values(ascending=False).head(20)
        if grouped.empty:
            raise ValueError("Selected bar chart inputs do not produce usable data.")
        axis.bar(range(len(grouped)), grouped.values, color="#0b5f45")
        axis.set_xticks(range(len(grouped)))
        axis.set_xticklabels(grouped.index.astype(str), rotation=35, ha="right")
        axis.set_xlabel(x_column)
        axis.set_ylabel(f"Mean {y_column}")
        summary = f"Bar chart of mean {y_column} by {x_column}."
    elif normalized_chart_type == "scatter":
        if not x_column or not y_columns:
            raise ValueError("Scatter chart requires both X and Y columns.")
        y_column = y_columns[0]
        plot_frame = frame[[x_column, y_column] + ([group_column] if group_column else [])].copy()
        plot_frame[x_column] = pd.to_numeric(plot_frame[x_column], errors="coerce")
        plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna(subset=[x_column, y_column]).head(max_points).copy()
        if plot_frame.empty:
            raise ValueError("Selected scatter variables have no numeric overlap.")
        if group_column:
            for label, chunk in plot_frame.groupby(group_column):
                axis.scatter(chunk[x_column], chunk[y_column], alpha=0.7, label=str(label)[:30])
            axis.legend(loc="best")
        else:
            axis.scatter(plot_frame[x_column], plot_frame[y_column], alpha=0.72, color="#0b5f45")
        axis.set_xlabel(x_column)
        axis.set_ylabel(y_column)
        summary = f"Scatter plot of {y_column} against {x_column}."
    else:
        if not x_column or not y_columns:
            raise ValueError("Line chart requires an X column and at least one Y column.")
        plot_columns = [x_column, *y_columns]
        plot_frame = frame[plot_columns].copy()
        x_role = infer_column_role(plot_frame[x_column])
        if x_role == "date":
            plot_frame[x_column] = _coerce_date_series(plot_frame[x_column])
        else:
            numeric_x = pd.to_numeric(plot_frame[x_column], errors="coerce")
            if numeric_x.notna().sum():
                plot_frame[x_column] = numeric_x
        for y_column in y_columns:
            plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna().head(max_points).copy()
        if plot_frame.empty:
            raise ValueError("Selected line chart variables do not produce usable observations.")
        plot_frame = plot_frame.sort_values(by=x_column)
        for y_column in y_columns:
            axis.plot(plot_frame[x_column], plot_frame[y_column], marker="o", linewidth=1.8, label=y_column)
        if len(y_columns) > 1:
            axis.legend(loc="best")
        axis.set_xlabel(x_column)
        axis.set_ylabel("Value")
        summary = f"Line chart for {', '.join(y_columns)} over {x_column}."

    axis.set_title(title.strip() or summary)
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()

    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(figure)
    payload = buffer.getvalue()
    plot_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-{normalized_chart_type or 'chart'}.png",
        content=payload,
        content_type="image/png",
        description=f"{normalized_chart_type.title()} chart generated from {asset.title}",
    )
    plot_asset.kind = "chart_png"
    plot_asset.metadata_json = {
        **plot_asset.metadata_json,
        "analysis_kind": "plot",
        "source_asset_id": asset.id,
        "chart_type": normalized_chart_type or "line",
        "x_column": x_column,
        "y_columns": y_columns,
        "group_column": group_column,
        "summary": summary,
    }
    db.flush()
    return {
        "asset": serialize_asset(plot_asset),
        "chart_type": normalized_chart_type or "line",
        "title": title.strip() or summary,
        "summary": summary,
        "download_url": f"/api/assets/{plot_asset.id}/download",
    }
