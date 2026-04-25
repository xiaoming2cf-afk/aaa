from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .runtime import math_status_metadata


SUBSYSTEM_DEFAULT_METRICS: dict[str, dict[str, Any]] = {
    "retrieval": {
        "top_k_recall": None,
        "baseline_top_k_recall": None,
        "golden_query_count": 0,
        "baseline": "lexical_knowledge_score",
    },
    "delivery": {
        "brier_score": None,
        "expected_calibration_error": None,
        "false_publish_rate": None,
        "false_block_rate": None,
        "calibration_sample_count": 0,
    },
    "repair": {
        "repair_success_rate": None,
        "human_intervention_false_positive_rate": None,
        "human_intervention_false_negative_rate": None,
        "calibration_sample_count": 0,
    },
    "candidate_selection": {
        "candidate_selection_win_rate": None,
        "false_approval_rate": None,
        "calibration_sample_count": 0,
    },
}


SUBSYSTEM_DEFAULT_THRESHOLDS: dict[str, dict[str, dict[str, float]]] = {
    "retrieval": {
        "min": {
            "top_k_recall": 0.8,
            "baseline_delta": 0.0,
            "golden_query_count": 3.0,
        }
    },
    "delivery": {
        "max": {
            "brier_score": 0.12,
            "expected_calibration_error": 0.08,
            "false_publish_rate": 0.0,
            "false_block_rate": 0.2,
        },
        "min": {"calibration_sample_count": 30.0},
    },
    "repair": {
        "min": {
            "repair_success_rate": 0.7,
            "calibration_sample_count": 30.0,
        },
        "max": {
            "human_intervention_false_positive_rate": 0.2,
            "human_intervention_false_negative_rate": 0.1,
        },
    },
    "candidate_selection": {
        "min": {
            "candidate_selection_win_rate": 0.55,
            "calibration_sample_count": 30.0,
        },
        "max": {"false_approval_rate": 0.0},
    },
}


def default_calibration_registry_path() -> Path:
    configured = os.getenv("AGENT_MATH_CALIBRATION_REGISTRY", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "docs" / "agent_math" / "calibration_registry.json"


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def _load_registry(path: str | Path | None = None) -> tuple[dict[str, Any], str]:
    registry_path = Path(path).expanduser().resolve() if path else default_calibration_registry_path()
    if not registry_path.exists():
        return {}, str(registry_path)
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "registry_version": "",
            "subsystems": {},
            "_load_error": f"invalid_json:{registry_path}",
        }, str(registry_path)
    if not isinstance(payload, dict):
        return {
            "registry_version": "",
            "subsystems": {},
            "_load_error": f"invalid_shape:{registry_path}",
        }, str(registry_path)
    return payload, str(registry_path)


@dataclass(frozen=True)
class CalibrationReport:
    subsystem: str
    requested_calibrated: bool = False
    calibrated: bool = False
    calibration_version: str = ""
    registry_version: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, dict[str, float]] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)
    source_path: str = ""

    def validation_metrics(self) -> dict[str, Any]:
        return {
            **self.metrics,
            "calibration_requested": self.requested_calibrated,
            "calibration_gate_passed": self.calibrated,
            "calibration_failure_reasons": list(self.failure_reasons),
            "registry_version": self.registry_version,
            "registry_source": self.source_path,
        }


def _threshold_failures(metrics: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, minimum in (thresholds.get("min") or {}).items():
        value = _safe_float(metrics.get(key))
        required = _safe_float(minimum)
        if value is None or required is None or value < required:
            failures.append(f"{key}_below_min")
    for key, maximum in (thresholds.get("max") or {}).items():
        value = _safe_float(metrics.get(key))
        required = _safe_float(maximum)
        if value is None or required is None or value > required:
            failures.append(f"{key}_above_max")
    for key, expected in (thresholds.get("equals") or {}).items():
        value = _safe_float(metrics.get(key))
        required = _safe_float(expected)
        if value is None or required is None or abs(value - required) > 1e-12:
            failures.append(f"{key}_not_equal")
    return failures


def calibration_report_for_subsystem(
    subsystem: str,
    *,
    registry_path: str | Path | None = None,
    default_metrics: dict[str, Any] | None = None,
) -> CalibrationReport:
    normalized = str(subsystem or "").strip().lower()
    registry, source_path = _load_registry(registry_path)
    registry_version = str(registry.get("registry_version") or "")
    subsystems = registry.get("subsystems") if isinstance(registry.get("subsystems"), dict) else {}
    entry = subsystems.get(normalized) if isinstance(subsystems, dict) else None
    base_metrics = {
        **SUBSYSTEM_DEFAULT_METRICS.get(normalized, {}),
        **(default_metrics or {}),
    }
    default_thresholds = SUBSYSTEM_DEFAULT_THRESHOLDS.get(normalized, {})
    if not isinstance(entry, dict):
        return CalibrationReport(
            subsystem=normalized,
            metrics=base_metrics,
            thresholds=default_thresholds,
            failure_reasons=["missing_calibration_report"],
            source_path=source_path,
            registry_version=registry_version,
        )

    requested = bool(entry.get("calibrated"))
    metrics = {
        **base_metrics,
        **(entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}),
    }
    thresholds = entry.get("thresholds") if isinstance(entry.get("thresholds"), dict) else default_thresholds
    failures = _threshold_failures(metrics, thresholds)
    if not requested:
        failures.insert(0, "calibration_not_requested")
    load_error = registry.get("_load_error")
    if load_error:
        failures.insert(0, str(load_error))
    calibrated = requested and not failures
    return CalibrationReport(
        subsystem=normalized,
        requested_calibrated=requested,
        calibrated=calibrated,
        calibration_version=str(entry.get("version") or registry_version or ""),
        registry_version=registry_version,
        metrics=metrics,
        thresholds=thresholds,
        failure_reasons=failures,
        source_path=source_path,
    )


def calibrated_math_status(
    *,
    subsystem: str,
    status: str,
    derivation_ref: str,
    gate: str,
    default_validation_metrics: dict[str, Any] | None = None,
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    report = calibration_report_for_subsystem(
        subsystem,
        registry_path=registry_path,
        default_metrics=default_validation_metrics,
    )
    return math_status_metadata(
        status=status,
        calibrated=report.calibrated,
        calibration_version=report.calibration_version,
        validation_metrics=report.validation_metrics(),
        derivation_ref=derivation_ref,
        gate=gate,
    )
