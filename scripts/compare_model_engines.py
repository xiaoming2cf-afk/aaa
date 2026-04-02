from __future__ import annotations

import inspect
import json
import math
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify_data_lab import auth_headers, build_panel_dataset, build_time_series_dataset, configure_test_environment, create_workspace, upload_csv_asset  # noqa: E402
from verify_data_lab_full import _nonempty_table_count, _save_result_bundle, _assert_model_output, _model_specs  # noqa: E402


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _merge_spec_dicts(base: dict[str, Any] | None, overlay: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_spec_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _coef_map(result: dict[str, Any]) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for row in result.get("coefficients", []) or []:
        term = str(row.get("term", "")).strip()
        value = _safe_float(row.get("coefficient"))
        if term and value is not None:
            mapping[term] = value
    return mapping


def _table_rows(result: dict[str, Any], name: str) -> list[dict[str, Any]]:
    rows = (result.get("tables") or {}).get(name) or []
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _numeric_signature(result: dict[str, Any], *, limit: int = 160) -> list[float]:
    values: list[float] = []
    for row in sorted(result.get("coefficients", []) or [], key=lambda item: str(item.get("term", ""))):
        value = _safe_float(row.get("coefficient"))
        if value is not None:
            values.append(round(value, 8))
    for table_name in sorted((result.get("tables") or {}).keys()):
        rows = _table_rows(result, table_name)
        for row in rows[:15]:
            for key in sorted(row.keys()):
                value = _safe_float(row.get(key))
                if value is not None:
                    values.append(round(value, 8))
                    if len(values) >= limit:
                        return values
    return values[:limit]


def _stability_score(result_a: dict[str, Any], result_b: dict[str, Any]) -> float:
    sig_a = _numeric_signature(result_a)
    sig_b = _numeric_signature(result_b)
    if not sig_a or not sig_b:
        return 50.0
    overlap = min(len(sig_a), len(sig_b))
    if overlap == 0:
        return 50.0
    diffs = [abs(sig_a[idx] - sig_b[idx]) for idx in range(overlap)]
    mean_diff = float(np.mean(diffs)) if diffs else 0.0
    score = 100.0 / (1.0 + mean_diff * 50.0)
    if len(sig_a) != len(sig_b):
        score *= 0.9
    return max(0.0, min(100.0, score))


def _speed_scores(baseline_seconds: float, candidate_seconds: float) -> tuple[float, float]:
    if baseline_seconds <= 0 or candidate_seconds <= 0:
        return 50.0, 50.0
    faster = min(baseline_seconds, candidate_seconds)
    baseline_score = 100.0 * faster / baseline_seconds
    candidate_score = 100.0 * faster / candidate_seconds
    return max(0.0, min(100.0, baseline_score)), max(0.0, min(100.0, candidate_score))


def _completeness_score(result_main: dict[str, Any], result_variant: dict[str, Any], contract: dict[str, Any] | None) -> float:
    contract = contract or {}
    expected_primary = len(contract.get("primary_tables") or [])
    expected_robustness = len(contract.get("robustness_tables") or [])
    expected_figures = len(contract.get("figures") or [])
    actual_tables = _nonempty_table_count(result_main) + _nonempty_table_count(result_variant)
    actual_figures = len(result_main.get("figures", []) or []) + len(result_variant.get("figures", []) or [])
    table_denominator = max(1, expected_primary + max(1, expected_robustness))
    figure_denominator = max(1, expected_figures)
    core_score = 0.0
    for result in (result_main, result_variant):
        if result.get("interpretation", {}).get("sections"):
            core_score += 10.0
        if result.get("audit_trail"):
            core_score += 7.5
        if result.get("specification"):
            core_score += 7.5
    table_score = 45.0 * min(1.0, actual_tables / table_denominator)
    figure_score = 30.0 * min(1.0, actual_figures / figure_denominator)
    return max(0.0, min(100.0, core_score + table_score + figure_score))


def _coefficient_accuracy(result: dict[str, Any], truth_map: dict[str, float], *, aliases: dict[str, list[str]] | None = None) -> float:
    aliases = aliases or {}
    coefficients = _coef_map(result)
    penalties: list[float] = []
    for term, truth in truth_map.items():
        candidates = [term, *(aliases.get(term) or [])]
        value = next((coefficients[candidate] for candidate in candidates if candidate in coefficients), None)
        if value is None:
            penalties.append(1.0)
            continue
        scale = max(1.0, abs(truth))
        penalties.append(min(abs(value - truth) / scale, 2.0) / 2.0)
    if not penalties:
        return 50.0
    return max(0.0, min(100.0, 100.0 * (1.0 - float(np.mean(penalties)))))


def _sign_accuracy(result: dict[str, Any], sign_map: dict[str, float]) -> float:
    coefficients = _coef_map(result)
    hits = 0
    total = 0
    for term, expected_sign in sign_map.items():
        if term not in coefficients:
            continue
        total += 1
        actual_sign = math.copysign(1.0, coefficients[term]) if coefficients[term] != 0 else 0.0
        if actual_sign == expected_sign:
            hits += 1
    if total == 0:
        return 50.0
    return 100.0 * hits / total


def _forecast_rmse_score(rows: list[dict[str, Any]], actual: list[float]) -> float:
    if not rows or not actual:
        return 50.0
    predicted: list[float] = []
    for row in rows[: len(actual)]:
        for key in ("mean", "forecast", "predicted_mean", "value"):
            value = _safe_float(row.get(key))
            if value is not None:
                predicted.append(value)
                break
    if len(predicted) != len(actual):
        return 40.0
    rmse = float(np.sqrt(np.mean([(predicted[idx] - actual[idx]) ** 2 for idx in range(len(actual))])))
    scale = max(1.0, float(np.std(actual)) or 1.0)
    return max(0.0, min(100.0, 100.0 / (1.0 + rmse / scale)))


def _portfolio_accuracy(result: dict[str, Any], returns_frame: pd.DataFrame, *, objective: str) -> float:
    weight_rows = _table_rows(result, "weights_table")
    if not weight_rows:
        return 30.0
    weights = {str(row.get("asset", row.get("portfolio", ""))): _safe_float(row.get("weight")) or 0.0 for row in weight_rows}
    assets = [column for column in returns_frame.columns if column in weights]
    if not assets:
        return 30.0
    total_weight = sum(weights[asset] for asset in assets)
    if abs(total_weight - 1.0) > 0.15:
        return 20.0
    sample = returns_frame[assets].tail(24).copy()
    portfolio_series = sum(sample[asset] * weights[asset] for asset in assets)
    mean_return = float(portfolio_series.mean())
    volatility = float(portfolio_series.std(ddof=0) or 1.0)
    if objective == "sharpe":
        metric = mean_return / volatility
        return max(0.0, min(100.0, 60.0 + metric * 80.0))
    if objective == "min_variance":
        return max(0.0, min(100.0, 100.0 / (1.0 + volatility * 40.0)))
    # risk parity
    cov = sample.cov().to_numpy()
    weight_vec = np.array([weights[asset] for asset in assets], dtype=float)
    portfolio_vol = float(np.sqrt(weight_vec @ cov @ weight_vec))
    if portfolio_vol <= 0:
        return 20.0
    marginal = cov @ weight_vec / portfolio_vol
    contributions = weight_vec * marginal
    dispersion = float(np.std(contributions))
    return max(0.0, min(100.0, 100.0 / (1.0 + dispersion * 50.0)))


def _asset_pricing_accuracy(result: dict[str, Any]) -> float:
    alpha_rows = _table_rows(result, "alpha_table")
    if not alpha_rows:
        return 45.0
    alphas = [_safe_float(row.get("alpha")) for row in alpha_rows]
    alphas = [value for value in alphas if value is not None]
    if not alphas:
        return 45.0
    mean_abs_alpha = float(np.mean(np.abs(alphas)))
    return max(0.0, min(100.0, 100.0 / (1.0 + mean_abs_alpha * 25.0)))


def _accuracy_score(method: str, result: dict[str, Any], *, panel_frame: pd.DataFrame, ts_frame: pd.DataFrame) -> float:
    if method == "ols":
        return _coefficient_accuracy(result, {"size": 0.65, "leverage": -1.8})
    if method == "ppml":
        return _sign_accuracy(result, {"size": 1.0, "leverage": -1.0, "post": 1.0})
    if method in {"logit", "probit"}:
        return _sign_accuracy(result, {"size": -1.0, "leverage": 1.0, "treated": 1.0})
    if method == "fixed_effects":
        return _coefficient_accuracy(result, {"size": 0.65, "leverage": -1.8})
    if method == "panel_iv":
        return _coefficient_accuracy(result, {"endogenous_x": 0.55}, aliases={"endogenous_x": ["fitted_endogenous_x", "instrumented_endogenous_x"]})
    if method == "did":
        return _coefficient_accuracy(result, {"did_interaction": 1.35})
    if method == "event_study":
        rows = _table_rows(result, "event_study_table")
        post_rows = [row for row in rows if (_safe_float(row.get("event_time")) or -999) >= 0]
        estimates = [_safe_float(row.get("coefficient")) for row in post_rows]
        estimates = [value for value in estimates if value is not None]
        if not estimates:
            return 40.0
        mean_post = float(np.mean(estimates))
        return max(0.0, min(100.0, 100.0 / (1.0 + abs(mean_post - 1.35))))
    if method == "rdd":
        coeffs = _coef_map(result)
        for term in ("treated_at_cutoff", "cutoff_treatment", "treatment_at_cutoff", "post_cutoff"):
            if term in coeffs:
                return max(0.0, min(100.0, 100.0 / (1.0 + abs(coeffs[term] - 1.1))))
        return 45.0
    if method == "arima":
        actual = ts_frame["policy_rate"].tail(6).tolist()
        return _forecast_rmse_score(_table_rows(result, "forecast_summary"), actual)
    if method in {"var", "svar_irf"}:
        actual = ts_frame["return_a"].tail(5).tolist()
        forecast_rows = _table_rows(result, "forecast_summary")
        return _forecast_rmse_score(forecast_rows, actual)
    if method in {"arch", "garch"}:
        rows = _table_rows(result, "volatility_forecast_table") or _table_rows(result, "forecast_summary")
        actual = ts_frame["implied_vol"].tail(min(5, len(rows))).tolist()
        return _forecast_rmse_score(rows, actual)
    if method == "mean_variance":
        return _portfolio_accuracy(result, ts_frame[["return_a", "return_b", "return_c"]], objective="sharpe")
    if method == "minimum_variance":
        return _portfolio_accuracy(result, ts_frame[["return_a", "return_b", "return_c"]], objective="min_variance")
    if method == "risk_parity":
        return _portfolio_accuracy(result, ts_frame[["return_a", "return_b", "return_c"]], objective="risk_parity")
    if method in {"capm", "fama_french_3"}:
        return _asset_pricing_accuracy(result)
    return 50.0


def _prepare_method_payload(spec: dict[str, Any], *, use_variant: bool) -> tuple[str, dict[str, Any]]:
    payload = dict(spec["baseline"])
    variant_label = ""
    variant_spec: dict[str, Any] = {}
    if use_variant:
        variant = dict(spec.get("variant") or {})
        variant_label = str(variant.get("variant_label") or "").strip()
        variant_spec = dict(variant.get("variant_spec") or {})
        payload = _merge_spec_dicts(payload, variant_spec)
    payload["variant_label"] = variant_label
    payload["variant_spec"] = variant_spec
    payload["effective_specification"] = dict(payload)
    method = str(spec["method"])
    family = str(spec["family"])
    payload.setdefault("model_family", family)
    payload.setdefault("model_type", method)
    return method, payload


def _result_contract(family: str, method: str) -> dict[str, Any]:
    from research_agent.data_lab_catalog import get_model_method

    meta = get_model_method(family, method) or {}
    return dict(meta.get("paper_output_contract") or {})


@contextmanager
def _winner_override(mapping: dict[str, str] | None = None):
    from research_agent.model_engine_selection import WINNER_FILE, clear_model_engine_winner_cache

    previous = WINNER_FILE.read_text(encoding="utf-8") if WINNER_FILE.exists() else None
    if mapping:
        WINNER_FILE.write_text(json.dumps({"winners": mapping}, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if WINNER_FILE.exists():
            WINNER_FILE.unlink()
    clear_model_engine_winner_cache()
    try:
        yield
    finally:
        if previous is None:
            if WINNER_FILE.exists():
                WINNER_FILE.unlink()
        else:
            WINNER_FILE.write_text(previous, encoding="utf-8")
        clear_model_engine_winner_cache()


def _load_user_workspace(db, *, email: str, workspace_id: str):
    from research_agent.entities import User, Workspace

    user = db.scalar(select(User).where(User.email == email))
    workspace = db.get(Workspace, workspace_id)
    if user is None or workspace is None:
        raise RuntimeError("Failed to resolve verification user or workspace.")
    return user, workspace


def _run_direct_model(*, email: str, workspace_id: str, payload: dict[str, Any], engine_choice: str) -> tuple[dict[str, Any], float]:
    from research_agent.config import get_settings
    from research_agent.db import session_scope
    from research_agent.platform_core import run_model_analysis

    allowed_keys = set(inspect.signature(run_model_analysis).parameters) - {"settings", "db", "user", "workspace"}
    filtered_payload = {key: value for key, value in payload.items() if key in allowed_keys}
    model_type = str(filtered_payload.get("model_type") or "").strip().lower()
    winner_map = {model_type: engine_choice} if engine_choice != "baseline" else {}
    with _winner_override(winner_map):
        with session_scope() as db:
            user, workspace = _load_user_workspace(db, email=email, workspace_id=workspace_id)
            settings = get_settings()
            started = time.perf_counter()
            result = run_model_analysis(settings, db, user=user, workspace=workspace, **filtered_payload)
            duration = time.perf_counter() - started
            return json.loads(json.dumps(result, ensure_ascii=False)), duration


def _decision_reason(
    *,
    baseline_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
    final_decision: str,
) -> str:
    if baseline_metrics["accuracy_score"] != candidate_metrics["accuracy_score"]:
        lead = "accuracy"
    elif baseline_metrics["completeness_score"] != candidate_metrics["completeness_score"]:
        lead = "completeness"
    elif baseline_metrics["stability_score"] != candidate_metrics["stability_score"]:
        lead = "stability"
    else:
        lead = "speed"
    winner_label = "candidate" if final_decision != "baseline" else "baseline"
    return f"{winner_label} wins on {lead} under the quality-first decision order (accuracy > completeness > stability > speed)."


def _pick_winner(baseline_metrics: dict[str, float], candidate_metrics: dict[str, float], candidate_engine: str) -> str:
    priorities = ["accuracy_score", "completeness_score", "stability_score", "speed_score"]
    for field in priorities:
        baseline_value = baseline_metrics[field]
        candidate_value = candidate_metrics[field]
        if abs(candidate_value - baseline_value) > 2.0:
            return candidate_engine if candidate_value > baseline_value else "baseline"
    baseline_total = 0.4 * baseline_metrics["accuracy_score"] + 0.3 * baseline_metrics["completeness_score"] + 0.2 * baseline_metrics["stability_score"] + 0.1 * baseline_metrics["speed_score"]
    candidate_total = 0.4 * candidate_metrics["accuracy_score"] + 0.3 * candidate_metrics["completeness_score"] + 0.2 * candidate_metrics["stability_score"] + 0.1 * candidate_metrics["speed_score"]
    return candidate_engine if candidate_total > baseline_total else "baseline"


def run_comparison(output_dir: Path | None = None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-model-compare-"))
    configure_test_environment(temp_root)

    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)

        register = client.post(
            "/api/auth/register",
            json={"full_name": "Engine Comparator", "email": "compare@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        workspace_id = create_workspace(client, token, "Engine Comparison Lab")

        panel_frame = build_panel_dataset()
        ts_frame = build_time_series_dataset()
        panel_asset_id = upload_csv_asset(client, token, workspace_id, "comparison_panel.csv", panel_frame)
        ts_asset_id = upload_csv_asset(client, token, workspace_id, "comparison_ts.csv", ts_frame)

        overlap_methods = {
            "ols",
            "ppml",
            "logit",
            "probit",
            "fixed_effects",
            "panel_iv",
            "did",
            "event_study",
            "rdd",
            "arima",
            "var",
            "svar_irf",
            "arch",
            "garch",
            "mean_variance",
            "minimum_variance",
            "risk_parity",
            "capm",
            "fama_french_3",
        }

        comparison_specs = [spec for spec in _model_specs(panel_asset_id, ts_asset_id) if spec["method"] in overlap_methods]
        from research_agent.data_lab_catalog import get_model_method

        winners: dict[str, str] = {}
        model_reports: dict[str, Any] = {}

        for spec in comparison_specs:
            family = str(spec["family"])
            method = str(spec["method"])
            label = f"{family}/{method}"
            started_at = time.perf_counter()
            print(f"[compare_model_engines] START {label}", flush=True)
            method_meta = get_model_method(family, method) or {}
            candidate_engine = str(method_meta.get("candidate_engine") or method_meta.get("engine") or "candidate")
            contract = _result_contract(family, method)

            baseline_method, baseline_main_payload = _prepare_method_payload(spec, use_variant=False)
            _, baseline_variant_payload = _prepare_method_payload(spec, use_variant=True)

            baseline_main_result, baseline_main_time = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_main_payload,
                engine_choice="baseline",
            )
            baseline_repeat_result, baseline_repeat_time = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_main_payload,
                engine_choice="baseline",
            )
            baseline_variant_result, _ = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_variant_payload,
                engine_choice="baseline",
            )

            candidate_main_result, candidate_main_time = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_main_payload,
                engine_choice=candidate_engine,
            )
            candidate_repeat_result, candidate_repeat_time = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_main_payload,
                engine_choice=candidate_engine,
            )
            candidate_variant_result, _ = _run_direct_model(
                email="compare@example.com",
                workspace_id=workspace_id,
                payload=baseline_variant_payload,
                engine_choice=candidate_engine,
            )

            _assert_model_output(f"{label} baseline main", baseline_main_result)
            _assert_model_output(f"{label} baseline variant", baseline_variant_result)
            _assert_model_output(f"{label} candidate main", candidate_main_result)
            _assert_model_output(f"{label} candidate variant", candidate_variant_result)

            baseline_speed, candidate_speed = _speed_scores(
                (baseline_main_time + baseline_repeat_time) / 2.0,
                (candidate_main_time + candidate_repeat_time) / 2.0,
            )
            baseline_metrics = {
                "speed_score": baseline_speed,
                "completeness_score": _completeness_score(baseline_main_result, baseline_variant_result, contract),
                "accuracy_score": _accuracy_score(method, baseline_main_result, panel_frame=panel_frame, ts_frame=ts_frame),
                "stability_score": _stability_score(baseline_main_result, baseline_repeat_result),
            }
            candidate_metrics = {
                "speed_score": candidate_speed,
                "completeness_score": _completeness_score(candidate_main_result, candidate_variant_result, contract),
                "accuracy_score": _accuracy_score(method, candidate_main_result, panel_frame=panel_frame, ts_frame=ts_frame),
                "stability_score": _stability_score(candidate_main_result, candidate_repeat_result),
            }
            winner = _pick_winner(baseline_metrics, candidate_metrics, candidate_engine)
            winners[method] = winner

            report = {
                "family": family,
                "method": method,
                "baseline_engine": "baseline",
                "candidate_engine": candidate_engine,
                "baseline_metrics": {
                    **baseline_metrics,
                    "avg_runtime_seconds": (baseline_main_time + baseline_repeat_time) / 2.0,
                },
                "candidate_metrics": {
                    **candidate_metrics,
                    "avg_runtime_seconds": (candidate_main_time + candidate_repeat_time) / 2.0,
                },
                "final_decision": winner,
                "decision_reason": _decision_reason(
                    baseline_metrics=baseline_metrics,
                    candidate_metrics=candidate_metrics,
                    final_decision=winner,
                ),
            }
            model_reports[label] = report

            if output_dir:
                model_root = output_dir / "models" / method
                _save_result_bundle(client, token, {"result": baseline_main_result}, model_root / "baseline" / "main")
                _save_result_bundle(client, token, {"result": baseline_variant_result}, model_root / "baseline" / "variant")
                _save_result_bundle(client, token, {"result": candidate_main_result}, model_root / "candidate" / "main")
                _save_result_bundle(client, token, {"result": candidate_variant_result}, model_root / "candidate" / "variant")
                _write_json(model_root / "comparison.json", report)
            elapsed = time.perf_counter() - started_at
            print(
                f"[compare_model_engines] PASS {label} winner={winner} "
                f"(baseline={baseline_metrics['accuracy_score']:.1f}/{baseline_metrics['completeness_score']:.1f}/"
                f"{baseline_metrics['stability_score']:.1f}/{baseline_metrics['speed_score']:.1f}; "
                f"candidate={candidate_metrics['accuracy_score']:.1f}/{candidate_metrics['completeness_score']:.1f}/"
                f"{candidate_metrics['stability_score']:.1f}/{candidate_metrics['speed_score']:.1f}; "
                f"{elapsed:.2f}s)",
                flush=True,
            )

        comparison_report = {
            "status": "passed",
            "generated_at": datetime.now().astimezone().isoformat(),
            "models": model_reports,
            "winners": winners,
        }
        if output_dir:
            _write_json(output_dir / "comparison_report.json", comparison_report)
            _write_text(
                output_dir / "notes.md",
                "\n".join(
                    [
                        "# Model Engine Comparison",
                        "",
                        "This directory stores the baseline-vs-candidate comparison for overlapping models.",
                        "Decision order: accuracy > completeness > stability > speed.",
                        "",
                        f"- Compared models: {len(model_reports)}",
                        f"- Candidate wins: {sum(1 for value in winners.values() if value != 'baseline')}",
                        f"- Baseline wins: {sum(1 for value in winners.values() if value == 'baseline')}",
                    ]
                ),
            )
        return comparison_report
    finally:
        client.close()


def main() -> None:
    report = run_comparison()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
