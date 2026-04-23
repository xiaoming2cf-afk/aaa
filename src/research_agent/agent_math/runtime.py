from __future__ import annotations

from typing import Any


VALID_MATH_MODES = {"off", "shadow", "active"}


def normalize_math_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in VALID_MATH_MODES:
        return mode
    return "off"


def settings_math_mode(settings: Any) -> str:
    return normalize_math_mode(getattr(settings, "agent_math_mode", "off"))
