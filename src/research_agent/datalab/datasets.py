from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Callable

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype
from sqlalchemy.orm import Session

from research_agent.asset_storage import load_asset_bytes
from research_agent.config import Settings
from research_agent.entities import DataAsset, User, Workspace
from research_agent.utils import slugify

DATASET_KINDS = {"dataset_csv", "dataset_excel", "dataset_json"}
MAX_DATASET_INPUT_BYTES = 25 * 1024 * 1024
MAX_DATASET_ROWS = 250_000
MAX_DATASET_COLUMNS = 500
MAX_DATASET_CELLS = 5_000_000
MAX_DATASET_MEMORY_BYTES = 256 * 1024 * 1024
MAX_DATASET_MEMORY_AMPLIFICATION = 12
MIN_DATASET_MEMORY_AMPLIFICATION_BYTES = 32 * 1024 * 1024


class DatasetLimitError(ValueError):
    pass


def serialize_preview_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def frame_preview_rows(frame: pd.DataFrame, *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {column: serialize_preview_value(value) for column, value in row.items()}
        for row in frame.head(limit).to_dict(orient="records")
    ]


def normalize_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in {"", "nan", "none", "nat", "null"}:
            return pd.NA
        return cleaned
    return value


def unique_clean_columns(columns: list[Any]) -> tuple[list[str], dict[str, str]]:
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
    cleaned_columns, source_map = unique_clean_columns(list(prepared.columns))
    prepared.columns = cleaned_columns
    duplicate_rows = int(prepared.duplicated().sum())
    if drop_duplicates:
        prepared = prepared.drop_duplicates().copy()
    for column in prepared.columns:
        prepared[column] = prepared[column].map(normalize_scalar)
    return prepared, {
        "source_columns": source_map,
        "duplicate_rows_detected": duplicate_rows,
        "rows_after_standardization": int(len(prepared)),
        "columns_after_standardization": list(prepared.columns),
    }


def infer_column_role(series: pd.Series) -> str:
    if is_datetime64_any_dtype(series):
        return "date"
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    if is_numeric_dtype(non_null):
        return "binary" if int(non_null.nunique(dropna=True)) <= 2 else "numeric"
    numeric_candidate = pd.to_numeric(non_null, errors="coerce")
    if len(non_null) and float(numeric_candidate.notna().mean()) >= 0.9:
        return "binary" if int(numeric_candidate.dropna().nunique()) <= 2 else "numeric"
    text_values = non_null.astype(str).str.strip()
    lowered = text_values.str.lower()
    binary_tokens = {
        "0",
        "1",
        "true",
        "false",
        "yes",
        "no",
        "y",
        "n",
        "treated",
        "control",
        "pre",
        "post",
    }
    if text_values.nunique() <= 2 or set(lowered.unique()).issubset(binary_tokens):
        return "binary"
    date_candidate = pd.to_datetime(text_values, errors="coerce", format="mixed")
    if len(text_values) and float(date_candidate.notna().mean()) >= 0.8:
        return "date"
    unique_count = int(text_values.nunique())
    return "categorical" if unique_count <= min(20, max(3, len(text_values) // 2)) else "text"


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def column_profile(frame: pd.DataFrame, source_map: dict[str, str], column: str) -> dict[str, Any]:
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
        "sample_values": [serialize_preview_value(value) for value in non_null.head(4).tolist()],
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
            profile.update({"min": date_series.min().isoformat(), "max": date_series.max().isoformat()})
    return profile


def _frame_memory_usage_bytes(frame: pd.DataFrame) -> int:
    try:
        return int(frame.memory_usage(index=True, deep=True).sum())
    except Exception:
        return int(frame.memory_usage(index=True).sum())


def _enforce_dataset_limits(frame: pd.DataFrame, *, raw_size_bytes: int) -> pd.DataFrame:
    row_count = int(frame.shape[0])
    column_count = int(frame.shape[1])
    cell_count = row_count * column_count
    memory_bytes = _frame_memory_usage_bytes(frame)
    if raw_size_bytes > MAX_DATASET_INPUT_BYTES:
        raise DatasetLimitError(
            f"Dataset file is {raw_size_bytes:,} bytes; the Data Lab limit is {MAX_DATASET_INPUT_BYTES:,} bytes."
        )
    if row_count > MAX_DATASET_ROWS:
        raise DatasetLimitError(f"Dataset has {row_count:,} rows; the Data Lab limit is {MAX_DATASET_ROWS:,} rows.")
    if column_count > MAX_DATASET_COLUMNS:
        raise DatasetLimitError(
            f"Dataset has {column_count:,} columns; the Data Lab limit is {MAX_DATASET_COLUMNS:,} columns."
        )
    if cell_count > MAX_DATASET_CELLS:
        raise DatasetLimitError(
            f"Dataset has {cell_count:,} cells; the Data Lab limit is {MAX_DATASET_CELLS:,} cells."
        )
    if memory_bytes > MAX_DATASET_MEMORY_BYTES:
        raise DatasetLimitError(
            f"Dataset expands to about {memory_bytes:,} bytes in memory; the Data Lab limit is {MAX_DATASET_MEMORY_BYTES:,} bytes."
        )
    if (
        raw_size_bytes > 0
        and memory_bytes > MIN_DATASET_MEMORY_AMPLIFICATION_BYTES
        and memory_bytes > raw_size_bytes * MAX_DATASET_MEMORY_AMPLIFICATION
    ):
        raise DatasetLimitError(
            "Dataset expands too much during parsing; reduce wide text columns or upload a smaller structured sample."
        )
    return frame


def load_dataset_frame(settings: Settings, asset: DataAsset) -> pd.DataFrame:
    raw_bytes = load_asset_bytes(settings, asset.file_path)
    raw_size_bytes = len(raw_bytes)
    if raw_size_bytes > MAX_DATASET_INPUT_BYTES:
        raise DatasetLimitError(
            f"Dataset file is {raw_size_bytes:,} bytes; the Data Lab limit is {MAX_DATASET_INPUT_BYTES:,} bytes."
        )
    if asset.kind == "dataset_csv":
        frame = pd.read_csv(BytesIO(raw_bytes), nrows=MAX_DATASET_ROWS + 1)
    elif asset.kind == "dataset_excel":
        frame = pd.read_excel(BytesIO(raw_bytes), nrows=MAX_DATASET_ROWS + 1)
    elif asset.kind == "dataset_json":
        frame = pd.DataFrame(json.loads(raw_bytes.decode("utf-8")))
    else:
        raise ValueError("This asset is not a structured dataset.")
    return _enforce_dataset_limits(frame, raw_size_bytes=raw_size_bytes)


def analysis_asset_or_raise(db: Session, *, user: User, workspace: Workspace, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")
    if asset.kind not in DATASET_KINDS:
        raise ValueError("This asset is not a structured dataset.")
    return asset


def load_analysis_frame(
    settings: Settings,
    asset: DataAsset,
    *,
    drop_duplicates: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return normalize_dataset_frame(load_dataset_frame(settings, asset), drop_duplicates=drop_duplicates)


def profile_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    serialize_asset: Callable[[DataAsset], dict[str, Any]],
) -> dict[str, Any]:
    asset = analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, meta = load_analysis_frame(settings, asset, drop_duplicates=False)
    column_profiles = [column_profile(frame, meta["source_columns"], column) for column in frame.columns]
    role_map: dict[str, list[str]] = {"numeric": [], "binary": [], "date": [], "categorical": [], "text": [], "empty": []}
    for item in column_profiles:
        role_map.setdefault(item["role"], []).append(item["name"])
    suggested_models = ["ols"]
    if role_map["binary"] and role_map["numeric"]:
        suggested_models.extend(["logit", "probit"])
    if role_map["numeric"]:
        suggested_models.extend(
            [
                "ppml",
                "rdd",
                "historical_var",
                "parametric_var",
                "ewma_volatility",
                "capm",
                "mean_variance",
                "minimum_variance",
                "risk_parity",
            ]
        )
    if role_map["numeric"] and len(role_map["binary"]) >= 2:
        suggested_models.extend(["did", "event_study"])
    if len(role_map["numeric"]) >= 3 and (role_map["categorical"] or role_map["text"] or role_map["date"]):
        suggested_models.extend(["fixed_effects", "arima", "var", "taylor_rule"])
    if len(role_map["numeric"]) >= 4:
        suggested_models.extend(
            [
                "gravity",
                "iv_2sls",
                "panel_iv",
                "fama_french_3",
                "black_scholes",
                "binomial_option",
                "altman_z",
                "dupont",
            ]
        )
    suggested_models.append("rbc_dsge")
    return {
        "asset": serialize_asset(asset),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows_detected": int(meta["duplicate_rows_detected"]),
        "column_profiles": column_profiles,
        "column_roles": role_map,
        "preview_rows": frame_preview_rows(frame),
        "suggested_models": list(dict.fromkeys(suggested_models)),
        "source_columns": meta["source_columns"],
    }
