from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_pipeline_chains(
    *,
    processing: list[dict[str, Any]],
    models: list[dict[str, Any]],
    optimization: list[dict[str, Any]],
    agent_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group Data Lab history items by best-effort source asset id."""
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"source_asset_id": "", "processing": [], "models": [], "optimization": [], "agent_sessions": []})
    for bucket_name, rows in (
        ("processing", processing),
        ("models", models),
        ("optimization", optimization),
        ("agent_sessions", agent_sessions),
    ):
        for row in rows:
            source_id = str(row.get("source_asset_id") or row.get("asset_id") or row.get("id") or "unknown").strip() or "unknown"
            bucket = buckets[source_id]
            bucket["source_asset_id"] = "" if source_id == "unknown" else source_id
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
        chains.append(
            {
                "id": source_id,
                "source_asset_id": bucket["source_asset_id"],
                "stages": stages,
                "processing": bucket["processing"][:5],
                "models": bucket["models"][:5],
                "optimization": bucket["optimization"][:5],
                "agent_sessions": bucket["agent_sessions"][:5],
                "latest_title": next((str(item.get("title") or "") for item in latest_candidates if item.get("title")), ""),
            }
        )
    return sorted(chains, key=lambda item: item.get("latest_title") or item.get("id") or "")
