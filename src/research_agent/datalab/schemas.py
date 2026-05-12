from __future__ import annotations

from typing import Any, Literal, TypedDict


PreflightStatus = Literal["ok", "warning", "blocked"]


class PreflightCheck(TypedDict, total=False):
    key: str
    label: str
    status: PreflightStatus
    severity: Literal["info", "warning", "error"]
    detail: str


class ReproducibilityManifest(TypedDict, total=False):
    version: str
    result_type: Literal["processing", "model"]
    result_id: str
    workspace_id: str
    source_asset_id: str
    source_asset_title: str
    source_asset_kind: str
    workflow_type: str
    workflow_group: str
    model_type: str
    selected_columns: list[str]
    variable_roles: dict[str, Any]
    specification: dict[str, Any]
    created_at: str
    generated_asset_ids: list[str]
    warnings: list[str]
