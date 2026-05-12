from __future__ import annotations

from typing import Any

from .schemas import PreflightCheck, PreflightStatus


def aggregate_preflight_status(checks: list[PreflightCheck]) -> PreflightStatus:
    if any(check.get("status") == "blocked" for check in checks):
        return "blocked"
    if any(check.get("status") == "warning" for check in checks):
        return "warning"
    return "ok"


def make_check(key: str, label: str, status: PreflightStatus, detail: str) -> PreflightCheck:
    severity = "error" if status == "blocked" else "warning" if status == "warning" else "info"
    return {"key": key, "label": label, "status": status, "severity": severity, "detail": detail}


def compact_warnings(checks: list[PreflightCheck]) -> list[str]:
    return [str(check.get("detail") or "") for check in checks if check.get("status") == "warning" and check.get("detail")]


def compact_blocking_reasons(checks: list[PreflightCheck]) -> list[str]:
    return [str(check.get("detail") or "") for check in checks if check.get("status") == "blocked" and check.get("detail")]
