from __future__ import annotations

from typing import Any


def _error_class(error_message: str) -> str:
    lowered = (error_message or "").lower()
    if any(token in lowered for token in ("not allowed", "safety", "blocked by")):
        return "safety"
    if any(token in lowered for token in ("syntaxerror", "unexpected eof", "invalid syntax")):
        return "syntax"
    if any(token in lowered for token in ("keyerror", "nameerror", "attributeerror", "missing", "available columns")):
        return "schema"
    return "runtime"


def build_data_lab_repair_decision(
    *,
    error_message: str,
    attempt_index: int,
    max_attempts: int,
    mode: str,
    has_human_code: bool = False,
) -> dict[str, Any]:
    cls = _error_class(error_message)
    progress_ratio = 1.0 if max_attempts <= 0 else min(max(float(attempt_index) / float(max_attempts), 0.0), 1.0)
    repair_base = {
        "syntax": 0.62,
        "schema": 0.57,
        "runtime": 0.44,
        "safety": 0.02,
    }.get(cls, 0.4)
    repair_utility = max(0.0, repair_base - 0.32 * progress_ratio)
    intervene_utility = min(1.0, 0.28 + 0.42 * progress_ratio + (0.18 if has_human_code else 0.0) + (0.1 if cls in {"syntax", "runtime"} else 0.0))
    block_utility = 0.96 if cls == "safety" else (0.18 if progress_ratio < 1.0 else 0.38)
    family_scores = {
        "A_auto": round(repair_utility, 6),
        "A_intervene": round(intervene_utility, 6),
        "A_terminal": round(block_utility, 6),
    }
    best_family = max(family_scores, key=family_scores.get)
    best_action = {
        "A_auto": "repair",
        "A_intervene": "ask_human",
        "A_terminal": "block",
    }[best_family]
    return {
        "mode": mode,
        "error_class": cls,
        "attempt_index": int(attempt_index),
        "max_attempts": int(max_attempts),
        "family_scores": family_scores,
        "best_family": best_family,
        "best_action": best_action,
        "active_override": mode == "active" and best_action != "repair",
    }
