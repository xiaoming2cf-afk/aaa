from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sqlalchemy.orm import Session

from research_agent.config import Settings
from research_agent.entities import DataAsset, User, Workspace

from .datasets import analysis_asset_or_raise, frame_preview_rows, load_analysis_frame

PREPARATION_DEFAULTS: dict[str, Any] = {
    "include_columns": None,
    "required_columns": None,
    "numeric_columns": None,
    "binary_columns": None,
    "date_columns": None,
    "impute_columns": None,
    "impute_method": "none",
    "winsorize_columns": None,
    "winsor_lower_quantile": 0.01,
    "winsor_upper_quantile": 0.99,
    "log_transform_columns": None,
    "standardize_columns": None,
    "minmax_scale_columns": None,
    "outlier_columns": None,
    "outlier_method": "none",
    "outlier_threshold": 1.5,
    "sort_column": "",
    "time_group_column": "",
    "difference_columns": None,
    "return_columns": None,
    "return_method": "simple",
    "lag_columns": None,
    "lag_periods": 1,
    "lead_columns": None,
    "lead_periods": 1,
    "rolling_mean_columns": None,
    "rolling_volatility_columns": None,
    "rolling_window": 5,
    "drop_duplicates": True,
    "drop_missing_required": True,
}


def normalize_preparation_options(values: dict[str, Any]) -> dict[str, Any]:
    return {key: values.get(key, default) for key, default in PREPARATION_DEFAULTS.items()}


def prepare_dataset_frame(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    prepare_sample: Callable[..., tuple[pd.DataFrame, dict[str, Any]]],
    **options: Any,
) -> tuple[DataAsset, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    asset = analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = load_analysis_frame(settings, asset, drop_duplicates=False)
    prepared_frame, summary = prepare_sample(frame, **normalize_preparation_options(options))
    return asset, frame, prepared_frame, summary


def preparation_transformed_columns(summary: dict[str, Any]) -> list[str]:
    transformed: set[str] = set()
    for key in ("numeric_columns", "binary_columns", "date_columns", "outlier_columns"):
        transformed.update(str(column) for column in summary.get(key) or [] if column)
    transformed.update(str(column) for column in (summary.get("imputed_columns") or {}).keys())
    transformed.update(str(column) for column in (summary.get("winsorized_columns") or {}).keys())
    transform_groups = summary.get("transformed_columns") or {}
    if isinstance(transform_groups, dict):
        for values in transform_groups.values():
            transformed.update(str(column) for column in values or [] if column)
    return sorted(transformed)


def prepare_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    workflow_group: str = "sample_preparation",
    template_id: str = "",
    template_name: str = "",
    variant_label: str = "",
    variant_spec: dict[str, Any] | None = None,
    effective_specification: dict[str, Any] | None = None,
    prepare_sample: Callable[..., tuple[pd.DataFrame, dict[str, Any]]],
    save_asset: Callable[..., DataAsset],
    serialize_asset: Callable[[DataAsset], dict[str, Any]],
    **options: Any,
) -> dict[str, Any]:
    normalized_options = normalize_preparation_options(options)
    asset, _, prepared_frame, summary = prepare_dataset_frame(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        prepare_sample=prepare_sample,
        **normalized_options,
    )
    if prepared_frame.empty:
        raise ValueError("Preparation would produce an empty output sample.")
    prepared_asset = save_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-prepared.csv",
        content=prepared_frame.to_csv(index=False).encode("utf-8"),
        content_type="text/csv",
        description=f"Prepared analysis sample derived from {asset.title}",
    )
    audit_trail = {
        "source_asset_id": asset.id,
        "source_asset_title": asset.title,
        "prepared_asset_id": prepared_asset.id,
        "prepared_download_url": f"/api/assets/{prepared_asset.id}/download",
        "template_id": template_id,
        "template_name": template_name,
        "variant_label": variant_label,
        "variant_spec": dict(variant_spec or {}) if isinstance(variant_spec, dict) else {},
        "effective_specification": dict(effective_specification or {}) if isinstance(effective_specification, dict) else {},
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
            "drop_duplicates": normalized_options["drop_duplicates"],
            "drop_missing_required": normalized_options["drop_missing_required"],
            "workflow_group": workflow_group or "sample_preparation",
        },
    }
    processing_result = {
        "workflow_type": "data_processing",
        "processing_family": workflow_group or "sample_preparation",
        "template_id": template_id,
        "template_name": template_name,
        "variant_label": variant_label,
        "variant_spec": dict(variant_spec or {}) if isinstance(variant_spec, dict) else {},
        "effective_specification": dict(effective_specification or {}) if isinstance(effective_specification, dict) else {},
        "asset": serialize_asset(prepared_asset),
        "summary": summary,
        "preview_rows": frame_preview_rows(prepared_frame),
        "audit_trail": audit_trail,
        "result_detail_path": f"/data-lab/results/processing/{prepared_asset.id}",
        "detail_path": f"/data-lab/results/processing/{prepared_asset.id}",
        "status": "ready",
        "reason": "Processing result is ready for review.",
        "next_action": "open_detail",
        "template_source": template_name or template_id,
        "variant_source": variant_label or ("custom" if isinstance(variant_spec, dict) and variant_spec else ""),
    }
    prepared_asset.metadata_json = {
        **prepared_asset.metadata_json,
        "preparation_summary": summary,
        "source_asset_id": asset.id,
        "processing_result": processing_result,
    }
    db.flush()
    return processing_result
