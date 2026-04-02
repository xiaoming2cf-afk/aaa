from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


WINNER_FILE = Path(__file__).with_name("model_engine_winners.json")


@lru_cache(maxsize=1)
def load_model_engine_winners() -> dict[str, str]:
    if not WINNER_FILE.exists():
        return {}
    try:
        payload = json.loads(WINNER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        if isinstance(payload.get("winners"), dict):
            return {str(key).strip().lower(): str(value).strip().lower() for key, value in payload["winners"].items()}
        return {str(key).strip().lower(): str(value).strip().lower() for key, value in payload.items() if isinstance(value, str)}
    return {}


def clear_model_engine_winner_cache() -> None:
    load_model_engine_winners.cache_clear()


def get_winning_engine(model_type: str) -> str:
    normalized = model_type.strip().lower()
    return load_model_engine_winners().get(normalized, "baseline")


def use_candidate_engine(model_type: str) -> bool:
    return get_winning_engine(model_type) != "baseline"


def write_model_engine_winners(winners: dict[str, str], *, metadata: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"winners": {str(key).strip().lower(): str(value).strip().lower() for key, value in winners.items()}}
    if isinstance(metadata, dict) and metadata:
        payload.update(metadata)
    WINNER_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_model_engine_winner_cache()
