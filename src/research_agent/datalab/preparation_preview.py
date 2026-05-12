from __future__ import annotations

from typing import Any


def summarize_preparation_preview(
    *,
    source_asset_id: str,
    workflow_group: str,
    input_rows: int,
    output_rows: int,
    input_columns: list[str],
    output_columns: list[str],
    missing_before_by_column: dict[str, int],
    missing_after_by_column: dict[str, int],
    warnings: list[str],
    preview_rows: list[dict[str, Any]],
    specification_summary: dict[str, Any],
) -> dict[str, Any]:
    input_set = set(input_columns)
    output_set = set(output_columns)
    return {
        "source_asset_id": source_asset_id,
        "workflow_group": workflow_group,
        "input_rows": input_rows,
        "output_rows": output_rows,
        "dropped_rows": max(0, input_rows - output_rows),
        "input_columns": input_columns,
        "output_columns": output_columns,
        "added_columns": [column for column in output_columns if column not in input_set],
        "removed_columns": [column for column in input_columns if column not in output_set],
        "transformed_columns": sorted(column for column in input_set & output_set if missing_before_by_column.get(column) != missing_after_by_column.get(column)),
        "missing_before_by_column": missing_before_by_column,
        "missing_after_by_column": missing_after_by_column,
        "warnings": warnings,
        "preview_rows": preview_rows[:10],
        "specification_summary": specification_summary,
    }
