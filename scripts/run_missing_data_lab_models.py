from __future__ import annotations

import argparse
import io
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_agent.data_lab_catalog import MODEL_FAMILY_CATALOG
from session_auth import same_origin_headers, session_token_from_cookies
from verify_data_lab_full import _assert_model_output, _save_result_bundle


BASE_URL = "http://127.0.0.1:8010"
EMAIL = "codex.frontend.1775101609@example.com"
PASSWORD = "CodexPass!2026"


class BaseUrlSession(requests.Session):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, url: str, *args: Any, **kwargs: Any):  # type: ignore[override]
        if url.startswith("/"):
            url = f"{self.base_url}{url}"
        return super().request(method, url, *args, **kwargs)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def locate_single(pattern: str) -> Path:
    matches = list(REPO_ROOT.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one match for {pattern!r}, got {len(matches)}")
    return matches[0]


RESULT_ROOT = locate_single("*/01_data_lab_results")
MANIFEST_DIR = RESULT_ROOT / "00_manifest"
SESSION_STATE_PATH = MANIFEST_DIR / "extended_models_session.json"
MANIFEST_PATH = MANIFEST_DIR / "extended_models_manifest.json"
SUMMARY_PATH = MANIFEST_DIR / "model_coverage_summary.json"
PANEL_INPUT_PATH = locate_single("*/00_derived_inputs/trade_panel_enriched.csv")
TS_INPUT_PATH = locate_single("*/00_derived_inputs/trade_timeseries_enriched.csv")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_panel_unit_metadata(panel_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(panel_path, usecols=["firm_id", "treated"])
    treated_units = sorted(frame.loc[frame["treated"] == 1, "firm_id"].astype(str).unique().tolist())
    control_units = sorted(frame.loc[frame["treated"] == 0, "firm_id"].astype(str).unique().tolist())
    if not treated_units:
        raise RuntimeError("No treated units found in the panel input.")
    if len(control_units) < 3:
        raise RuntimeError("Not enough control units found in the panel input.")
    return {"treated_unit": treated_units[0], "control_units": control_units[:6]}


def login(session: requests.Session) -> str:
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        headers=same_origin_headers(BASE_URL),
        json={"email": EMAIL, "password": PASSWORD},
        timeout=60,
    )
    response.raise_for_status()
    return session_token_from_cookies(session)


def upload_csv_asset(session: requests.Session, token: str, workspace_id: str, path: Path) -> str:
    with path.open("rb") as handle:
        response = session.post(
            f"{BASE_URL}/api/workspaces/{workspace_id}/assets/upload",
            headers=auth_headers(token),
            files={"file": (path.name, io.BytesIO(handle.read()), "text/csv")},
            data={"description": path.name, "source_url": ""},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()["asset"]["id"]


def create_session_state(fresh: bool = False) -> dict[str, Any]:
    if SESSION_STATE_PATH.exists() and not fresh:
        return read_json(SESSION_STATE_PATH, {})

    session = BaseUrlSession(BASE_URL)
    token = login(session)
    response = session.post(
        f"{BASE_URL}/api/workspaces",
        json={
            "name": f"Codex Data Lab Missing Models {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "description": "Incremental workspace for the missing Data Lab model coverage sweep.",
            "research_domain": "economics",
        },
        headers=auth_headers(token),
        timeout=60,
    )
    response.raise_for_status()
    workspace_id = response.json()["workspace"]["id"]
    panel_asset_id = upload_csv_asset(session, token, workspace_id, PANEL_INPUT_PATH)
    ts_asset_id = upload_csv_asset(session, token, workspace_id, TS_INPUT_PATH)
    state = {
        "base_url": BASE_URL,
        "email": EMAIL,
        "workspace_id": workspace_id,
        "panel_asset_id": panel_asset_id,
        "ts_asset_id": ts_asset_id,
        "created_at": utc_now(),
        "panel_input_path": str(PANEL_INPUT_PATH),
        "ts_input_path": str(TS_INPUT_PATH),
    }
    write_json(SESSION_STATE_PATH, state)
    return state


def scan_saved_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for path in RESULT_ROOT.rglob("baseline"):
        if not path.is_dir():
            continue
        if "optimization" in path.parts:
            continue
        if len(path.parts) < 6:
            continue
        pairs.add((path.parts[-3], path.parts[-2]))
    return pairs


def scan_catalog_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for family in MODEL_FAMILY_CATALOG:
        family_slug = str(family["slug"])
        for method in family["methods"]:
            pairs.append((family_slug, str(method["slug"])))
    return pairs


def build_spec_map(panel_asset_id: str, ts_asset_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    unit_meta = load_panel_unit_metadata(PANEL_INPUT_PATH)
    features = [
        "market_return",
        "smb",
        "hml",
        "return_a",
        "return_b",
        "return_c",
        "policy_rate",
        "inflation_gap",
        "output_gap",
    ]

    def panel_model(family: str, method: str, **payload: Any) -> dict[str, Any]:
        return {
            "group": "country_panel",
            "payload": {"asset_id": panel_asset_id, "model_family": family, "model_type": method, **payload},
        }

    def ts_model(family: str, method: str, **payload: Any) -> dict[str, Any]:
        return {
            "group": "macro_finance_ts",
            "payload": {"asset_id": ts_asset_id, "model_family": family, "model_type": method, **payload},
        }

    return {
        ("econometrics_baseline", "random_effects"): panel_model("econometrics_baseline", "random_effects", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "first_difference"): panel_model("econometrics_baseline", "first_difference", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "between_ols"): panel_model("econometrics_baseline", "between_ols", dependent="outcome_y", independents=["size", "profitability"], controls=["endogenous_x"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "pooled_ols"): panel_model("econometrics_baseline", "pooled_ols", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "fama_macbeth"): panel_model("econometrics_baseline", "fama_macbeth", dependent="outcome_y", independents=["size", "profitability"], controls=["endogenous_x"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "iv_liml"): panel_model("econometrics_baseline", "iv_liml", dependent="outcome_y", independents=["size"], controls=["leverage"], endogenous_column="endogenous_x", instrument_columns=["instrument_z"]),
        ("econometrics_baseline", "iv_gmm"): panel_model("econometrics_baseline", "iv_gmm", dependent="outcome_y", independents=["size"], controls=["leverage"], endogenous_column="endogenous_x", instrument_columns=["instrument_z"]),
        ("econometrics_baseline", "absorbing_ls"): panel_model("econometrics_baseline", "absorbing_ls", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], entity_column="firm_id", time_column="calendar_year"),
        ("econometrics_baseline", "sur"): panel_model("econometrics_baseline", "sur", dependent="outcome_y", secondary_dependent="secondary_outcome"),
        ("econometrics_baseline", "iv_3sls"): panel_model("econometrics_baseline", "iv_3sls", dependent="outcome_y", secondary_dependent="secondary_outcome", endogenous_column="endogenous_x", instrument_columns=["instrument_z"]),
        ("econometrics_baseline", "system_gmm"): panel_model("econometrics_baseline", "system_gmm", dependent="outcome_y", secondary_dependent="secondary_outcome", endogenous_column="endogenous_x", instrument_columns=["instrument_z"]),
        ("econometrics_baseline", "glm"): panel_model("econometrics_baseline", "glm", dependent="count_outcome", independents=["size", "leverage"], controls=["post"], glm_family="poisson"),
        ("econometrics_baseline", "quantile_regression"): panel_model("econometrics_baseline", "quantile_regression", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], quantile=0.5),
        ("econometrics_baseline", "gee"): panel_model("econometrics_baseline", "gee", dependent="outcome_y", independents=["size", "leverage"], controls=["post"], entity_column="firm_id", gee_group_column="firm_id", gee_family="gaussian"),
        ("econometrics_baseline", "mnlogit"): panel_model("econometrics_baseline", "mnlogit", dependent="multiclass_outcome", independents=["size", "leverage"], controls=["post"]),
        ("econometrics_baseline", "negative_binomial"): panel_model("econometrics_baseline", "negative_binomial", dependent="count_outcome", independents=["size", "leverage"], controls=["post"]),
        ("econometrics_baseline", "zero_inflated_count"): panel_model("econometrics_baseline", "zero_inflated_count", dependent="count_outcome", independents=["size", "leverage"], controls=["post"], inflation_regressors=["size", "post"], count_family="poisson"),
        ("econometrics_baseline", "mixedlm"): panel_model("econometrics_baseline", "mixedlm", dependent="outcome_y", independents=["size", "leverage", "post"], entity_column="firm_id"),
        ("time_series_finance", "varmax"): ts_model("time_series_finance", "varmax", series_columns=["return_a", "return_b", "return_c"], time_column="date", varmax_order=[1, 1], forecast_steps=6),
        ("time_series_finance", "vecm"): ts_model("time_series_finance", "vecm", series_columns=["level_a", "level_b"], time_column="date", coint_rank=1, vecm_diff_lags=1, forecast_steps=6),
        ("time_series_finance", "markov_switching"): ts_model("time_series_finance", "markov_switching", dependent="asset_return", time_column="date", markov_regimes=2),
        ("time_series_finance", "unobserved_components"): ts_model("time_series_finance", "unobserved_components", dependent="policy_rate", time_column="date", seasonal_periods=12),
        ("time_series_finance", "exponential_smoothing"): ts_model("time_series_finance", "exponential_smoothing", dependent="policy_rate", time_column="date", seasonal="add", seasonal_periods=12, forecast_steps=6),
        ("time_series_finance", "egarch"): ts_model("time_series_finance", "egarch", dependent="asset_return", time_column="date", garch_p=1, garch_q=1, forecast_steps=6),
        ("time_series_finance", "gjr_garch"): ts_model("time_series_finance", "gjr_garch", dependent="asset_return", time_column="date", garch_p=1, garch_o=1, garch_q=1, forecast_steps=6),
        ("time_series_finance", "harx"): ts_model("time_series_finance", "harx", dependent="asset_return", time_column="date", harx_lags=[1, 5, 12], forecast_steps=6),
        ("time_series_finance", "adf_test"): ts_model("time_series_finance", "adf_test", dependent="policy_rate", time_column="date", trend="c"),
        ("time_series_finance", "kpss_test"): ts_model("time_series_finance", "kpss_test", dependent="policy_rate", time_column="date", trend="c"),
        ("time_series_finance", "pp_test"): ts_model("time_series_finance", "pp_test", dependent="policy_rate", time_column="date", trend="c"),
        ("time_series_finance", "zivot_andrews"): ts_model("time_series_finance", "zivot_andrews", dependent="policy_rate", time_column="date", trend="ct"),
        ("time_series_finance", "engle_granger"): ts_model("time_series_finance", "engle_granger", dependent="level_a", series_columns=["level_b"], time_column="date"),
        ("time_series_finance", "dynamic_ols"): ts_model("time_series_finance", "dynamic_ols", dependent="level_a", series_columns=["level_b"], time_column="date"),
        ("time_series_finance", "fm_ols"): ts_model("time_series_finance", "fm_ols", dependent="level_a", series_columns=["level_b"], time_column="date"),
        ("portfolio_allocation", "efficient_frontier"): ts_model("portfolio_allocation", "efficient_frontier", series_columns=["return_a", "return_b", "return_c"], time_column="date", portfolio_objective="max_sharpe", long_only=True),
        ("portfolio_allocation", "semivariance_frontier"): ts_model("portfolio_allocation", "semivariance_frontier", series_columns=["return_a", "return_b", "return_c"], time_column="date", long_only=True),
        ("portfolio_allocation", "cvar_frontier"): ts_model("portfolio_allocation", "cvar_frontier", series_columns=["return_a", "return_b", "return_c"], time_column="date", cvar_beta=0.95, long_only=True),
        ("portfolio_allocation", "black_litterman"): ts_model("portfolio_allocation", "black_litterman", series_columns=["return_a", "return_b", "return_c"], time_column="date"),
        ("portfolio_allocation", "hrp"): ts_model("portfolio_allocation", "hrp", series_columns=["return_a", "return_b", "return_c"], time_column="date"),
        ("portfolio_allocation", "discrete_allocation"): ts_model("portfolio_allocation", "discrete_allocation", series_columns=["return_a", "return_b", "return_c"], time_column="date", capital=100000.0),
        ("portfolio_allocation", "cdar_frontier"): ts_model("portfolio_allocation", "cdar_frontier", series_columns=["return_a", "return_b", "return_c"], time_column="date", cdar_beta=0.95, long_only=True),
        ("asset_pricing", "traded_factor_model"): ts_model("asset_pricing", "traded_factor_model", dependent="asset_return", series_columns=["asset_return", "return_a", "return_b"], factor_columns=["market_return", "smb", "hml"], time_column="date"),
        ("asset_pricing", "linear_factor_gmm"): ts_model("asset_pricing", "linear_factor_gmm", dependent="asset_return", series_columns=["asset_return", "return_a", "return_b"], factor_columns=["market_return", "smb", "hml"], time_column="date"),
        ("causal_inference", "staggered_did"): panel_model("causal_inference", "staggered_did", dependent="outcome_y", controls=["size", "leverage"], entity_column="firm_id", time_column="calendar_year", treatment_column="treated", treatment_time_column="treatment_time", lead_window=4, lag_window=4),
        ("causal_inference", "synthetic_control"): panel_model("causal_inference", "synthetic_control", dependent="outcome_y", entity_column="firm_id", time_column="calendar_year", treated_unit=unit_meta["treated_unit"], control_units=unit_meta["control_units"], treatment_time=12),
        ("causal_inference", "interrupted_time_series"): ts_model("causal_inference", "interrupted_time_series", dependent="policy_rate", time_column="date", controls=["inflation_gap", "output_gap"], treatment_time=120),
        ("causal_inference", "regression_kink"): panel_model("causal_inference", "regression_kink", dependent="outcome_y", running_column="running_score", controls=["size", "leverage"], kink_point=0.0, bandwidth=1.5),
        ("causal_inference", "instrumental_causal"): panel_model("causal_inference", "instrumental_causal", dependent="outcome_y", controls=["size", "leverage"], endogenous_column="endogenous_x", instrument_columns=["instrument_z"]),
        ("causal_inference", "inverse_propensity_weighting"): panel_model("causal_inference", "inverse_propensity_weighting", dependent="outcome_y", treatment_column="treated", controls=["size", "leverage", "profitability"]),
        ("bayesian", "bayesian_linear_regression"): panel_model("bayesian", "bayesian_linear_regression", dependent="outcome_y", independents=["size", "leverage", "post"], draws=100, tune=100, chains=2),
        ("bayesian", "bayesian_panel"): panel_model("bayesian", "bayesian_panel", dependent="outcome_y", independents=["size", "leverage", "post"], entity_column="firm_id", time_column="calendar_year", draws=100, tune=100, chains=2),
        ("bayesian", "bayesian_did"): panel_model("bayesian", "bayesian_did", dependent="outcome_y", treatment_column="treated", post_column="post", controls=["size", "leverage"], draws=100, tune=100, chains=2),
        ("bayesian", "bayesian_its"): ts_model("bayesian", "bayesian_its", dependent="policy_rate", time_column="date", treatment_index=120, draws=100, tune=100, chains=2),
        ("quant_research", "quant_linear_model"): ts_model("quant_research", "quant_linear_model", dependent="asset_return", feature_columns=features, time_column="date", split_ratio=0.7),
        ("quant_research", "quant_lightgbm"): ts_model("quant_research", "quant_lightgbm", dependent="asset_return", feature_columns=features, time_column="date", split_ratio=0.7, n_estimators=120, learning_rate=0.05, num_leaves=15),
        ("quant_research", "quant_backtest_report"): ts_model("quant_research", "quant_backtest_report", dependent="asset_return", feature_columns=features, time_column="date", split_ratio=0.7),
        ("quant_research", "quant_catboost"): ts_model("quant_research", "quant_catboost", dependent="asset_return", feature_columns=features, time_column="date", split_ratio=0.7, iterations=120, depth=6, learning_rate=0.05),
        ("quant_research", "position_analysis"): ts_model("quant_research", "position_analysis", dependent="asset_return", feature_columns=features, time_column="date", split_ratio=0.7),
    }


def target_pairs_for_families(families: set[str] | None = None) -> list[tuple[str, str]]:
    pairs = scan_catalog_pairs()
    return [pair for pair in pairs if not families or pair[0] in families]


def load_manifest() -> dict[str, Any]:
    return read_json(MANIFEST_PATH, {"base_url": BASE_URL, "result_root": str(RESULT_ROOT), "started_at": utc_now(), "updated_at": utc_now(), "completed": [], "failed": [], "skipped_existing": []})


def index_manifest_entries(entries: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(item["family"]), str(item["method"])): item for item in entries}


def write_summary(session_state: dict[str, Any], manifest: dict[str, Any]) -> None:
    completed = scan_saved_pairs()
    catalog_pairs = scan_catalog_pairs()
    missing = sorted(pair for pair in catalog_pairs if pair not in completed)
    family_counts: dict[str, dict[str, int]] = {}
    for family, method in catalog_pairs:
        family_counts.setdefault(family, {"catalog_total": 0, "saved_total": 0, "missing_total": 0})
        family_counts[family]["catalog_total"] += 1
        if (family, method) in completed:
            family_counts[family]["saved_total"] += 1
        else:
            family_counts[family]["missing_total"] += 1
    write_json(
        SUMMARY_PATH,
        {
            "base_url": BASE_URL,
            "workspace_id": session_state.get("workspace_id"),
            "panel_asset_id": session_state.get("panel_asset_id"),
            "ts_asset_id": session_state.get("ts_asset_id"),
            "catalog_total": len(catalog_pairs),
            "saved_total": len(completed),
            "missing_total": len(missing),
            "missing": [{"family": family, "method": method} for family, method in missing],
            "family_counts": family_counts,
            "manifest_completed_total": len(manifest.get("completed", [])),
            "manifest_failed_total": len(manifest.get("failed", [])),
            "updated_at": utc_now(),
        },
    )


def assert_extra_contract(family: str, method: str, result: dict[str, Any]) -> None:
    if family == "asset_pricing" and method in {"traded_factor_model", "linear_factor_gmm"}:
        tables = result.get("tables") or {}
        if not {"risk_premia_table", "alpha_table", "beta_table"}.issubset(set(tables)):
            raise AssertionError(f"{family}/{method}: missing required asset-pricing tables")


def run_batch(families: set[str] | None, fresh_session: bool) -> int:
    session_state = create_session_state(fresh=fresh_session)
    manifest = load_manifest()
    manifest["workspace_id"] = session_state["workspace_id"]
    manifest["panel_asset_id"] = session_state["panel_asset_id"]
    manifest["ts_asset_id"] = session_state["ts_asset_id"]
    manifest["updated_at"] = utc_now()

    completed_index = index_manifest_entries(manifest.get("completed", []))
    failed_index = index_manifest_entries(manifest.get("failed", []))
    skipped_index = index_manifest_entries(manifest.get("skipped_existing", []))
    spec_map = build_spec_map(session_state["panel_asset_id"], session_state["ts_asset_id"])
    saved_pairs = scan_saved_pairs()
    run_pairs = [pair for pair in target_pairs_for_families(families) if pair in spec_map]

    session = BaseUrlSession(BASE_URL)
    token = login(session)
    headers = {**auth_headers(token), "Content-Type": "application/json"}
    completed_this_run = 0
    failed_this_run = 0

    for index, (family, method) in enumerate(run_pairs, start=1):
        output_dir = RESULT_ROOT / spec_map[(family, method)]["group"] / "models" / family / method / "baseline"
        if (family, method) in saved_pairs and output_dir.exists() and (family, method) not in failed_index:
            skipped_index[(family, method)] = {"family": family, "method": method, "path": str(output_dir), "status": "already_saved", "updated_at": utc_now()}
            continue

        label = f"{family}/{method}"
        print(f"[{index}/{len(run_pairs)}] Running {label}", flush=True)
        try:
            response = session.post(
                f"{BASE_URL}/api/workspaces/{session_state['workspace_id']}/analysis/models",
                headers=headers,
                json=spec_map[(family, method)]["payload"],
                timeout=1800,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"{response.status_code} {response.text[:1000]}")
            record_id = response.json().get("result_record_id")
            if not record_id:
                raise RuntimeError("missing result_record_id")
            detail = session.get(f"{BASE_URL}/api/data-lab/results/models/{record_id}", headers=auth_headers(token), timeout=180)
            detail.raise_for_status()
            detail_payload = detail.json()
            result = detail_payload.get("result", {})
            result["_record_id"] = record_id
            _assert_model_output(label, result)
            assert_extra_contract(family, method, result)
            _save_result_bundle(session, token, detail_payload, output_dir)
            completed_index[(family, method)] = {"family": family, "method": method, "record_id": record_id, "path": str(output_dir), "workspace_id": session_state["workspace_id"], "updated_at": utc_now()}
            failed_index.pop((family, method), None)
            completed_this_run += 1
            print(f"  OK  -> {output_dir}", flush=True)
        except Exception as exc:
            failed_index[(family, method)] = {"family": family, "method": method, "path": str(output_dir), "workspace_id": session_state["workspace_id"], "error": str(exc), "traceback": traceback.format_exc(), "updated_at": utc_now()}
            failed_this_run += 1
            print(f"  FAIL -> {exc}", flush=True)

        manifest["completed"] = list(completed_index.values())
        manifest["failed"] = list(failed_index.values())
        manifest["skipped_existing"] = list(skipped_index.values())
        manifest["updated_at"] = utc_now()
        write_json(MANIFEST_PATH, manifest)
        write_summary(session_state, manifest)

    manifest["completed"] = list(completed_index.values())
    manifest["failed"] = list(failed_index.values())
    manifest["skipped_existing"] = list(skipped_index.values())
    manifest["updated_at"] = utc_now()
    write_json(MANIFEST_PATH, manifest)
    write_summary(session_state, manifest)

    print(json.dumps({"workspace_id": session_state["workspace_id"], "completed_this_run": completed_this_run, "failed_this_run": failed_this_run, "manifest_path": str(MANIFEST_PATH), "summary_path": str(SUMMARY_PATH)}, ensure_ascii=False, indent=2), flush=True)
    return failed_this_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the missing Data Lab model methods and save result bundles.")
    parser.add_argument("--families", default="", help="Comma-separated family slugs to run. Default: all missing families.")
    parser.add_argument("--fresh-session", action="store_true", help="Create a new workspace and upload fresh assets.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    families = {item.strip() for item in args.families.split(",") if item.strip()} or None
    return run_batch(families=families, fresh_session=bool(args.fresh_session))


if __name__ == "__main__":
    raise SystemExit(main())
