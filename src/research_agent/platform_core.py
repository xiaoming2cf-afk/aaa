from __future__ import annotations

import json
import math
from statistics import NormalDist
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
from statsmodels.tsa.api import VAR
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.sandbox.regression.gmm import IV2SLS
from statsmodels.tools.sm_exceptions import PerfectSeparationError
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

    date_candidate = pd.to_datetime(text_values, errors="coerce", format="mixed")
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
    if isinstance(metadata, dict) and (metadata.get("workflow_type") == "model" or metadata.get("model_type")):
        metadata.setdefault("workflow_type", "model")
        metadata.setdefault("result_record_id", record.id)
        metadata.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
        record.metadata_json = metadata
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


def get_owned_knowledge_record(db: Session, *, user: User, record_id: str) -> KnowledgeRecord:
    record = db.get(KnowledgeRecord, record_id)
    if not record or record.owner_user_id != user.id:
        raise FileNotFoundError("Knowledge record not found.")
    return record


def get_owned_asset(db: Session, *, user: User, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id:
        raise FileNotFoundError("Asset not found.")
    return asset


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


def build_model_result_detail(db: Session, *, user: User, record_id: str) -> dict[str, Any]:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    metadata = dict(record.metadata_json or {})
    if not metadata.get("model_type"):
        raise ValueError("This knowledge record is not a model result.")
    metadata.setdefault("workflow_type", "model")
    metadata.setdefault("model_family", _infer_model_family(str(metadata.get("model_type", ""))))
    metadata.setdefault("result_record_id", record.id)
    metadata.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
    return {
        "record": serialize_knowledge_record(record),
        "result": metadata,
        "workspace_id": record.workspace_id,
    }


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


def _coerce_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _winsorize_series(series: pd.Series, lower_quantile: float, upper_quantile: float) -> pd.Series:
    clean = series.dropna()
    if clean.empty:
        return series
    lower = clean.quantile(lower_quantile)
    upper = clean.quantile(upper_quantile)
    return series.clip(lower=lower, upper=upper)


def _impute_series(series: pd.Series, method: str) -> pd.Series:
    normalized_method = (method or "none").strip().lower()
    if normalized_method in {"", "none"}:
        return series
    if normalized_method == "mean":
        return series.fillna(series.mean())
    if normalized_method == "median":
        return series.fillna(series.median())
    if normalized_method == "zero":
        return series.fillna(0)
    if normalized_method == "ffill":
        return series.ffill()
    if normalized_method == "bfill":
        return series.bfill()
    raise ValueError(f"Unsupported imputation method: {method}")


def _drop_outliers(
    sample: pd.DataFrame,
    columns: list[str],
    *,
    method: str,
    threshold: float,
) -> tuple[pd.DataFrame, int]:
    normalized_method = (method or "none").strip().lower()
    if normalized_method in {"", "none"} or not columns:
        return sample, 0

    mask = pd.Series(True, index=sample.index)
    if normalized_method == "iqr":
        for column in columns:
            clean = sample[column].dropna()
            if clean.empty:
                continue
            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1
            if pd.isna(iqr) or iqr == 0:
                continue
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            mask &= sample[column].isna() | sample[column].between(lower, upper)
    elif normalized_method == "zscore":
        for column in columns:
            clean = sample[column].dropna()
            if clean.empty:
                continue
            std = clean.std()
            if pd.isna(std) or std == 0:
                continue
            z_score = (sample[column] - clean.mean()) / std
            mask &= sample[column].isna() | (z_score.abs() <= threshold)
    else:
        raise ValueError(f"Unsupported outlier method: {method}")

    removed = int((~mask).sum())
    return sample.loc[mask].copy(), removed


def _prepare_selected_sample(
    frame: pd.DataFrame,
    *,
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    impute_columns: list[str] | None = None,
    impute_method: str = "none",
    winsorize_columns: list[str] | None = None,
    winsor_lower_quantile: float = 0.01,
    winsor_upper_quantile: float = 0.99,
    log_transform_columns: list[str] | None = None,
    standardize_columns: list[str] | None = None,
    minmax_scale_columns: list[str] | None = None,
    outlier_columns: list[str] | None = None,
    outlier_method: str = "none",
    outlier_threshold: float = 1.5,
    sort_column: str = "",
    time_group_column: str = "",
    difference_columns: list[str] | None = None,
    return_columns: list[str] | None = None,
    return_method: str = "simple",
    lag_columns: list[str] | None = None,
    lag_periods: int = 1,
    lead_columns: list[str] | None = None,
    lead_periods: int = 1,
    rolling_mean_columns: list[str] | None = None,
    rolling_volatility_columns: list[str] | None = None,
    rolling_window: int = 5,
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
    impute_columns = [column for column in (impute_columns or []) if column]
    winsorize_columns = [column for column in (winsorize_columns or []) if column]
    log_transform_columns = [column for column in (log_transform_columns or []) if column]
    standardize_columns = [column for column in (standardize_columns or []) if column]
    minmax_scale_columns = [column for column in (minmax_scale_columns or []) if column]
    outlier_columns = [column for column in (outlier_columns or []) if column]
    difference_columns = [column for column in (difference_columns or []) if column]
    return_columns = [column for column in (return_columns or []) if column]
    lag_columns = [column for column in (lag_columns or []) if column]
    lead_columns = [column for column in (lead_columns or []) if column]
    rolling_mean_columns = [column for column in (rolling_mean_columns or []) if column]
    rolling_volatility_columns = [column for column in (rolling_volatility_columns or []) if column]

    requested_columns = {
        *(include_columns or []),
        *required_columns,
        *numeric_columns,
        *binary_columns,
        *date_columns,
        *impute_columns,
        *winsorize_columns,
        *log_transform_columns,
        *standardize_columns,
        *minmax_scale_columns,
        *outlier_columns,
        *difference_columns,
        *return_columns,
        *lag_columns,
        *lead_columns,
        *rolling_mean_columns,
        *rolling_volatility_columns,
    }
    if sort_column:
        requested_columns.add(sort_column)
    if time_group_column:
        requested_columns.add(time_group_column)
    missing_columns = [column for column in requested_columns if column not in sample.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    if include_columns:
        if sort_column and sort_column not in include_columns:
            include_columns.append(sort_column)
        if time_group_column and time_group_column not in include_columns:
            include_columns.append(time_group_column)
        sample = sample[include_columns].copy()

    numeric_pipeline_columns = {
        *numeric_columns,
        *winsorize_columns,
        *log_transform_columns,
        *standardize_columns,
        *minmax_scale_columns,
        *outlier_columns,
        *difference_columns,
        *return_columns,
        *lag_columns,
        *lead_columns,
        *rolling_mean_columns,
        *rolling_volatility_columns,
    }
    if impute_method.strip().lower() in {"mean", "median", "zero"}:
        numeric_pipeline_columns.update(impute_columns)

    for column in numeric_pipeline_columns:
        if column in sample.columns:
            sample[column] = _coerce_numeric_series(sample[column])
    for column in binary_columns:
        if column in sample.columns:
            sample[column] = _coerce_binary_series(sample[column])
    for column in date_columns:
        if column in sample.columns:
            sample[column] = _coerce_date_series(sample[column])

    imputation_log: dict[str, str] = {}
    if impute_method.strip().lower() not in {"", "none"}:
        for column in impute_columns:
            if is_numeric_dtype(sample[column]) or impute_method.strip().lower() in {"ffill", "bfill"}:
                sample[column] = _impute_series(sample[column], impute_method)
                imputation_log[column] = impute_method.strip().lower()
            else:
                raise ValueError(f"Imputation method '{impute_method}' requires numeric columns for {column}.")

    winsorization_log: dict[str, dict[str, float]] = {}
    if winsorize_columns:
        if not (0 <= winsor_lower_quantile < winsor_upper_quantile <= 1):
            raise ValueError("Winsorization quantiles must satisfy 0 <= lower < upper <= 1.")
        for column in winsorize_columns:
            sample[column] = _winsorize_series(sample[column], winsor_lower_quantile, winsor_upper_quantile)
            winsorization_log[column] = {"lower": winsor_lower_quantile, "upper": winsor_upper_quantile}

    transformed_columns: dict[str, list[str]] = {"log": [], "zscore": [], "minmax": []}
    for column in log_transform_columns:
        if (sample[column].dropna() <= 0).any():
            raise ValueError(f"Log transform requires strictly positive values in column: {column}")
        sample[column] = np.log(sample[column])
        transformed_columns["log"].append(column)

    for column in standardize_columns:
        clean = sample[column].dropna()
        std = clean.std()
        if clean.empty or pd.isna(std) or std == 0:
            continue
        sample[column] = (sample[column] - clean.mean()) / std
        transformed_columns["zscore"].append(column)

    for column in minmax_scale_columns:
        clean = sample[column].dropna()
        if clean.empty:
            continue
        col_min = clean.min()
        col_max = clean.max()
        if pd.isna(col_min) or pd.isna(col_max) or col_max == col_min:
            continue
        sample[column] = (sample[column] - col_min) / (col_max - col_min)
        transformed_columns["minmax"].append(column)

    timeseries_requested = bool(
        difference_columns
        or return_columns
        or lag_columns
        or lead_columns
        or rolling_mean_columns
        or rolling_volatility_columns
    )
    if timeseries_requested and not sort_column:
        raise ValueError("Time-series preparation requires a sort column.")
    if lag_periods < 1 or lead_periods < 1:
        raise ValueError("Lag and lead periods must be at least 1.")
    if rolling_window < 2 and (rolling_mean_columns or rolling_volatility_columns):
        raise ValueError("Rolling window must be at least 2.")

    time_series_log: dict[str, Any] = {
        "sort_column": sort_column,
        "group_column": time_group_column,
        "difference_columns": [],
        "return_columns": [],
        "lag_columns": [],
        "lead_columns": [],
        "rolling_mean_columns": [],
        "rolling_volatility_columns": [],
    }
    derived_columns: list[str] = []
    if timeseries_requested:
        sort_keys = [column for column in [time_group_column, sort_column] if column]
        sample = sample.sort_values(sort_keys).copy()
        grouped = sample.groupby(time_group_column, dropna=False) if time_group_column else None

        def grouped_series(column: str):
            return grouped[column] if grouped is not None else sample[column]

        for column in difference_columns:
            derived_name = f"diff_{column}"
            sample[derived_name] = grouped_series(column).diff() if grouped is not None else sample[column].diff()
            time_series_log["difference_columns"].append(derived_name)
            derived_columns.append(derived_name)

        normalized_return_method = (return_method or "simple").strip().lower()
        for column in return_columns:
            shifted = grouped_series(column).shift(1) if grouped is not None else sample[column].shift(1)
            if normalized_return_method == "log":
                if (sample[column].dropna() <= 0).any():
                    raise ValueError(f"Log returns require strictly positive values in column: {column}")
                if (shifted.dropna() <= 0).any():
                    raise ValueError(f"Log returns require strictly positive lagged values in column: {column}")
                series = np.log(sample[column] / shifted)
            else:
                series = (sample[column] / shifted) - 1.0
            derived_name = f"{'logret' if normalized_return_method == 'log' else 'ret'}_{column}"
            sample[derived_name] = series
            time_series_log["return_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in lag_columns:
            derived_name = f"lag{int(lag_periods)}_{column}"
            sample[derived_name] = grouped_series(column).shift(int(lag_periods)) if grouped is not None else sample[column].shift(int(lag_periods))
            time_series_log["lag_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in lead_columns:
            derived_name = f"lead{int(lead_periods)}_{column}"
            sample[derived_name] = grouped_series(column).shift(-int(lead_periods)) if grouped is not None else sample[column].shift(-int(lead_periods))
            time_series_log["lead_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in rolling_mean_columns:
            derived_name = f"rollmean{int(rolling_window)}_{column}"
            if grouped is not None:
                sample[derived_name] = grouped[column].transform(lambda values: values.rolling(int(rolling_window)).mean())
            else:
                sample[derived_name] = sample[column].rolling(int(rolling_window)).mean()
            time_series_log["rolling_mean_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in rolling_volatility_columns:
            derived_name = f"rollvol{int(rolling_window)}_{column}"
            if grouped is not None:
                sample[derived_name] = grouped[column].transform(lambda values: values.rolling(int(rolling_window)).std())
            else:
                sample[derived_name] = sample[column].rolling(int(rolling_window)).std()
            time_series_log["rolling_volatility_columns"].append(derived_name)
            derived_columns.append(derived_name)

    sample, outliers_removed = _drop_outliers(
        sample,
        outlier_columns,
        method=outlier_method,
        threshold=outlier_threshold,
    )

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
        "imputed_columns": imputation_log,
        "winsorized_columns": winsorization_log,
        "transformed_columns": transformed_columns,
        "time_series_features": time_series_log,
        "derived_columns": derived_columns,
        "outlier_columns": outlier_columns,
        "outlier_method": outlier_method,
        "outlier_threshold": outlier_threshold,
        "outliers_removed": outliers_removed,
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
    if role_map["binary"] and role_map["numeric"]:
        suggested_models.extend(["logit", "probit"])
    if role_map["numeric"]:
        suggested_models.extend(["ppml", "rdd", "historical_var", "parametric_var", "ewma_volatility", "capm", "mean_variance", "minimum_variance", "risk_parity"])
    if role_map["numeric"] and len(role_map["binary"]) >= 2:
        suggested_models.extend(["did", "event_study"])
    if len(role_map["numeric"]) >= 3 and (role_map["categorical"] or role_map["text"] or role_map["date"]):
        suggested_models.extend(["fixed_effects", "arima", "var", "taylor_rule"])
    if len(role_map["numeric"]) >= 4:
        suggested_models.extend(["gravity", "iv_2sls", "panel_iv", "fama_french_3", "black_scholes", "binomial_option", "altman_z", "dupont"])
    suggested_models.append("rbc_dsge")
    suggested_models = list(dict.fromkeys(suggested_models))

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


def build_processing_result_detail(
    settings: Settings,
    db: Session,
    *,
    user: User,
    asset_id: str,
) -> dict[str, Any]:
    asset = get_owned_asset(db, user=user, asset_id=asset_id)
    if asset.kind not in DATASET_KINDS:
        raise ValueError("This asset is not a structured dataset.")
    workspace = db.get(Workspace, asset.workspace_id)
    if not workspace or workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    detail = (asset.metadata_json or {}).get("processing_result")
    asset_payload = serialize_asset(asset)
    if isinstance(asset_payload.get("metadata"), dict):
        asset_payload["metadata"] = {key: value for key, value in asset_payload["metadata"].items() if key != "processing_result"}
    if not isinstance(detail, dict):
        summary = (asset.metadata_json or {}).get("preparation_summary") or {}
        detail = {
            "workflow_type": "data_processing",
            "processing_family": summary.get("workflow_group") or "sample_preparation",
            "asset": asset_payload,
            "summary": summary,
            "audit_trail": {
                "source_asset_id": (asset.metadata_json or {}).get("source_asset_id"),
                "prepared_asset_id": asset.id,
                "prepared_download_url": f"/api/assets/{asset.id}/download",
                "manual_checklist": [
                    "Download the prepared sample and compare row counts, columns, and preview rows.",
                    "Reapply every documented transformation in order using the raw source asset.",
                    "Confirm derived columns and filters match the saved processing summary.",
                ],
                "operations": summary,
            },
            "result_detail_path": f"/data-lab/results/processing/{asset.id}",
        }
    profile = profile_dataset_asset(settings, db, user=user, workspace=workspace, asset_id=asset.id)
    if isinstance(profile.get("asset", {}).get("metadata"), dict):
        profile["asset"]["metadata"] = {
            key: value for key, value in profile["asset"]["metadata"].items() if key != "processing_result"
        }
    detail["asset"] = asset_payload
    detail["result_detail_path"] = detail.get("result_detail_path") or f"/data-lab/results/processing/{asset.id}"
    detail["profile"] = profile
    detail.setdefault("preview_rows", profile.get("preview_rows", []))
    detail["workspace_id"] = workspace.id
    return detail


def prepare_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    workflow_group: str = "sample_preparation",
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    impute_columns: list[str] | None = None,
    impute_method: str = "none",
    winsorize_columns: list[str] | None = None,
    winsor_lower_quantile: float = 0.01,
    winsor_upper_quantile: float = 0.99,
    log_transform_columns: list[str] | None = None,
    standardize_columns: list[str] | None = None,
    minmax_scale_columns: list[str] | None = None,
    outlier_columns: list[str] | None = None,
    outlier_method: str = "none",
    outlier_threshold: float = 1.5,
    sort_column: str = "",
    time_group_column: str = "",
    difference_columns: list[str] | None = None,
    return_columns: list[str] | None = None,
    return_method: str = "simple",
    lag_columns: list[str] | None = None,
    lag_periods: int = 1,
    lead_columns: list[str] | None = None,
    lead_periods: int = 1,
    rolling_mean_columns: list[str] | None = None,
    rolling_volatility_columns: list[str] | None = None,
    rolling_window: int = 5,
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
        impute_columns=impute_columns,
        impute_method=impute_method,
        winsorize_columns=winsorize_columns,
        winsor_lower_quantile=winsor_lower_quantile,
        winsor_upper_quantile=winsor_upper_quantile,
        log_transform_columns=log_transform_columns,
        standardize_columns=standardize_columns,
        minmax_scale_columns=minmax_scale_columns,
        outlier_columns=outlier_columns,
        outlier_method=outlier_method,
        outlier_threshold=outlier_threshold,
        sort_column=sort_column,
        time_group_column=time_group_column,
        difference_columns=difference_columns,
        return_columns=return_columns,
        return_method=return_method,
        lag_columns=lag_columns,
        lag_periods=lag_periods,
        lead_columns=lead_columns,
        lead_periods=lead_periods,
        rolling_mean_columns=rolling_mean_columns,
        rolling_volatility_columns=rolling_volatility_columns,
        rolling_window=rolling_window,
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
    preview_rows = _frame_preview_rows(prepared_frame)
    audit_trail = {
        "source_asset_id": asset.id,
        "source_asset_title": asset.title,
        "prepared_asset_id": prepared_asset.id,
        "prepared_download_url": f"/api/assets/{prepared_asset.id}/download",
        "manual_checklist": [
            "Download the prepared asset and compare row/column counts with rows_after_prepare and columns.",
            "Reapply each cleaning step in order: imputation, winsorization, transforms, outlier filter, and missing-value filtering.",
            "Verify the preview_rows against the downloaded prepared sample.",
        ],
        "operations": {
            "required_columns": summary["required_columns"],
            "numeric_columns": summary["numeric_columns"],
            "binary_columns": summary["binary_columns"],
            "date_columns": summary["date_columns"],
            "imputed_columns": summary["imputed_columns"],
            "winsorized_columns": summary["winsorized_columns"],
            "transformed_columns": summary["transformed_columns"],
            "time_series_features": summary["time_series_features"],
            "derived_columns": summary["derived_columns"],
            "outlier_columns": summary["outlier_columns"],
            "outlier_method": summary["outlier_method"],
            "outlier_threshold": summary["outlier_threshold"],
            "drop_duplicates": drop_duplicates,
            "drop_missing_required": drop_missing_required,
            "workflow_group": workflow_group or "sample_preparation",
        },
    }
    processing_result = {
        "workflow_type": "data_processing",
        "processing_family": workflow_group or "sample_preparation",
        "asset": serialize_asset(prepared_asset),
        "summary": summary,
        "preview_rows": preview_rows,
        "audit_trail": audit_trail,
        "result_detail_path": f"/data-lab/results/processing/{prepared_asset.id}",
    }
    prepared_asset.metadata_json = {
        **prepared_asset.metadata_json,
        "preparation_summary": summary,
        "source_asset_id": asset.id,
        "processing_result": processing_result,
    }
    db.flush()
    return processing_result


def _serialize_model_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    sample = frame[columns].copy()
    for column in columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    return sample.dropna().copy()


def _serialize_coefficients(result: Any) -> list[dict[str, Any]]:
    params = result.params
    if hasattr(params, "index"):
        term_names = list(params.index)
        param_values = params
    else:
        term_names = list(getattr(result.model, "exog_names", []))
        if not term_names:
            term_names = [f"x{i}" for i in range(len(params))]
        param_values = pd.Series(params, index=term_names)

    bse = result.bse if hasattr(result, "bse") else None
    if bse is None:
        bse = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(bse, "index"):
        bse = pd.Series(bse, index=term_names)

    tvalues = getattr(result, "tvalues", None)
    if tvalues is None:
        tvalues = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(tvalues, "index"):
        tvalues = pd.Series(tvalues, index=term_names)

    pvalues = getattr(result, "pvalues", None)
    if pvalues is None:
        pvalues = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(pvalues, "index"):
        pvalues = pd.Series(pvalues, index=term_names)

    rows: list[dict[str, Any]] = []
    for name in term_names:
        rows.append(
            {
                "term": name,
                "coefficient": float(param_values[name]),
                "std_error": float(bse[name]) if name in bse.index and pd.notna(bse[name]) else None,
                "t_stat": float(tvalues[name]) if name in tvalues.index and pd.notna(tvalues[name]) else None,
                "p_value": float(pvalues[name]) if name in pvalues.index and pd.notna(pvalues[name]) else None,
            }
        )
    return rows


def _safe_result_float_attr(result: Any, attribute: str) -> float | None:
    try:
        value = getattr(result, attribute, None)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fit_ols(sample: pd.DataFrame, dependent: str, regressors: list[str], *, robust_covariance: bool = True) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(10, len(regressors) + 4):
        raise ValueError("Not enough complete observations for the selected model.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    return sm.OLS(sample[dependent], design).fit(cov_type="HC1" if robust_covariance else "nonrobust")


def _fit_binary_response(
    sample: pd.DataFrame,
    dependent: str,
    regressors: list[str],
    *,
    model_kind: str,
    robust_covariance: bool = True,
) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(20, len(regressors) * 3):
        raise ValueError("Not enough complete observations for the selected binary response model.")
    if sample[dependent].nunique(dropna=True) < 2:
        raise ValueError("Binary response models require both 0 and 1 outcomes.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    model_class = sm.Logit if model_kind == "logit" else sm.Probit
    try:
        fitted = model_class(sample[dependent], design).fit(
            disp=False,
            cov_type="HC1" if robust_covariance else "nonrobust",
        )
    except PerfectSeparationError as exc:
        raise ValueError("Perfect separation detected; try different regressors or a larger sample.") from exc
    except Exception as exc:
        raise ValueError(f"{model_kind.title()} estimation failed: {exc}") from exc
    return fitted


def _fit_iv_2sls(
    sample: pd.DataFrame,
    dependent: str,
    exogenous: list[str],
    endogenous: str,
    instruments: list[str],
    *,
    robust_covariance: bool = True,
) -> tuple[Any, str]:
    if not instruments:
        raise ValueError("IV-2SLS requires at least one instrument.")
    regressor_count = len(exogenous) + 1
    if len(sample) < max(12, regressor_count + len(instruments) + 4):
        raise ValueError("Not enough complete observations for IV-2SLS.")
    exog_design = pd.concat(
        [sm.add_constant(sample[exogenous], has_constant="add"), sample[[endogenous]]],
        axis=1,
    )
    instrument_design = pd.concat(
        [sm.add_constant(sample[exogenous], has_constant="add"), sample[instruments]],
        axis=1,
    )
    fitted = IV2SLS(sample[dependent], exog_design, instrument_design).fit()
    if robust_covariance:
        try:
            fitted = fitted.get_robustcov_results(cov_type="HC1")
            return fitted, "HC1"
        except Exception:
            return fitted, "nonrobust"
    return fitted, "nonrobust"


def _fit_ppml(sample: pd.DataFrame, dependent: str, regressors: list[str], *, robust_covariance: bool = True) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(12, len(regressors) + 4):
        raise ValueError("Not enough complete observations for PPML.")
    if (sample[dependent] < 0).any():
        raise ValueError("PPML requires a nonnegative dependent variable.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    return sm.GLM(
        sample[dependent],
        design,
        family=sm.families.Poisson(),
    ).fit(cov_type="HC1" if robust_covariance else "nonrobust")


def _build_fe_dummies(
    sample: pd.DataFrame,
    *,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    entity_dummies = pd.get_dummies(sample[entity_column], prefix=f"fe_{entity_column}", drop_first=True, dtype=float)
    fe_frames = [entity_dummies]
    fe_labels = [entity_column]
    if include_time_effects and time_column:
        time_dummies = pd.get_dummies(sample[time_column], prefix=f"fe_{time_column}", drop_first=True, dtype=float)
        fe_frames.append(time_dummies)
        fe_labels.append(time_column)
    if not fe_frames:
        return pd.DataFrame(index=sample.index), fe_labels
    return pd.concat(fe_frames, axis=1), fe_labels


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
    extra = extra or {}
    covariance_type = extra.get("covariance_type") or getattr(result, "cov_type", "nonrobust")
    equation_terms = regressors if regressors else ["1"]
    payload = {
        "model_type": model_type,
        "model_label": model_label,
        "asset": serialize_asset(asset),
        "dependent": dependent,
        "regressors": regressors,
        "observations": int(getattr(result, "nobs", len(sample))),
        "r_squared": _safe_result_float_attr(result, "rsquared"),
        "adj_r_squared": _safe_result_float_attr(result, "rsquared_adj"),
        "pseudo_r_squared": _safe_result_float_attr(result, "prsquared"),
        "aic": _safe_result_float_attr(result, "aic"),
        "bic": _safe_result_float_attr(result, "bic"),
        "log_likelihood": _safe_result_float_attr(result, "llf"),
        "coefficients": _serialize_coefficients(result),
        "narrative": narrative_lines,
        "sample_columns": list(sample.columns),
        "sample_preview": _frame_preview_rows(sample, limit=5),
        "specification": {
            "model_type": model_type,
            "model_label": model_label,
            "dependent": dependent,
            "regressors": regressors,
            "covariance_type": covariance_type,
            "equation": f"{dependent} ~ {' + '.join(equation_terms)}",
        },
        "audit_trail": {
            "sample_asset_id": asset.id,
            "sample_title": asset.title,
            "sample_download_url": f"/api/assets/{asset.id}/download",
            "rows_used": int(len(sample)),
            "sample_columns": list(sample.columns),
            "covariance_type": covariance_type,
            "manual_checklist": [
                "Download the prepared sample asset referenced in sample_asset_id.",
                "Rebuild any derived regressors listed in derived_columns before estimation.",
                "Use the listed regressors, covariance_type, and sample filters to reproduce the model manually.",
                "Compare the reproduced coefficient table with the coefficients array term by term.",
            ],
        },
    }
    audit_extra = extra.pop("audit_trail", None)
    if audit_extra:
        payload["audit_trail"].update(audit_extra)
    payload.update(extra)
    return payload


def _nonregression_result_payload(
    *,
    model_type: str,
    model_label: str,
    asset: DataAsset,
    sample: pd.DataFrame | None,
    narrative_lines: list[str],
    specification: dict[str, Any],
    audit_trail: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    tables: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "model_type": model_type,
        "model_label": model_label,
        "asset": serialize_asset(asset),
        "observations": int(len(sample)) if sample is not None else 0,
        "narrative": narrative_lines,
        "specification": specification,
        "audit_trail": {
            "sample_asset_id": asset.id,
            "sample_title": asset.title,
            "sample_download_url": f"/api/assets/{asset.id}/download",
            **audit_trail,
        },
        "metrics": metrics or {},
        "tables": tables or {},
        "sample_columns": list(sample.columns) if sample is not None else [],
        "sample_preview": _frame_preview_rows(sample, limit=5) if sample is not None else [],
    }
    if extra:
        payload.update(extra)
    return payload


def _sort_sample_by_time(sample: pd.DataFrame, time_column: str) -> pd.DataFrame:
    if not time_column or time_column not in sample.columns:
        return sample
    prepared = sample.copy()
    parsed = pd.to_datetime(prepared[time_column], errors="coerce")
    if parsed.notna().sum():
        prepared["__sort_time"] = parsed
    else:
        numeric = pd.to_numeric(prepared[time_column], errors="coerce")
        if numeric.notna().sum():
            prepared["__sort_time"] = numeric
        else:
            prepared["__sort_time"] = prepared[time_column].astype(str)
    prepared = prepared.sort_values("__sort_time").drop(columns="__sort_time")
    return prepared


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _black_scholes_price(
    *,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
    option_type: str,
) -> dict[str, float]:
    if spot <= 0 or strike <= 0 or maturity <= 0 or volatility <= 0:
        raise ValueError("Black-Scholes requires strictly positive spot, strike, maturity, and volatility.")
    sqrt_t = math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility**2) * maturity) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    if option_type == "put":
        price = strike * math.exp(-rate * maturity) * _normal_cdf(-d2) - spot * _normal_cdf(-d1)
        delta = _normal_cdf(d1) - 1.0
    else:
        price = spot * _normal_cdf(d1) - strike * math.exp(-rate * maturity) * _normal_cdf(d2)
        delta = _normal_cdf(d1)
    gamma = math.exp(-(d1**2) / 2.0) / (spot * volatility * sqrt_t * math.sqrt(2.0 * math.pi))
    return {"price": price, "delta": delta, "gamma": gamma, "d1": d1, "d2": d2}


def _binomial_option_price(
    *,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
    steps: int,
    option_type: str,
) -> float:
    if steps < 1:
        raise ValueError("Binomial option pricing requires at least one step.")
    if spot <= 0 or strike <= 0 or maturity <= 0 or volatility <= 0:
        raise ValueError("Binomial option pricing requires strictly positive spot, strike, maturity, and volatility.")
    dt = maturity / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    discount = math.exp(-rate * dt)
    probability = (math.exp(rate * dt) - down) / (up - down)
    if probability <= 0 or probability >= 1:
        raise ValueError("Invalid binomial probability. Check rate, volatility, maturity, and step count.")
    terminal = []
    for step in range(steps + 1):
        stock_price = spot * (up ** (steps - step)) * (down**step)
        if option_type == "put":
            payoff = max(strike - stock_price, 0.0)
        else:
            payoff = max(stock_price - strike, 0.0)
        terminal.append(payoff)
    values = terminal
    for level in range(steps, 0, -1):
        values = [
            discount * (probability * values[index] + (1 - probability) * values[index + 1])
            for index in range(level)
        ]
    return float(values[0])


def _risk_parity_weights(covariance: np.ndarray, *, iterations: int = 600, tolerance: float = 1e-7) -> np.ndarray:
    count = covariance.shape[0]
    weights = np.full(count, 1.0 / count)
    for _ in range(iterations):
        portfolio_variance = float(weights @ covariance @ weights)
        if portfolio_variance <= 0:
            break
        marginal = covariance @ weights
        risk_contrib = weights * marginal / math.sqrt(portfolio_variance)
        target = risk_contrib.sum() / count
        if np.max(np.abs(risk_contrib - target)) <= tolerance:
            break
        safe_rc = np.where(np.abs(risk_contrib) < 1e-12, 1e-12, risk_contrib)
        weights = weights * target / safe_rc
        weights = np.clip(weights, 1e-8, None)
        weights = weights / weights.sum()
    return weights


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
        extra={
            "residual_sum_squares": float(np.sum(np.square(fitted.resid))),
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent or regressor values are dropped."],
            },
        },
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
            "audit_trail": {
                "derived_columns": ["did_interaction"],
                "filters": ["Rows with missing outcome, treatment, post indicator, or selected controls are dropped."],
            },
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
            "audit_trail": {
                "derived_columns": ["ln_flow", "ln_origin_mass", "ln_destination_mass", "ln_distance"],
                "filters": [
                    "Rows with missing flow, mass, distance, or selected controls are dropped.",
                    "Rows with negative flow or nonpositive mass/distance are excluded before log transforms.",
                ],
            },
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


def run_ppml_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = _serialize_model_frame(frame, required_columns)
    fitted = _fit_ppml(sample, dependent, regressors, robust_covariance=robust_covariance)
    summary_lines = [
        f"PPML run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="ppml",
        model_label="PPML",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "mean_prediction": float(np.mean(fitted.predict())) if len(sample) else None,
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent or regressor values are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"PPML summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["ppml", "poisson", "econometrics"],
        metadata=payload,
    )
    return payload


def _event_period_label(period: int) -> str:
    if period < 0:
        return f"lead_{abs(period)}"
    if period > 0:
        return f"lag_{period}"
    return "event_0"


def run_event_study_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    treatment_column: str,
    event_time_column: str,
    controls: list[str] | None = None,
    entity_column: str = "",
    time_column: str = "",
    include_time_effects: bool = False,
    lead_window: int = 4,
    lag_window: int = 4,
    omitted_period: int = -1,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, treatment_column, event_time_column, *controls]
    if entity_column:
        required_columns.append(entity_column)
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample[treatment_column] = _coerce_binary_series(sample[treatment_column])
    sample[event_time_column] = _coerce_numeric_series(sample[event_time_column])
    for column in controls:
        sample[column] = _coerce_numeric_series(sample[column])
    if entity_column:
        sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()
    sample[event_time_column] = sample[event_time_column].round().astype(int)

    if lead_window < 0 or lag_window < 0:
        raise ValueError("Lead and lag windows must be nonnegative.")
    periods = list(range(-int(lead_window), int(lag_window) + 1))
    if omitted_period not in periods:
        raise ValueError("Omitted period must lie within the requested lead/lag window.")

    event_columns: list[str] = []
    dynamic_effects: list[dict[str, Any]] = []
    for period in periods:
        if period == omitted_period:
            continue
        column_name = f"event_{_event_period_label(period)}"
        sample[column_name] = (
            (sample[treatment_column] == 1.0) & (sample[event_time_column] == period)
        ).astype(float)
        if sample[column_name].sum() <= 0:
            sample = sample.drop(columns=[column_name])
            continue
        event_columns.append(column_name)
        dynamic_effects.append({"period": period, "column": column_name})

    if not event_columns:
        raise ValueError("No event-time cells are available in the selected window.")

    regressors = [*event_columns, *controls]
    fe_labels: list[str] = []
    derived_columns = event_columns.copy()
    if entity_column:
        fe_dummies, fe_labels = _build_fe_dummies(
            sample,
            entity_column=entity_column,
            time_column=time_column,
            include_time_effects=include_time_effects,
        )
        if not fe_dummies.empty:
            sample = pd.concat([sample, fe_dummies], axis=1)
            regressors.extend(list(fe_dummies.columns))
            derived_columns.extend(list(fe_dummies.columns))

    fitted = _fit_ols(sample[[dependent, *regressors]].copy(), dependent, regressors, robust_covariance=robust_covariance)
    effect_map = {row["column"]: row["period"] for row in dynamic_effects}
    for coefficient in _serialize_coefficients(fitted):
        period = effect_map.get(coefficient["term"])
        if period is not None:
            coefficient["period"] = period

    summary_lines = [
        f"Event study run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Treatment indicator: {treatment_column}.",
        f"Relative event-time column: {event_time_column}.",
        f"Window: [{-int(lead_window)}, {int(lag_window)}], omitted period {int(omitted_period)}.",
    ]
    payload = _model_result_payload(
        model_type="event_study",
        model_label="Event Study",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, treatment_column, event_time_column, *controls]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "treatment_column": treatment_column,
            "event_time_column": event_time_column,
            "control_columns": controls,
            "lead_window": int(lead_window),
            "lag_window": int(lag_window),
            "omitted_period": int(omitted_period),
            "dynamic_effects": [
                {
                    "period": effect_map.get(item["term"]),
                    "term": item["term"],
                    "coefficient": item["coefficient"],
                    "std_error": item["std_error"],
                    "p_value": item["p_value"],
                }
                for item in _serialize_coefficients(fitted)
                if item["term"] in effect_map
            ],
            "audit_trail": {
                "derived_columns": derived_columns,
                "filters": [
                    "Rows with missing outcome, treatment, event-time, or selected controls are dropped.",
                    f"Event window restricted to periods between {-int(lead_window)} and {int(lag_window)}.",
                ],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Event study summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["event_study", "dynamic_did", "econometrics"],
        metadata=payload,
    )
    return payload


def run_rdd_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    running_column: str,
    controls: list[str] | None = None,
    cutoff: float = 0.0,
    bandwidth: float = 0.0,
    polynomial_order: int = 1,
    treat_above_cutoff: bool = True,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, running_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if polynomial_order < 1 or polynomial_order > 3:
        raise ValueError("RDD polynomial order must be between 1 and 3.")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample[running_column] = _coerce_numeric_series(sample[running_column])
    for column in controls:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    sample["running_centered"] = sample[running_column] - float(cutoff)
    if bandwidth and bandwidth > 0:
        sample = sample.loc[sample["running_centered"].abs() <= float(bandwidth)].copy()
    if sample.empty:
        raise ValueError("RDD bandwidth leaves no usable observations.")

    if treat_above_cutoff:
        sample["rdd_treatment"] = (sample["running_centered"] >= 0).astype(float)
    else:
        sample["rdd_treatment"] = (sample["running_centered"] <= 0).astype(float)

    regressors = ["rdd_treatment"]
    derived_columns = ["running_centered", "rdd_treatment"]
    for power in range(1, int(polynomial_order) + 1):
        base_name = "running_centered" if power == 1 else f"running_centered_pow_{power}"
        if power > 1:
            sample[base_name] = sample["running_centered"] ** power
            derived_columns.append(base_name)
        regressors.append(base_name)
        interaction_name = f"rdd_treatment_x_{base_name}"
        sample[interaction_name] = sample["rdd_treatment"] * sample[base_name]
        regressors.append(interaction_name)
        derived_columns.append(interaction_name)
    regressors.extend(controls)

    fitted = _fit_ols(sample[[dependent, *regressors]].copy(), dependent, regressors, robust_covariance=robust_covariance)
    local_effect = float(fitted.params.get("rdd_treatment", np.nan))
    summary_lines = [
        f"RDD run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Running variable: {running_column}.",
        f"Cutoff: {float(cutoff):.4f}.",
        f"Local treatment effect at cutoff: {local_effect:.4f}.",
    ]
    payload = _model_result_payload(
        model_type="rdd",
        model_label="RDD",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, running_column, *controls]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "running_column": running_column,
            "cutoff": float(cutoff),
            "bandwidth": float(bandwidth),
            "polynomial_order": int(polynomial_order),
            "treat_above_cutoff": bool(treat_above_cutoff),
            "local_effect": local_effect,
            "audit_trail": {
                "derived_columns": derived_columns,
                "filters": [
                    "Rows with missing outcome, running variable, or selected controls are dropped.",
                    f"Bandwidth filter: {float(bandwidth)}." if bandwidth and bandwidth > 0 else "No bandwidth filter applied.",
                ],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"RDD summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["rdd", "causal_inference", "econometrics"],
        metadata=payload,
    )
    return payload


def run_panel_iv_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    endogenous_column: str,
    instrument_columns: list[str] | None = None,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    exogenous = [column for column in [*(independents or []), *(controls or [])] if column]
    instruments = [column for column in (instrument_columns or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, endogenous_column, entity_column, *exogenous, *instruments]
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    numeric_columns = [dependent, endogenous_column, *exogenous, *instruments]
    for column in numeric_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()

    fe_dummies, fe_labels = _build_fe_dummies(
        sample,
        entity_column=entity_column,
        time_column=time_column,
        include_time_effects=include_time_effects,
    )
    if not fe_dummies.empty:
        sample = pd.concat([sample, fe_dummies], axis=1)
    expanded_exogenous = [*exogenous, *list(fe_dummies.columns)]
    fitted, covariance_type = _fit_iv_2sls(
        sample,
        dependent,
        exogenous=expanded_exogenous,
        endogenous=endogenous_column,
        instruments=instruments,
        robust_covariance=robust_covariance,
    )
    summary_lines = [
        f"Panel IV run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Endogenous regressor: {endogenous_column}.",
        f"Instruments: {', '.join(instruments)}.",
        f"Fixed effects: {', '.join(fe_labels)}.",
    ]
    payload = _model_result_payload(
        model_type="panel_iv",
        model_label="Panel IV",
        asset=asset,
        dependent=dependent,
        regressors=[*expanded_exogenous, endogenous_column],
        sample=sample[[dependent, endogenous_column, *exogenous, *instruments, entity_column] + ([time_column] if include_time_effects and time_column else [])].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "endogenous_column": endogenous_column,
            "instrument_columns": instruments,
            "exogenous_columns": exogenous,
            "entity_column": entity_column,
            "time_column": time_column if include_time_effects else "",
            "include_time_effects": include_time_effects,
            "entity_count": int(sample[entity_column].nunique()),
            "time_count": int(sample[time_column].nunique()) if include_time_effects and time_column else 0,
            "covariance_type": covariance_type,
            "covariance_note": "Panel IV uses conventional covariance when robust covariance is unavailable in the current backend."
            if robust_covariance and covariance_type != "HC1"
            else "",
            "audit_trail": {
                "derived_columns": list(fe_dummies.columns),
                "filters": [
                    "Rows with missing dependent, endogenous regressor, instrument, or selected controls are dropped.",
                ],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Panel IV summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["panel_iv", "instrumental_variables", "econometrics"],
        metadata=payload,
    )
    return payload


def run_arima_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    time_column: str = "",
    arima_order: tuple[int, int, int] = (1, 0, 0),
    forecast_steps: int = 5,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [dependent] + ([time_column] if time_column else [])
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample = sample.dropna(subset=[dependent]).copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    p, d, q = arima_order
    if len(sample) < max(20, p + d + q + 8):
        raise ValueError("Not enough observations for the selected ARIMA order.")
    fitted = ARIMA(sample[dependent], order=(p, d, q)).fit()
    forecast = fitted.forecast(steps=int(forecast_steps))
    summary_lines = [
        f"ARIMA({p}, {d}, {q}) run on {asset.title}.",
        f"Target series: {dependent}.",
        f"Forecast horizon: {int(forecast_steps)} step(s).",
    ]
    return _model_result_payload(
        model_type="arima",
        model_label="ARIMA Forecast",
        asset=asset,
        dependent=dependent,
        regressors=[f"ARIMA({p},{d},{q})"],
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "model_family": "time_series_finance",
            "time_column": time_column,
            "forecast": [{"step": index + 1, "forecast": float(value)} for index, value in enumerate(np.asarray(forecast).tolist())],
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing target values are dropped.", "Series is sorted by the selected time column before estimation." if time_column else "Series order follows the uploaded sample order."],
            },
        },
    )


def run_var_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    lags: int = 1,
    forecast_steps: int = 5,
) -> dict[str, Any]:
    series_columns = [column for column in series_columns if column]
    if len(series_columns) < 2:
        raise ValueError("VAR requires at least two series columns.")
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [*series_columns, *([time_column] if time_column else [])]
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in series_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    if len(sample) < max(18, len(series_columns) * (lags + 2)):
        raise ValueError("Not enough observations for VAR estimation.")
    fitted = VAR(sample[series_columns]).fit(maxlags=int(lags), trend="c")
    lag_order = int(fitted.k_ar)
    forecast_values = fitted.forecast(sample[series_columns].values[-lag_order:], steps=int(forecast_steps))
    coefficients: list[dict[str, Any]] = []
    for equation in fitted.names:
        for term in fitted.params.index:
            coefficients.append(
                {
                    "equation": equation,
                    "term": term,
                    "coefficient": float(fitted.params.loc[term, equation]),
                    "std_error": float(fitted.stderr.loc[term, equation]) if term in fitted.stderr.index else None,
                    "p_value": float(fitted.pvalues.loc[term, equation]) if term in fitted.pvalues.index else None,
                }
            )
    forecast_rows = [
        {"step": step, **{series_columns[index]: float(value) for index, value in enumerate(row)}}
        for step, row in enumerate(forecast_values, start=1)
    ]
    summary_lines = [
        f"VAR({lag_order}) run on {asset.title}.",
        f"Series: {', '.join(series_columns)}.",
        f"Forecast horizon: {int(forecast_steps)} step(s).",
    ]
    return _nonregression_result_payload(
        model_type="var",
        model_label="Vector Autoregression",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), *series_columns]].copy(),
        narrative_lines=summary_lines,
        specification={
            "model_type": "var",
            "model_family": "time_series_finance",
            "series_columns": series_columns,
            "time_column": time_column,
            "lags": lag_order,
            "forecast_steps": int(forecast_steps),
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), *series_columns],
            "manual_checklist": [
                "Download the sample asset and sort it by the listed time_column if one is provided.",
                "Estimate a VAR with the same lag order on the listed series columns.",
                "Compare coefficient blocks and forecast rows equation by equation.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        tables={"coefficients": coefficients, "forecast": forecast_rows},
        metrics={"lag_order": lag_order, "aic": float(fitted.aic), "bic": float(fitted.bic)},
    )


def run_altman_z_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    working_capital_column: str,
    retained_earnings_column: str,
    ebit_column: str,
    market_equity_column: str,
    sales_column: str,
    total_assets_column: str,
    total_liabilities_column: str,
) -> dict[str, Any]:
    required_columns = [working_capital_column, retained_earnings_column, ebit_column, market_equity_column, sales_column, total_assets_column, total_liabilities_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    positive_mask = (sample[total_assets_column] > 0) & (sample[total_liabilities_column] > 0)
    sample = sample.loc[positive_mask].copy()
    if sample.empty:
        raise ValueError("Altman Z-score requires positive total assets and total liabilities.")
    sample["altman_z"] = 1.2 * (sample[working_capital_column] / sample[total_assets_column]) + 1.4 * (sample[retained_earnings_column] / sample[total_assets_column]) + 3.3 * (sample[ebit_column] / sample[total_assets_column]) + 0.6 * (sample[market_equity_column] / sample[total_liabilities_column]) + 1.0 * (sample[sales_column] / sample[total_assets_column])
    sample["distress_zone"] = np.where(sample["altman_z"] < 1.81, "distress", np.where(sample["altman_z"] < 2.99, "grey", "safe"))
    latest = sample.iloc[-1]
    return _nonregression_result_payload(
        model_type="altman_z",
        model_label="Altman Z-Score",
        asset=asset,
        sample=sample[required_columns + ["altman_z", "distress_zone"]].copy(),
        narrative_lines=[f"Altman Z-score computed on {asset.title}.", f"Latest Z-score: {float(latest['altman_z']):.4f}.", f"Latest zone: {latest['distress_zone']}."],
        specification={
            "model_type": "altman_z",
            "model_family": "corporate_finance",
            "equation": "1.2*(WC/TA)+1.4*(RE/TA)+3.3*(EBIT/TA)+0.6*(MVE/TL)+1.0*(Sales/TA)",
            "input_columns": {"working_capital": working_capital_column, "retained_earnings": retained_earnings_column, "ebit": ebit_column, "market_equity": market_equity_column, "sales": sales_column, "total_assets": total_assets_column, "total_liabilities": total_liabilities_column},
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": required_columns,
            "manual_checklist": [
                "Recompute each ratio term using the listed accounting columns.",
                "Apply the standard Altman weights to reproduce altman_z.",
                "Check the distress-zone cutoff against 1.81 and 2.99.",
            ],
            "derived_columns": ["altman_z", "distress_zone"],
            "filters": ["Rows with missing inputs are dropped.", "Rows with nonpositive total assets or total liabilities are removed."],
        },
        metrics={"latest_score": float(latest["altman_z"]), "mean_score": float(sample["altman_z"].mean()), "distress_share": float((sample["distress_zone"] == "distress").mean())},
        tables={"score_preview": _frame_preview_rows(sample[required_columns + ["altman_z", "distress_zone"]].copy(), limit=10)},
    )


def run_dupont_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    net_income_column: str,
    revenue_column: str,
    total_assets_column: str,
    equity_column: str,
) -> dict[str, Any]:
    required_columns = [net_income_column, revenue_column, total_assets_column, equity_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    positive_mask = (sample[revenue_column] != 0) & (sample[total_assets_column] != 0) & (sample[equity_column] != 0)
    sample = sample.loc[positive_mask].copy()
    if sample.empty:
        raise ValueError("DuPont analysis requires nonzero revenue, total assets, and equity.")
    sample["profit_margin"] = sample[net_income_column] / sample[revenue_column]
    sample["asset_turnover"] = sample[revenue_column] / sample[total_assets_column]
    sample["equity_multiplier"] = sample[total_assets_column] / sample[equity_column]
    sample["roe_dupont"] = sample["profit_margin"] * sample["asset_turnover"] * sample["equity_multiplier"]
    latest = sample.iloc[-1]
    return _nonregression_result_payload(
        model_type="dupont",
        model_label="DuPont Analysis",
        asset=asset,
        sample=sample[required_columns + ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"]].copy(),
        narrative_lines=[f"DuPont analysis computed on {asset.title}.", f"Latest ROE decomposition: {float(latest['roe_dupont']):.4f}."],
        specification={
            "model_type": "dupont",
            "model_family": "corporate_finance",
            "equation": "ROE = (NetIncome/Revenue) * (Revenue/Assets) * (Assets/Equity)",
            "input_columns": {"net_income": net_income_column, "revenue": revenue_column, "total_assets": total_assets_column, "equity": equity_column},
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": required_columns,
            "manual_checklist": [
                "Compute profit margin, asset turnover, and equity multiplier from the listed accounting columns.",
                "Multiply the three terms to reproduce roe_dupont.",
                "Compare the latest-row decomposition with the preview table.",
            ],
            "derived_columns": ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"],
            "filters": ["Rows with missing inputs are dropped.", "Rows with zero revenue, assets, or equity are removed."],
        },
        metrics={"latest_roe": float(latest["roe_dupont"]), "mean_roe": float(sample["roe_dupont"].mean())},
        tables={"dupont_preview": _frame_preview_rows(sample[required_columns + ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"]].copy(), limit=10)},
    )


def run_risk_metric_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    return_column: str,
    time_column: str = "",
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
    ewma_lambda: float = 0.94,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [return_column] + ([time_column] if time_column else [])
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    sample[return_column] = _coerce_numeric_series(sample[return_column])
    sample = sample.dropna().copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    if len(sample) < 20:
        raise ValueError("Risk models require at least 20 return observations.")
    returns = sample[return_column].astype(float)
    alpha = 1.0 - float(confidence_level)
    if not (0 < alpha < 1):
        raise ValueError("Confidence level must lie between 0 and 1.")
    if holding_period_days < 1:
        raise ValueError("Holding period must be at least 1 day.")
    normal = NormalDist()

    if model_type == "historical_var":
        raw_var = float(returns.quantile(alpha))
        tail = returns.loc[returns <= raw_var]
        expected_shortfall = float(tail.mean()) if not tail.empty else raw_var
        label = "Historical VaR / ES"
        equation = "VaR_alpha = empirical quantile; ES_alpha = mean(returns <= VaR_alpha)"
        metrics = {"confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "var": -raw_var * math.sqrt(holding_period_days), "expected_shortfall": -expected_shortfall * math.sqrt(holding_period_days), "mean_return": float(returns.mean()), "volatility": float(returns.std())}
        derived_columns: list[str] = []
    elif model_type == "parametric_var":
        z_value = normal.inv_cdf(alpha)
        mean_return = float(returns.mean())
        volatility = float(returns.std())
        raw_var = mean_return + z_value * volatility
        es = mean_return - volatility * (math.exp(-(z_value**2) / 2.0) / math.sqrt(2.0 * math.pi)) / alpha
        label = "Parametric VaR / ES"
        equation = "VaR_alpha = mu + z_alpha*sigma under normality"
        metrics = {"confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "var": -raw_var * math.sqrt(holding_period_days), "expected_shortfall": -es * math.sqrt(holding_period_days), "mean_return": mean_return, "volatility": volatility}
        derived_columns = []
    else:
        normalized_lambda = float(ewma_lambda)
        if not (0 < normalized_lambda < 1):
            raise ValueError("EWMA lambda must lie between 0 and 1.")
        ewma_variance = float(np.var(returns))
        volatility_path = []
        for value in returns.astype(float):
            ewma_variance = normalized_lambda * ewma_variance + (1 - normalized_lambda) * float(value) ** 2
            volatility_path.append(math.sqrt(max(ewma_variance, 0.0)))
        label = "EWMA Volatility"
        equation = "sigma_t^2 = lambda*sigma_{t-1}^2 + (1-lambda)*r_{t-1}^2"
        sample = sample.copy()
        sample["ewma_volatility"] = volatility_path
        metrics = {"ewma_lambda": normalized_lambda, "latest_volatility": float(volatility_path[-1]), "mean_return": float(returns.mean()), "volatility": float(returns.std())}
        derived_columns = ["ewma_volatility"]

    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=sample,
        narrative_lines=[f"{label} run on {asset.title}.", f"Return series: {return_column}."],
        specification={"model_type": model_type, "model_family": "risk_management", "equation": equation, "return_column": return_column, "time_column": time_column, "confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "ewma_lambda": float(ewma_lambda)},
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": list(sample.columns),
            "manual_checklist": [
                "Download the sample asset and sort it by the listed time_column if one is provided.",
                "Recompute the return distribution statistics and the stated risk metric formula.",
                "Compare the reproduced VaR/ES or EWMA volatility against the metrics block.",
            ],
            "derived_columns": derived_columns,
            "filters": ["Rows with missing selected return values are dropped."],
        },
        metrics=metrics,
        tables={"series_preview": _frame_preview_rows(sample, limit=10)},
    )


def run_option_pricing_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    spot_column: str,
    strike_column: str,
    maturity_column: str,
    rate_column: str,
    volatility_column: str,
    option_type: str = "call",
    option_steps: int = 50,
) -> dict[str, Any]:
    required_columns = [spot_column, strike_column, maturity_column, rate_column, volatility_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if sample.empty:
        raise ValueError("No complete observations are available for option pricing.")
    records = []
    truncated = sample.head(500).copy()
    for _, row in truncated.iterrows():
        if model_type == "binomial_option":
            records.append(
                {
                    "price": _binomial_option_price(
                        spot=float(row[spot_column]),
                        strike=float(row[strike_column]),
                        maturity=float(row[maturity_column]),
                        rate=float(row[rate_column]),
                        volatility=float(row[volatility_column]),
                        steps=int(option_steps),
                        option_type=option_type,
                    )
                }
            )
        else:
            records.append(
                _black_scholes_price(
                    spot=float(row[spot_column]),
                    strike=float(row[strike_column]),
                    maturity=float(row[maturity_column]),
                    rate=float(row[rate_column]),
                    volatility=float(row[volatility_column]),
                    option_type=option_type,
                )
            )
    valuations = pd.DataFrame(records)
    preview = pd.concat([truncated.reset_index(drop=True), valuations], axis=1)
    latest = preview.iloc[-1]
    label = "Binomial Option Pricing" if model_type == "binomial_option" else "Black-Scholes"
    equation = "CRR binomial tree backward induction" if model_type == "binomial_option" else "Closed-form Black-Scholes-Merton pricing formula"
    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=preview,
        narrative_lines=[f"{label} run on {asset.title}.", f"Option type: {option_type}.", f"Latest price: {float(latest['price']):.4f}."],
        specification={
            "model_type": model_type,
            "model_family": "derivatives_pricing",
            "equation": equation,
            "input_columns": {"spot": spot_column, "strike": strike_column, "maturity": maturity_column, "rate": rate_column, "volatility": volatility_column},
            "option_type": option_type,
            "option_steps": int(option_steps),
        },
        audit_trail={
            "rows_used": int(len(preview)),
            "sample_columns": list(preview.columns),
            "manual_checklist": [
                "Download the sample asset and reproduce the pricing inputs row by row.",
                "Use the same option_type and option_steps when applicable.",
                "Compare the reproduced option values against the preview table and latest price metric.",
            ],
            "derived_columns": list(valuations.columns),
            "filters": ["Rows with missing pricing inputs are dropped.", "Only the first 500 complete rows are priced for stability."],
        },
        metrics={"latest_price": float(latest["price"]), "mean_price": float(preview["price"].mean())},
        tables={"valuation_preview": _frame_preview_rows(preview, limit=10)},
    )


def run_taylor_rule_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    inflation_gap_column: str,
    output_gap_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [inflation_gap_column, output_gap_column, *[column for column in (controls or []) if column]]
    payload = run_ols_analysis(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        dependent=dependent,
        independents=regressors,
        robust_covariance=robust_covariance,
    )
    payload["model_type"] = "taylor_rule"
    payload["model_label"] = "Taylor Rule"
    payload["model_family"] = "macro_finance_dsge"
    payload["inflation_gap_column"] = inflation_gap_column
    payload["output_gap_column"] = output_gap_column
    payload["specification"]["model_type"] = "taylor_rule"
    payload["specification"]["model_family"] = "macro_finance_dsge"
    payload["specification"]["equation"] = f"{dependent} ~ {inflation_gap_column} + {output_gap_column}" + (f" + {' + '.join(controls or [])}" if controls else "")
    payload["audit_trail"]["manual_checklist"].append("Interpret the inflation-gap and output-gap coefficients against the standard Taylor-rule benchmark.")
    return payload


def run_rbc_dsge_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    alpha: float = 0.33,
    beta: float = 0.99,
    delta: float = 0.025,
    productivity: float = 1.0,
    labor: float = 0.33,
    shock_persistence: float = 0.9,
    shock_size: float = 0.01,
    impulse_horizon: int = 12,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    if not (0 < alpha < 1 and 0 < beta < 1 and 0 < delta < 1 and productivity > 0 and labor > 0):
        raise ValueError("RBC/DSGE calibration requires alpha, beta, delta in (0,1) and positive productivity/labor.")
    capital_return = (1 / beta) - 1 + delta
    capital_per_labor = (alpha * productivity / capital_return) ** (1 / (1 - alpha))
    capital = capital_per_labor * labor
    output = productivity * (capital**alpha) * (labor ** (1 - alpha))
    investment = delta * capital
    consumption = output - investment
    impulse = []
    for step in range(int(impulse_horizon) + 1):
        technology = productivity * (1 + shock_size * (shock_persistence**step))
        shocked_output = technology * (capital**alpha) * (labor ** (1 - alpha))
        impulse.append({"step": step, "technology": float(technology), "output": float(shocked_output), "consumption": float(shocked_output - investment)})
    return _nonregression_result_payload(
        model_type="rbc_dsge",
        model_label="Toy RBC / DSGE",
        asset=asset,
        sample=None,
        narrative_lines=[f"Toy RBC/DSGE calibration run on {asset.title}.", f"Steady-state output: {float(output):.4f}.", f"Steady-state consumption: {float(consumption):.4f}."],
        specification={
            "model_type": "rbc_dsge",
            "model_family": "macro_finance_dsge",
            "equation": "Calibrated Cobb-Douglas RBC steady state with a productivity shock impulse path",
            "parameters": {"alpha": float(alpha), "beta": float(beta), "delta": float(delta), "productivity": float(productivity), "labor": float(labor), "shock_persistence": float(shock_persistence), "shock_size": float(shock_size), "impulse_horizon": int(impulse_horizon)},
        },
        audit_trail={
            "rows_used": 0,
            "sample_columns": [],
            "manual_checklist": [
                "Recompute the Euler-implied capital return and steady-state capital-labor ratio from the listed calibration parameters.",
                "Rebuild steady-state output, investment, and consumption under the Cobb-Douglas production function.",
                "Reproduce the impulse path using the same shock persistence and shock size.",
            ],
            "derived_columns": [],
            "filters": [],
        },
        metrics={"steady_state_capital": float(capital), "steady_state_output": float(output), "steady_state_consumption": float(consumption), "steady_state_investment": float(investment)},
        tables={"impulse_response": impulse},
    )


def run_portfolio_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    series_columns: list[str],
    risk_aversion: float = 3.0,
    long_only: bool = True,
) -> dict[str, Any]:
    series_columns = [column for column in series_columns if column]
    if len(series_columns) < 2:
        raise ValueError("Portfolio allocation requires at least two return series.")
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in series_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[series_columns].copy()
    for column in series_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    returns = sample.dropna().astype(float)
    if len(returns) < 20:
        raise ValueError("Portfolio models require at least 20 complete return observations.")
    mean_returns = returns.mean().to_numpy()
    covariance = returns.cov().to_numpy()
    inverse_covariance = np.linalg.pinv(covariance)
    ones = np.ones(len(series_columns))
    if model_type == "minimum_variance":
        weights = inverse_covariance @ ones
        label = "Minimum Variance Portfolio"
    elif model_type == "risk_parity":
        weights = _risk_parity_weights(covariance)
        label = "Risk Parity Portfolio"
    else:
        weights = inverse_covariance @ mean_returns / max(float(risk_aversion), 1e-6)
        label = "Mean-Variance Portfolio"
    if long_only:
        weights = np.clip(weights, 0.0, None)
    if np.allclose(weights.sum(), 0.0):
        weights = np.full(len(series_columns), 1.0 / len(series_columns))
    else:
        weights = weights / weights.sum()
    portfolio_return = float(mean_returns @ weights)
    portfolio_volatility = float(math.sqrt(max(weights @ covariance @ weights, 0.0)))
    weights_table = [{"asset_column": series_columns[index], "weight": float(weights[index]), "mean_return": float(mean_returns[index])} for index in range(len(series_columns))]
    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=returns,
        narrative_lines=[f"{label} run on {asset.title}.", f"Assets: {', '.join(series_columns)}.", f"Expected portfolio return: {portfolio_return:.6f}.", f"Portfolio volatility: {portfolio_volatility:.6f}."],
        specification={"model_type": model_type, "model_family": "portfolio_allocation", "series_columns": series_columns, "risk_aversion": float(risk_aversion), "long_only": bool(long_only)},
        audit_trail={
            "rows_used": int(len(returns)),
            "sample_columns": series_columns,
            "manual_checklist": [
                "Recompute the sample mean vector and covariance matrix from the listed return columns.",
                "Apply the same allocation rule and long_only setting to reproduce the portfolio weights.",
                "Check the resulting portfolio return and volatility against the metrics block.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing return values across any selected asset column are dropped."],
        },
        metrics={"expected_return": portfolio_return, "volatility": portfolio_volatility},
        tables={"weights": weights_table},
    )


def run_asset_pricing_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    asset_return_column: str,
    market_column: str,
    risk_free_column: str = "",
    smb_column: str = "",
    hml_column: str = "",
    robust_covariance: bool = True,
) -> dict[str, Any]:
    required_columns = [asset_return_column, market_column]
    if risk_free_column:
        required_columns.append(risk_free_column)
    if model_type == "fama_french_3":
        required_columns.extend([smb_column, hml_column])
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    sample["asset_excess"] = sample[asset_return_column] - sample[risk_free_column] if risk_free_column else sample[asset_return_column]
    sample["market_excess"] = sample[market_column] - sample[risk_free_column] if risk_free_column else sample[market_column]
    regressors = ["market_excess"]
    if model_type == "fama_french_3":
        regressors.extend([smb_column, hml_column])
    fitted = _fit_ols(sample[["asset_excess", *regressors]].copy(), "asset_excess", regressors, robust_covariance=robust_covariance)
    payload = _model_result_payload(
        model_type=model_type,
        model_label="Fama-French 3-Factor" if model_type == "fama_french_3" else "CAPM",
        asset=asset,
        dependent="asset_excess",
        regressors=regressors,
        sample=sample[["asset_excess", *regressors]].copy(),
        result=fitted,
        narrative_lines=[
            f"{'Fama-French 3-Factor' if model_type == 'fama_french_3' else 'CAPM'} run on {asset.title}.",
            f"Asset return column: {asset_return_column}.",
            f"Market factor column: {market_column}.",
        ],
        extra={
            "model_family": "asset_pricing",
            "asset_return_column": asset_return_column,
            "market_column": market_column,
            "risk_free_column": risk_free_column,
            "smb_column": smb_column,
            "hml_column": hml_column,
            "audit_trail": {
                "derived_columns": ["asset_excess", "market_excess"],
                "filters": ["Rows with missing factor or return inputs are dropped."],
            },
        },
    )
    payload["specification"]["equation"] = "asset_excess ~ " + " + ".join(regressors)
    return payload


def run_logit_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_binary_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted = _fit_binary_response(sample, dependent, regressors, model_kind="logit", robust_covariance=robust_covariance)
    summary_lines = [
        f"Logit run on {asset.title}.",
        f"Binary outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="logit",
        model_label="Logit",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing binary outcome or selected regressors are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Logit summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["logit", "dataset", "econometrics"],
        metadata=payload,
    )
    return payload


def run_probit_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_binary_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted = _fit_binary_response(sample, dependent, regressors, model_kind="probit", robust_covariance=robust_covariance)
    summary_lines = [
        f"Probit run on {asset.title}.",
        f"Binary outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="probit",
        model_label="Probit",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing binary outcome or selected regressors are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Probit summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["probit", "dataset", "econometrics"],
        metadata=payload,
    )
    return payload


def run_fixed_effects_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, entity_column, *regressors]
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()

    if not regressors:
        raise ValueError("Fixed effects models require at least one explanatory variable.")

    entity_dummies = pd.get_dummies(sample[entity_column], prefix=f"fe_{entity_column}", drop_first=True, dtype=float)
    design_parts = [sample[regressors].astype(float), entity_dummies]
    fe_labels = [entity_column]
    if include_time_effects and time_column:
        time_dummies = pd.get_dummies(sample[time_column], prefix=f"fe_{time_column}", drop_first=True, dtype=float)
        design_parts.append(time_dummies)
        fe_labels.append(time_column)
    design = pd.concat(design_parts, axis=1)
    fitted = _fit_ols(pd.concat([sample[[dependent]], design], axis=1), dependent, list(design.columns), robust_covariance=robust_covariance)
    summary_lines = [
        f"Fixed effects model run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Slope regressors: {', '.join(regressors)}.",
        f"Fixed effects: {', '.join(fe_labels)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="fixed_effects",
        model_label="Fixed Effects",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, *regressors, entity_column] + ([time_column] if include_time_effects and time_column else [])].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "entity_column": entity_column,
            "time_column": time_column if include_time_effects else "",
            "include_time_effects": include_time_effects,
            "entity_count": int(sample[entity_column].nunique()),
            "time_count": int(sample[time_column].nunique()) if include_time_effects and time_column else 0,
            "audit_trail": {
                "derived_columns": list(design.columns),
                "filters": ["Rows with missing outcome, slope regressors, entity ids, or time ids are dropped."],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Fixed effects summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["fixed_effects", "panel", "econometrics"],
        metadata=payload,
    )
    return payload


def run_iv_2sls_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    endogenous_column: str,
    instrument_columns: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    exogenous = [column for column in [*(independents or []), *(controls or [])] if column]
    instruments = [column for column in (instrument_columns or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, endogenous_column, *exogenous, *instruments]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted, covariance_type = _fit_iv_2sls(
        sample,
        dependent,
        exogenous=exogenous,
        endogenous=endogenous_column,
        instruments=instruments,
        robust_covariance=robust_covariance,
    )
    summary_lines = [
        f"IV-2SLS run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Endogenous regressor: {endogenous_column}.",
        f"Instruments: {', '.join(instruments)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="iv_2sls",
        model_label="IV-2SLS",
        asset=asset,
        dependent=dependent,
        regressors=[*exogenous, endogenous_column],
        sample=sample[[dependent, *exogenous, endogenous_column, *instruments]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "endogenous_column": endogenous_column,
            "instrument_columns": instruments,
            "exogenous_columns": exogenous,
            "covariance_type": covariance_type,
            "covariance_note": "IV-2SLS uses conventional covariance when robust covariance is unavailable in the current backend."
            if robust_covariance and covariance_type != "HC1"
            else "",
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent, endogenous regressor, exogenous regressors, or instruments are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"IV-2SLS summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["iv_2sls", "instrumental_variables", "econometrics"],
        metadata=payload,
    )
    return payload


def _infer_model_family(model_type: str) -> str:
    mapping = {
        "ols": "econometrics_baseline",
        "ppml": "econometrics_baseline",
        "logit": "econometrics_baseline",
        "probit": "econometrics_baseline",
        "did": "econometrics_baseline",
        "event_study": "econometrics_baseline",
        "rdd": "econometrics_baseline",
        "fixed_effects": "econometrics_baseline",
        "gravity": "econometrics_baseline",
        "iv_2sls": "econometrics_baseline",
        "panel_iv": "econometrics_baseline",
        "arima": "time_series_finance",
        "var": "time_series_finance",
        "altman_z": "corporate_finance",
        "dupont": "corporate_finance",
        "historical_var": "risk_management",
        "parametric_var": "risk_management",
        "ewma_volatility": "risk_management",
        "black_scholes": "derivatives_pricing",
        "binomial_option": "derivatives_pricing",
        "taylor_rule": "macro_finance_dsge",
        "rbc_dsge": "macro_finance_dsge",
        "mean_variance": "portfolio_allocation",
        "minimum_variance": "portfolio_allocation",
        "risk_parity": "portfolio_allocation",
        "capm": "asset_pricing",
        "fama_french_3": "asset_pricing",
    }
    return mapping.get(model_type, "econometrics_baseline")


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
    series_columns: list[str] | None = None,
    treatment_column: str = "",
    post_column: str = "",
    event_time_column: str = "",
    lead_window: int = 4,
    lag_window: int = 4,
    omitted_period: int = -1,
    origin_mass_column: str = "",
    destination_mass_column: str = "",
    distance_column: str = "",
    running_column: str = "",
    cutoff: float = 0.0,
    bandwidth: float = 0.0,
    polynomial_order: int = 1,
    treat_above_cutoff: bool = True,
    entity_column: str = "",
    time_column: str = "",
    include_time_effects: bool = False,
    endogenous_column: str = "",
    instrument_columns: list[str] | None = None,
    market_column: str = "",
    risk_free_column: str = "",
    smb_column: str = "",
    hml_column: str = "",
    spot_column: str = "",
    strike_column: str = "",
    maturity_column: str = "",
    rate_column: str = "",
    volatility_column: str = "",
    working_capital_column: str = "",
    retained_earnings_column: str = "",
    ebit_column: str = "",
    market_equity_column: str = "",
    total_assets_column: str = "",
    total_liabilities_column: str = "",
    sales_column: str = "",
    net_income_column: str = "",
    revenue_column: str = "",
    equity_column: str = "",
    inflation_gap_column: str = "",
    output_gap_column: str = "",
    arima_p: int = 1,
    arima_d: int = 0,
    arima_q: int = 0,
    forecast_steps: int = 5,
    var_lags: int = 1,
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
    ewma_lambda: float = 0.94,
    option_type: str = "call",
    option_steps: int = 50,
    risk_aversion: float = 3.0,
    long_only: bool = True,
    dsge_alpha: float = 0.33,
    dsge_beta: float = 0.99,
    dsge_delta: float = 0.025,
    dsge_productivity: float = 1.0,
    dsge_labor: float = 0.33,
    dsge_shock_persistence: float = 0.9,
    dsge_shock_size: float = 0.01,
    dsge_impulse_horizon: int = 12,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    normalized_model = model_type.strip().lower()

    def attach(payload: dict[str, Any]) -> dict[str, Any]:
        family = _infer_model_family(normalized_model)
        payload["workflow_type"] = "model"
        payload.setdefault("model_family", family)
        specification = payload.get("specification")
        if isinstance(specification, dict):
            specification.setdefault("model_family", family)
        if not payload.get("result_record_id"):
            asset_title = ((payload.get("asset") or {}).get("title") or "dataset").strip()
            record = create_knowledge_record(
                db,
                user=user,
                workspace=workspace,
                title=f"{payload.get('model_label', 'Model')} summary for {asset_title}",
                content="\n".join(payload.get("narrative") or [f"{payload.get('model_label', 'Model')} completed."]),
                tags=[normalized_model, family, "dataset"],
                metadata=payload,
            )
            payload.setdefault("result_record_id", record.id)
            payload.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
        return payload

    if normalized_model == "ols":
        return attach(
            run_ols_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "logit":
        return attach(
            run_logit_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "probit":
        return attach(
            run_probit_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "ppml":
        return attach(
            run_ppml_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "arima":
        return attach(
            run_arima_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                time_column=time_column,
                arima_order=(int(arima_p), int(arima_d), int(arima_q)),
                forecast_steps=int(forecast_steps),
            )
        )
    if normalized_model == "var":
        return attach(
            run_var_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                series_columns=series_columns or [],
                time_column=time_column,
                lags=int(var_lags),
                forecast_steps=int(forecast_steps),
            )
        )
    if normalized_model == "did":
        return attach(
            run_did_analysis(
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
        )
    if normalized_model == "event_study":
        return attach(
            run_event_study_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                treatment_column=treatment_column,
                event_time_column=event_time_column,
                controls=controls or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                lead_window=lead_window,
                lag_window=lag_window,
                omitted_period=omitted_period,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "fixed_effects":
        return attach(
            run_fixed_effects_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "gravity":
        return attach(
            run_gravity_analysis(
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
        )
    if normalized_model == "rdd":
        return attach(
            run_rdd_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                running_column=running_column,
                controls=controls or [],
                cutoff=cutoff,
                bandwidth=bandwidth,
                polynomial_order=polynomial_order,
                treat_above_cutoff=treat_above_cutoff,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model in {"historical_var", "parametric_var", "ewma_volatility"}:
        return attach(
            run_risk_metric_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                return_column=dependent,
                time_column=time_column,
                confidence_level=confidence_level,
                holding_period_days=holding_period_days,
                ewma_lambda=ewma_lambda,
            )
        )
    if normalized_model == "iv_2sls":
        return attach(
            run_iv_2sls_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                endogenous_column=endogenous_column,
                instrument_columns=instrument_columns or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "panel_iv":
        return attach(
            run_panel_iv_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                endogenous_column=endogenous_column,
                instrument_columns=instrument_columns or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model in {"black_scholes", "binomial_option"}:
        return attach(
            run_option_pricing_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                spot_column=spot_column,
                strike_column=strike_column,
                maturity_column=maturity_column,
                rate_column=rate_column,
                volatility_column=volatility_column,
                option_type=option_type,
                option_steps=option_steps,
            )
        )
    if normalized_model == "taylor_rule":
        return attach(
            run_taylor_rule_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                inflation_gap_column=inflation_gap_column,
                output_gap_column=output_gap_column,
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "rbc_dsge":
        return attach(
            run_rbc_dsge_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                alpha=dsge_alpha,
                beta=dsge_beta,
                delta=dsge_delta,
                productivity=dsge_productivity,
                labor=dsge_labor,
                shock_persistence=dsge_shock_persistence,
                shock_size=dsge_shock_size,
                impulse_horizon=dsge_impulse_horizon,
            )
        )
    if normalized_model in {"mean_variance", "minimum_variance", "risk_parity"}:
        return attach(
            run_portfolio_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                series_columns=series_columns or [],
                risk_aversion=risk_aversion,
                long_only=long_only,
            )
        )
    if normalized_model in {"capm", "fama_french_3"}:
        return attach(
            run_asset_pricing_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                asset_return_column=dependent,
                market_column=market_column,
                risk_free_column=risk_free_column,
                smb_column=smb_column,
                hml_column=hml_column,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "altman_z":
        return attach(
            run_altman_z_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                working_capital_column=working_capital_column,
                retained_earnings_column=retained_earnings_column,
                ebit_column=ebit_column,
                market_equity_column=market_equity_column,
                sales_column=sales_column,
                total_assets_column=total_assets_column,
                total_liabilities_column=total_liabilities_column,
            )
        )
    if normalized_model == "dupont":
        return attach(
            run_dupont_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                net_income_column=net_income_column,
                revenue_column=revenue_column,
                total_assets_column=total_assets_column,
                equity_column=equity_column,
            )
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
        "workflow_type": "data_processing",
        "processing_family": "visualization",
        "asset": serialize_asset(plot_asset),
        "chart_type": normalized_chart_type or "line",
        "title": title.strip() or summary,
        "summary": summary,
        "download_url": f"/api/assets/{plot_asset.id}/download",
        "plot_specification": {
            "chart_type": normalized_chart_type or "line",
            "x_column": x_column,
            "y_columns": y_columns,
            "group_column": group_column,
            "title": title.strip() or summary,
            "max_points": int(max_points),
        },
        "audit_trail": {
            "source_asset_id": asset.id,
            "source_asset_title": asset.title,
            "plot_asset_id": plot_asset.id,
            "download_url": f"/api/assets/{plot_asset.id}/download",
            "manual_checklist": [
                "Download the plotted image and the source sample asset.",
                "Recreate the chart using the listed chart_type, x_column, y_columns, and group_column.",
                "Compare the visible point counts or grouped bars against the summary and source sample.",
            ],
        },
    }
