from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
import numpy as np
import pandas as pd
import requests
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


def clean_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
) -> dict[str, Any]:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")

    frame = load_dataset_frame(settings, asset)
    original_rows = len(frame)
    original_columns = list(frame.columns)

    frame.columns = [slugify(str(column), max_length=48).replace("-", "_") for column in frame.columns]
    frame = frame.drop_duplicates().copy()

    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].astype(str).str.strip()
            frame.loc[frame[column].isin({"", "nan", "None", "NaT"}), column] = pd.NA

    summary = {
        "original_rows": original_rows,
        "cleaned_rows": int(len(frame)),
        "dropped_rows": int(original_rows - len(frame)),
        "columns_before": original_columns,
        "columns_after": list(frame.columns),
        "missing_by_column": {
            column: int(value) for column, value in frame.isna().sum().to_dict().items()
        },
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
) -> dict[str, Any]:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")
    frame = load_dataset_frame(settings, asset)

    required_columns = [dependent, *independents]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    numeric = frame[required_columns].apply(pd.to_numeric, errors="coerce").dropna()
    if len(numeric) < max(8, len(independents) + 2):
        raise ValueError("Not enough complete numeric observations for OLS analysis.")

    y = numeric[dependent].to_numpy(dtype=float)
    x = numeric[independents].to_numpy(dtype=float)
    intercept = np.ones((len(numeric), 1))
    design = np.concatenate([intercept, x], axis=1)
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    predictions = design @ coefficients
    residuals = y - predictions
    sse = float(np.sum(residuals**2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - sse / sst if sst else 0.0

    names = ["intercept", *independents]
    coefficient_map = {name: float(value) for name, value in zip(names, coefficients.tolist(), strict=False)}
    summary_lines = [
        f"OLS run on asset {asset.title}",
        f"Dependent variable: {dependent}",
        f"Independent variables: {', '.join(independents)}",
        f"Observations: {len(numeric)}",
        f"R-squared: {r_squared:.4f}",
    ]
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"OLS summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["ols", "dataset", "economics"],
        metadata={
            "asset_id": asset.id,
            "dependent": dependent,
            "independents": independents,
            "coefficients": coefficient_map,
            "observations": int(len(numeric)),
            "r_squared": r_squared,
        },
    )
    return {
        "asset": serialize_asset(asset),
        "dependent": dependent,
        "independents": independents,
        "observations": int(len(numeric)),
        "r_squared": r_squared,
        "coefficients": coefficient_map,
        "residual_sum_squares": sse,
    }
