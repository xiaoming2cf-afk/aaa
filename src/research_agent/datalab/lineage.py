from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested_source_asset_id(row: dict[str, Any]) -> str:
    for key in ("request_json", "request"):
        request_payload = _dict_value(row.get(key))
        asset_id = str(request_payload.get("asset_id") or "").strip()
        if asset_id:
            return asset_id
    metadata = _dict_value(row.get("metadata"))
    for key in ("source_asset_id", "asset_id"):
        asset_id = str(metadata.get(key) or "").strip()
        if asset_id:
            return asset_id
    return ""


def _lineage_source(row: dict[str, Any], bucket_name: str) -> tuple[str, str]:
    source_asset_id = str(row.get("source_asset_id") or "").strip()
    if source_asset_id:
        return source_asset_id, "high"
    asset_id = _nested_source_asset_id(row)
    if asset_id:
        return asset_id, "medium"
    row_id = str(row.get("run_id") or row.get("id") or "").strip()
    return f"unlinked:{bucket_name}:{row_id or id(row)}", "low"


def _lineage_time(row: dict[str, Any]) -> datetime:
    for key in ("updated_at", "created_at", "finished_at", "started_at"):
        value = row.get(key)
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
    return datetime.min


def build_pipeline_chains(
    *,
    processing: list[dict[str, Any]],
    models: list[dict[str, Any]],
    optimization: list[dict[str, Any]],
    agent_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group Data Lab history items by best-effort source asset id."""
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_asset_id": "",
            "lineage_confidence": "low",
            "best_effort": True,
            "processing": [],
            "models": [],
            "optimization": [],
            "agent_sessions": [],
        }
    )
    for bucket_name, rows in (
        ("processing", processing),
        ("models", models),
        ("optimization", optimization),
        ("agent_sessions", agent_sessions),
    ):
        for row in rows:
            source_id, confidence = _lineage_source(row, bucket_name)
            bucket = buckets[source_id]
            bucket["source_asset_id"] = "" if confidence == "low" else source_id
            if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[str(bucket["lineage_confidence"])]:
                bucket["lineage_confidence"] = confidence
            bucket[bucket_name].append(row)
    chains = []
    for source_id, bucket in buckets.items():
        stages = {
            "processing_count": len(bucket["processing"]),
            "model_count": len(bucket["models"]),
            "optimization_count": len(bucket["optimization"]),
            "agent_session_count": len(bucket["agent_sessions"]),
        }
        latest_candidates = bucket["processing"] + bucket["models"] + bucket["optimization"] + bucket["agent_sessions"]
        latest_item = max(latest_candidates, key=_lineage_time, default={})
        chains.append(
            {
                "id": source_id,
                "source_asset_id": bucket["source_asset_id"],
                "lineage_confidence": bucket["lineage_confidence"],
                "confidence": bucket["lineage_confidence"],
                "lineage_quality": bucket["lineage_confidence"],
                "best_effort": bucket["best_effort"],
                "stages": stages,
                "processing": bucket["processing"][:5],
                "models": bucket["models"][:5],
                "optimization": bucket["optimization"][:5],
                "agent_sessions": bucket["agent_sessions"][:5],
                "latest": latest_item,
                "latest_title": str(latest_item.get("title") or ""),
                "latest_at": str(latest_item.get("updated_at") or latest_item.get("created_at") or ""),
                "latest_status": str(latest_item.get("status") or ""),
            }
        )
    return sorted(chains, key=lambda item: _lineage_time(item.get("latest") or {}), reverse=True)
