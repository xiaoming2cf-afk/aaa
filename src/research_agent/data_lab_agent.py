from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import uuid
from typing import Any

os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd
from sqlalchemy.orm import Session

from .agent_math import (
    build_data_lab_repair_decision,
    rank_retrieval_candidates,
    settings_math_mode,
)
from .asset_storage import load_asset_bytes
from .config import Settings
from .data_lab_catalog import get_data_lab_catalog
from .data_lab_agent_llm import (
    AgentLLMClient,
    AgentLLMError,
    get_agent_llm_config,
    resolve_agent_llm_config,
    test_agent_llm_config,
    update_agent_llm_config,
)
from .entities import DataAsset, DataLabRun, User, Workspace
from .platform_core import (
    DATASET_KINDS,
    create_data_lab_run,
    list_knowledge_records,
    load_dataset_frame,
    serialize_asset,
)
from .team_library import list_team_library_records
from .utils import truncate_text


AGENT_WORKFLOW_TYPE = "agent_session"
AGENT_FAMILY = "data_lab_agent"
AGENT_METHOD = "trusted_python_execution"
_DEFAULT_ARTIFACT_MAX_COUNT = 20
_DEFAULT_ARTIFACT_MAX_BYTES = 25 * 1024 * 1024

_BLOCKED_IMPORT_ROOTS = {
    "builtins",
    "conda",
    "ftplib",
    "glob",
    "http",
    "importlib",
    "os",
    "pathlib",
    "pip",
    "requests",
    "shutil",
    "site",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}
_ALLOWED_IMPORT_ROOTS = {
    "arviz",
    "arch",
    "catboost",
    "causalpy",
    "json",
    "lightgbm",
    "math",
    "matplotlib",
    "numpy",
    "pandas",
    "pymc",
    "scipy",
    "seaborn",
    "sklearn",
    "statistics",
    "statsmodels",
}
_BLOCKED_CALLS = {
    "__import__",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_BLOCKED_ATTRS = {
    "chmod",
    "chown",
    "environ",
    "makedirs",
    "popen",
    "read_bytes",
    "read_text",
    "read_csv",
    "read_excel",
    "read_feather",
    "read_fwf",
    "read_hdf",
    "read_json",
    "read_orc",
    "read_parquet",
    "read_pickle",
    "read_sas",
    "read_spss",
    "read_sql",
    "read_stata",
    "read_table",
    "remove",
    "removedirs",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "savefig",
    "system",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_hdf",
    "to_json",
    "to_orc",
    "to_parquet",
    "to_pickle",
    "to_sql",
    "to_stata",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
_BLOCKED_TEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(^|\n)\s*![a-z]",
        r"\bpip\s+install\b",
        r"\bconda\s+install\b",
        r"\bcurl\s+",
        r"\bwget\s+",
        r"\bpowershell\b",
        r"\bcmd\.exe\b",
    ]
]
_COMMON_WORDS = {
    "column",
    "columns",
    "describe",
    "distribution",
    "histogram",
    "missing",
    "plot",
    "preview",
    "regression",
    "scatter",
    "show",
    "summary",
}


class SafetyViolation(ValueError):
    """Raised when user-provided code crosses the Data Lab execution policy."""


class DataLabAgentFeatureDisabled(PermissionError):
    """Raised when the Data Lab Agent feature flag is off."""


class DataLabTrustedExecutionDisabled(PermissionError):
    """Raised when local Python execution has not been explicitly trusted."""


class DataLabExecutionPolicyError(ValueError):
    def __init__(self, message: str, *, error_type: str) -> None:
        super().__init__(message)
        self.error_type = error_type


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return str(value)


def _agent_root(settings: Settings) -> Path:
    root = (settings.storage_dir / "data_lab_agent").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _session_work_dir(settings: Settings, run_id: str) -> Path:
    root = _agent_root(settings)
    work_dir = (root / run_id).resolve()
    if root not in work_dir.parents and work_dir != root:
        raise ValueError("Invalid Data Lab Agent session path.")
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "inputs").mkdir(exist_ok=True)
    (work_dir / "outputs").mkdir(exist_ok=True)
    (work_dir / "execution").mkdir(exist_ok=True)
    return work_dir


def _safe_input_filename(asset: DataAsset) -> str:
    suffix = Path(asset.title or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls", ".json"}:
        suffix = ".csv" if asset.kind == "dataset_csv" else ".json"
    return f"{asset.id}{suffix}"


def _dataset_asset_or_raise(db: Session, *, user: User, workspace: Workspace, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")
    if asset.kind not in DATASET_KINDS:
        raise ValueError("Data Lab Agent sessions only accept structured dataset assets.")
    return asset


def _profile_frame(frame: pd.DataFrame, *, asset: DataAsset, local_path: Path) -> dict[str, Any]:
    roles: dict[str, list[str]] = {"numeric": [], "date": [], "categorical": [], "text": [], "empty": []}
    columns_detail: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        column_name = str(column)
        role = _infer_column_role(series, column_name)
        roles.setdefault(role, []).append(column_name)
        columns_detail.append(_profile_column(series, name=column_name, role=role, row_count=len(frame)))
    preview = frame.head(6).where(pd.notna(frame.head(6)), None).to_dict(orient="records")
    quality_warnings = _profile_quality_warnings(frame, columns_detail)
    candidate_targets = _candidate_target_columns(frame, roles)
    candidate_features = [
        column
        for column in [str(item) for item in frame.columns]
        if column not in set(candidate_targets) and column not in set(roles.get("empty") or [])
    ][:30]
    schema_fingerprint = _schema_fingerprint(frame)
    return _json_safe(
        {
            "profile_version": 2,
            "asset_id": asset.id,
            "title": asset.title,
            "kind": asset.kind,
            "local_path": str(local_path),
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "column_names": [str(column) for column in frame.columns],
            "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
            "missing_by_column": {str(column): int(value) for column, value in frame.isna().sum().to_dict().items()},
            "roles": roles,
            "columns_detail": columns_detail,
            "candidate_targets": candidate_targets,
            "candidate_features": candidate_features,
            "quality_warnings": quality_warnings,
            "schema_fingerprint": schema_fingerprint,
            "preview_rows": preview,
            "suggested_models": _suggest_models(roles),
        }
    )


def _schema_fingerprint(frame: pd.DataFrame) -> str:
    schema = [{"name": str(column), "dtype": str(dtype)} for column, dtype in frame.dtypes.items()]
    return hashlib.sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _infer_column_role(series: pd.Series, column_name: str) -> str:
    if series.notna().sum() == 0:
        return "empty"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    lowered = column_name.lower()
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    if any(token in lowered for token in ["date", "time", "year", "month", "day"]):
        parsed = pd.to_datetime(non_null.head(80), errors="coerce")
        if parsed.notna().mean() >= 0.75:
            return "date"
    median_length = non_null.astype(str).str.len().median()
    unique_ratio = float(non_null.nunique(dropna=True)) / max(1, int(non_null.shape[0]))
    if median_length > 60 or (unique_ratio > 0.8 and non_null.shape[0] > 30):
        return "text"
    return "categorical"


def _profile_column(series: pd.Series, *, name: str, role: str, row_count: int) -> dict[str, Any]:
    non_null = series.dropna()
    detail: dict[str, Any] = {
        "name": name,
        "dtype": str(series.dtype),
        "role": role,
        "missing_count": int(series.isna().sum()),
        "missing_rate": round(float(series.isna().mean()), 4) if row_count else 0,
        "unique_count": int(non_null.nunique(dropna=True)),
        "unique_rate": round(float(non_null.nunique(dropna=True)) / max(1, int(non_null.shape[0])), 4),
        "examples": [str(value) for value in non_null.head(4).tolist()],
    }
    if role == "numeric":
        detail["numeric_summary"] = _numeric_column_summary(series)
    elif role == "date":
        detail["date_summary"] = _date_column_summary(series)
    elif role in {"categorical", "text"}:
        values = non_null.astype(str).value_counts().head(6)
        detail["top_values"] = [{"value": str(index), "count": int(value)} for index, value in values.items()]
    return detail


def _numeric_column_summary(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {}
    quantiles = numeric.quantile([0.25, 0.5, 0.75])
    q1 = float(quantiles.loc[0.25])
    q3 = float(quantiles.loc[0.75])
    iqr = q3 - q1
    outlier_count = 0
    if iqr > 0:
        outlier_count = int(((numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)).sum())
    return {
        "mean": float(numeric.mean()),
        "std": float(numeric.std()) if len(numeric) > 1 else 0.0,
        "min": float(numeric.min()),
        "q1": q1,
        "median": float(quantiles.loc[0.5]),
        "q3": q3,
        "max": float(numeric.max()),
        "skew": float(numeric.skew()) if len(numeric) > 2 else 0.0,
        "outlier_count": outlier_count,
    }


def _date_column_summary(series: pd.Series) -> dict[str, Any]:
    parsed = pd.to_datetime(series, errors="coerce").dropna().sort_values()
    if parsed.empty:
        return {}
    deltas = parsed.diff().dropna()
    median_delta = str(deltas.median()) if not deltas.empty else ""
    return {
        "min": parsed.iloc[0].isoformat(),
        "max": parsed.iloc[-1].isoformat(),
        "median_delta": median_delta,
        "non_null_count": int(parsed.shape[0]),
    }


def _profile_quality_warnings(frame: pd.DataFrame, columns_detail: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if frame.empty:
        warnings.append("Dataset has no rows.")
    duplicate_rows = int(frame.duplicated().sum()) if not frame.empty else 0
    if duplicate_rows:
        warnings.append(f"Dataset contains {duplicate_rows} duplicate row(s).")
    for detail in columns_detail:
        missing_rate = float(detail.get("missing_rate") or 0)
        if missing_rate >= 0.5:
            warnings.append(f"Column {detail.get('name')} is missing at least 50% of values.")
        numeric_summary = detail.get("numeric_summary") or {}
        if int(numeric_summary.get("outlier_count") or 0) > 0:
            warnings.append(f"Column {detail.get('name')} has potential numeric outliers.")
    return warnings[:12]


def _candidate_target_columns(frame: pd.DataFrame, roles: dict[str, list[str]]) -> list[str]:
    columns = [str(column) for column in frame.columns]
    priority_tokens = ["target", "label", "outcome", "y", "dependent", "response", "结果", "目标"]
    candidates = [
        column
        for column in columns
        if any(token == column.lower() or (len(token) > 1 and token in column.lower()) for token in priority_tokens)
        and column not in set(roles.get("empty") or [])
    ]
    if candidates:
        return candidates[:5]
    numeric = roles.get("numeric") or []
    return numeric[:1]


def _suggest_models(roles: dict[str, list[str]]) -> list[str]:
    suggestions = ["summary_statistics"]
    if roles.get("numeric"):
        suggestions.extend(["correlation", "ols", "histogram"])
    if len(roles.get("numeric", [])) >= 2:
        suggestions.append("scatter_plot")
    if roles.get("date") and roles.get("numeric"):
        suggestions.extend(["time_series_plot", "arima"])
    if roles.get("categorical") and roles.get("numeric"):
        suggestions.append("group_summary")
    return list(dict.fromkeys(suggestions))


def _bootstrap_code(session: dict[str, Any]) -> str:
    assets = session.get("assets") or []
    asset_paths = {str(item["asset_id"]): str(item["local_path"]) for item in assets if item.get("asset_id")}
    first_asset_id = str(assets[0]["asset_id"]) if assets else ""
    return textwrap.dedent(
        f"""
        import json
        from pathlib import Path
        import numpy as np
        import pandas as pd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        WORK_DIR = Path({str(session.get("work_dir", ""))!r})
        INPUT_DIR = WORK_DIR / "inputs"
        OUTPUT_DIR = WORK_DIR / "outputs"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        asset_paths = {asset_paths!r}
        datasets = {{}}
        for asset_id, raw_path in asset_paths.items():
            path = Path(raw_path)
            suffix = path.suffix.lower()
            if suffix == ".csv":
                datasets[asset_id] = pd.read_csv(path)
            elif suffix in {{".xlsx", ".xls"}}:
                datasets[asset_id] = pd.read_excel(path)
            elif suffix == ".json":
                datasets[asset_id] = pd.read_json(path)
        df = datasets[{first_asset_id!r}] if {first_asset_id!r} in datasets else next(iter(datasets.values()))
        """
    ).strip()


def _session_from_run(run: DataLabRun) -> dict[str, Any]:
    payload = dict(run.output_json or {}) if isinstance(run.output_json, dict) else {}
    session = payload.get("agent_session")
    if not isinstance(session, dict):
        raise FileNotFoundError("Data Lab Agent session state was not found.")
    return dict(session)


def _assign_session(run: DataLabRun, session: dict[str, Any]) -> None:
    run.output_json = _json_safe(
        {
            "workflow_type": AGENT_WORKFLOW_TYPE,
            "summary": session.get("summary", ""),
            "detail_path": session.get("detail_path", ""),
            "agent_session": session,
        }
    )
    run.summary = truncate_text(str(session.get("summary") or ""), 600)
    run.detail_path = str(session.get("detail_path") or "")
    run.status = str(session.get("run_status") or "ready")
    run.updated_at = datetime.now(timezone.utc)


def _run_or_raise(db: Session, *, user: User, workspace: Workspace, run_id: str) -> DataLabRun:
    run = db.get(DataLabRun, run_id)
    if not run or run.owner_user_id != user.id or run.workspace_id != workspace.id:
        raise FileNotFoundError("Data Lab Agent session not found.")
    if run.workflow_type != AGENT_WORKFLOW_TYPE:
        raise FileNotFoundError("Data Lab Agent session not found.")
    return run


def _require_enabled(settings: Settings) -> None:
    if not settings.data_lab_agent_enabled:
        raise DataLabAgentFeatureDisabled("Data Lab Agent is disabled. Set DATA_LAB_AGENT_ENABLED=true to enable it.")


def _recent_failure_classes(session: dict[str, Any]) -> list[str]:
    classes: list[str] = []
    for message in session.get("messages") or []:
        trace = (message.get("math_trace") or {}).get("repair_decisions") or []
        for item in trace:
            if not isinstance(item, dict):
                continue
            error_class = str(item.get("error_class") or "").strip()
            if error_class:
                classes.append(error_class)
    return classes[-6:]


def _data_lab_internal_math_state(
    session: dict[str, Any],
    *,
    instruction: str = "",
    requested_execution_mode: str = "",
    status: str = "",
) -> dict[str, Any]:
    assets = list(session.get("assets") or [])
    profile = dict((assets[0] or {}).get("profile") or {}) if assets else {}
    successful_cells = [cell for cell in (session.get("cells") or []) if str(cell.get("status") or "") == "success"]
    artifacts = [artifact for cell in successful_cells for artifact in (cell.get("artifacts") or [])]
    artifact_names = [
        str(artifact.get("name") or artifact.get("relative_path") or "")
        for artifact in artifacts
        if str(artifact.get("name") or artifact.get("relative_path") or "").strip()
    ]
    human_intervention_count = sum(
        1
        for message in session.get("messages") or []
        if isinstance(message.get("human_intervention"), dict) and (message.get("human_intervention") or {}).get("provided")
    )
    return {
        "W_t": {
            "instruction": truncate_text(instruction or str(((session.get("messages") or [{}])[-1] or {}).get("content") or ""), 500),
            "requested_execution_mode": requested_execution_mode or str((session.get("executor") or {}).get("requested_mode") or ""),
            "dataset_fingerprint": str(profile.get("schema_fingerprint") or ""),
        },
        "M_t": {
            "successful_cell_count": len(successful_cells),
            "recent_failure_classes": _recent_failure_classes(session),
            "artifact_names_recent": artifact_names[-10:],
            "human_intervention_count": human_intervention_count,
        },
        "C_t": {
            "safety_event_count": len(session.get("safety_events") or []),
            "active_mode": str((session.get("executor") or {}).get("active_mode") or ""),
            "llm_ready": bool((session.get("llm") or {}).get("ready")),
        },
        "E_t": {
            "profile_snapshot_count": len(session.get("profile_snapshots") or []),
            "last_schema_fingerprint": str(profile.get("schema_fingerprint") or ""),
            "run_status": status or str(session.get("run_status") or ""),
        },
    }


def _public_math_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    memory = dict(state.get("M_t") or {})
    constraints = dict(state.get("C_t") or {})
    evaluation = dict(state.get("E_t") or {})
    working = dict(state.get("W_t") or {})
    return {
        "instruction": working.get("instruction", ""),
        "requested_execution_mode": working.get("requested_execution_mode", ""),
        "dataset_fingerprint": working.get("dataset_fingerprint", ""),
        "successful_cell_count": int(memory.get("successful_cell_count") or 0),
        "recent_failure_classes": list(memory.get("recent_failure_classes") or []),
        "human_intervention_count": int(memory.get("human_intervention_count") or 0),
        "safety_event_count": int(constraints.get("safety_event_count") or 0),
        "profile_snapshot_count": int(evaluation.get("profile_snapshot_count") or 0),
        "run_status": str(evaluation.get("run_status") or ""),
    }


class DataLabKnowledgeResolver:
    def resolve(
        self,
        db: Session,
        *,
        user: User,
        workspace: Workspace,
        instruction: str,
        session: dict[str, Any],
        mode: str = "off",
        override_margin: float = 0.05,
    ) -> dict[str, Any]:
        tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", instruction or "") if len(token) > 2}
        notes = []
        cards: list[dict[str, Any]] = []
        for record in list_knowledge_records(db, user=user, workspace=workspace)[:20]:
            haystack = f"{record.title} {record.content[:800]}".lower()
            score = _knowledge_score(tokens, haystack)
            if score > 0 or not tokens:
                note = {"id": record.id, "title": record.title, "excerpt": truncate_text(record.content, 260)}
                notes.append(note)
                cards.append(
                    self._card(
                        source_type="workspace_knowledge",
                        title=record.title,
                        summary=truncate_text(record.content, 520),
                        score=score or 1,
                        ref_id=record.id,
                        tags=[str(tag) for tag in (record.tags_json or [])[:8]],
                    )
                )
            if len(notes) >= 5:
                break
        catalog_summary, catalog_cards = self._catalog_summary(tokens)
        cards.extend(catalog_cards)
        cards.extend(self._team_library_cards(db, user=user, workspace=workspace, tokens=tokens))
        model_suggestions: list[str] = []
        for asset in session.get("assets") or []:
            model_suggestions.extend(asset.get("profile", {}).get("suggested_models") or [])
        cards.extend(self._method_cards(model_suggestions))
        ranked_cards, arbiter_trace = rank_retrieval_candidates(
            query_text=instruction,
            candidates=cards,
            session=session,
            limit=10,
            mode=mode,
            override_margin=override_margin,
        )
        return {
            "catalog": catalog_summary,
            "workspace_notes": notes,
            "suggested_methods": list(dict.fromkeys(model_suggestions))[:12],
            "cards": ranked_cards,
            "arbiter": arbiter_trace,
        }

    def _catalog_summary(self, tokens: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            catalog = get_data_lab_catalog()
        except Exception:
            return {"processing_families": [], "model_families": []}, []
        processing = catalog.get("processing_families") or catalog.get("processing") or []
        models = catalog.get("model_families") or catalog.get("models") or []
        cards: list[dict[str, Any]] = []
        for group_name, rows in (("processing_catalog", processing), ("model_catalog", models)):
            for item in rows[:18]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("label") or item.get("title") or item.get("name") or item.get("slug") or "").strip()
                summary = str(item.get("description") or item.get("summary") or "").strip()
                haystack = f"{title} {summary}".lower()
                score = _knowledge_score(tokens, haystack)
                if score > 0 or not tokens:
                    cards.append(
                        self._card(
                            source_type=group_name,
                            title=title,
                            summary=summary or "Data Lab catalog capability.",
                            score=score or 1,
                            ref_id=str(item.get("slug") or title),
                            tags=[group_name.replace("_catalog", "")],
                            interface={"slug": item.get("slug", ""), "kind": group_name},
                        )
                    )
        return {
            "processing_families": [str((item or {}).get("label") or (item or {}).get("title") or (item or {}).get("name") or "") for item in processing[:8] if isinstance(item, dict)],
            "model_families": [str((item or {}).get("label") or (item or {}).get("title") or (item or {}).get("name") or "") for item in models[:10] if isinstance(item, dict)],
        }, cards

    def _method_cards(self, model_suggestions: list[str]) -> list[dict[str, Any]]:
        cards = []
        for index, method in enumerate(list(dict.fromkeys(model_suggestions))[:8]):
            cards.append(
                self._card(
                    source_type="method_hint",
                    title=str(method),
                    summary="Suggested by the current dataset profile; use through Data Lab Agent code, not copied external implementation.",
                    score=max(1, 8 - index),
                    ref_id=str(method),
                    tags=["profile", "method"],
                    interface={"method": str(method)},
                )
            )
        return cards

    def _team_library_cards(
        self,
        db: Session,
        *,
        user: User,
        workspace: Workspace,
        tokens: set[str],
    ) -> list[dict[str, Any]]:
        team_id = str(getattr(workspace, "team_id", "") or "").strip()
        if not team_id:
            return []
        cards: list[dict[str, Any]] = []
        try:
            records = list_team_library_records(db, user=user, team_id=team_id)
        except Exception:
            return []
        for record in records[:12]:
            haystack = f"{record.title} {record.summary} {record.content[:600]}".lower()
            score = _knowledge_score(tokens, haystack)
            if score <= 0 and tokens:
                continue
            cards.append(
                self._card(
                    source_type="team_library",
                    title=record.title,
                    summary=truncate_text(record.summary or record.content, 520),
                    score=score or 1,
                    ref_id=record.id,
                    tags=[str(record.source_type or "team")],
                )
            )
        return cards[:5]

    def _card(
        self,
        *,
        source_type: str,
        title: str,
        summary: str,
        score: int,
        ref_id: str = "",
        tags: list[str] | None = None,
        interface: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": f"{source_type}:{ref_id or hashlib.sha1(title.encode('utf-8')).hexdigest()[:10]}",
            "source_type": source_type,
            "title": title or source_type,
            "summary": truncate_text(summary, 620),
            "score": int(score),
            "tags": tags or [],
            "interface": interface or {},
            "policy": "interface_only_no_external_source_injection",
        }


def _knowledge_score(tokens: set[str], text: str) -> int:
    if not tokens:
        return 1
    lowered = text.lower()
    return sum(1 for token in tokens if token and token in lowered)


def _code_plan(
    code: str,
    *,
    source: str,
    explanation: str,
    risk_notes: Any = None,
    llm_error: str = "",
    patch_intent: str = "",
) -> dict[str, Any]:
    notes = risk_notes if isinstance(risk_notes, list) else []
    return {
        "code": str(code or "").strip(),
        "source": source,
        "explanation": truncate_text(explanation, 800),
        "risk_notes": [truncate_text(str(item), 240) for item in notes[:6]],
        "llm_error": truncate_text(llm_error, 600),
        "patch_intent": truncate_text(patch_intent, 500),
    }


def _plan_trace(role: str, plan: dict[str, Any], llm_config: Any) -> dict[str, Any]:
    source = str(plan.get("source") or "")
    return {
        "role": role,
        "source": source,
        "model": llm_config.model_for_role("reviewer" if role == "reviewer" else "coder") if source.startswith("llm") and getattr(llm_config, "ready", False) else "",
        "fallback": source.endswith("fallback"),
        "llm_error": plan.get("llm_error", ""),
        "summary": truncate_text(str(plan.get("explanation") or plan.get("patch_intent") or ""), 360),
    }


def _diagnosis_trace(role: str, diagnosis: dict[str, Any], llm_config: Any) -> dict[str, Any]:
    source = str(diagnosis.get("source") or "")
    return {
        "role": role,
        "source": source,
        "model": llm_config.model_for_role("reviewer") if source.startswith("llm") and getattr(llm_config, "ready", False) else "",
        "fallback": source.endswith("fallback"),
        "llm_error": diagnosis.get("llm_error", ""),
        "summary": truncate_text(str(diagnosis.get("repair_strategy") or diagnosis.get("suggestion") or ""), 360),
    }


def _clean_llm_code(value: Any) -> str:
    code = str(value or "").strip()
    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", code)
        code = re.sub(r"\s*```$", "", code)
    return code.strip()


def _coder_instructions(session: dict[str, Any]) -> str:
    language = str(session.get("language") or "Chinese")
    return (
        "You are the Data Lab Agent analysis coder. Produce original, safe Python for an already-loaded pandas "
        "workspace. The variables datasets, df, WORK_DIR, INPUT_DIR, OUTPUT_DIR, pd, np, plt are already available. "
        "Do not use shell commands, network access, package installation, environment variables, or arbitrary file reads or writes. "
        "Prefer concise code that prints interpretable intermediate results and creates matplotlib plots for automatic capture. "
        f"Reply in {language} explanations, but return only JSON with keys code, explanation, risk_notes."
    )


def _repair_instructions(session: dict[str, Any]) -> str:
    language = str(session.get("language") or "Chinese")
    return (
        "You are the Data Lab Agent code repairer. Given a failed Python cell, error text, and reviewer suggestion, "
        "return a safer corrected cell that can run in the same pandas workspace. Preserve the user's analytical intent "
        "when possible, but prefer a robust fallback summary over brittle column guesses. Do not use shell commands, "
        "network access, package installation, environment variables, or arbitrary file reads. "
        f"Reply in {language} explanations, but return only JSON with keys code, explanation, patch_intent, risk_notes."
    )


def _reviewer_instructions(session: dict[str, Any]) -> str:
    language = str(session.get("language") or "Chinese")
    return (
        "You are the Data Lab Agent execution reviewer. Diagnose why a Python data-analysis cell failed and propose "
        "one concrete repair strategy. Do not ask for external packages, shell commands, network calls, or file reads. "
        f"Write the suggestion in {language}. Return only JSON with keys error_type, suggestion, repair_strategy."
    )


def _report_instructions(session: dict[str, Any]) -> str:
    language = str(session.get("language") or "Chinese")
    return (
        "You are the Data Lab Agent report narrator. Summarize only the evidence that appears in this session payload: "
        "dataset profiles, executed code summaries, printed outputs, artifacts, repair events, and human interventions. "
        "Do not invent findings. Return only JSON with key summary. "
        f"Write the summary in {language}."
    )


def _report_payload(session: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "title": session.get("title"),
            "assets": [
                {
                    "title": asset.get("title"),
                    "profile": asset.get("profile"),
                }
                for asset in session.get("assets") or []
            ],
            "steps": [
                {
                    "status": message.get("status"),
                    "content": message.get("content"),
                    "stdout": truncate_text(str((message.get("execution") or {}).get("stdout") or ""), 1600),
                    "artifact_manifest": message.get("artifact_manifest") or {},
                    "repair_trace": message.get("repair_trace") or [],
                    "human_intervention": message.get("human_intervention") or {},
                }
                for message in session.get("messages") or []
                if message.get("role") == "assistant"
            ],
        }
    )


def _coder_payload(
    *,
    instruction: str,
    session: dict[str, Any],
    knowledge: dict[str, Any],
    failure_context: dict[str, Any] | None,
) -> dict[str, Any]:
    recent_cells = [
        {
            "code": truncate_text(str(cell.get("code") or ""), 1600),
            "stdout": truncate_text(str(cell.get("stdout") or ""), 1000),
            "artifacts": cell.get("artifacts") or [],
        }
        for cell in (session.get("cells") or [])[-5:]
    ]
    return _json_safe(
        {
            "instruction": instruction,
            "datasets": [
                {
                    "title": asset.get("title"),
                    "asset_id": asset.get("asset_id"),
                    "profile": asset.get("profile"),
                }
                for asset in session.get("assets") or []
            ],
            "knowledge_cards": knowledge.get("cards") or [],
            "recent_successful_cells": recent_cells,
            "failure_context": failure_context or {},
            "output_contract": {
                "code": "single Python cell",
                "explanation": "brief plain-language rationale",
                "risk_notes": "list of safety or interpretation caveats",
            },
        }
    )


class AnalystCoder:
    def __init__(self, llm_client: AgentLLMClient | None = None) -> None:
        self.llm_client = llm_client

    def draft_plan(self, instruction: str, session: dict[str, Any], knowledge: dict[str, Any]) -> dict[str, Any]:
        if self.llm_client is not None:
            try:
                payload = self.llm_client.complete_json(
                    role="coder",
                    instructions=_coder_instructions(session),
                    input_payload=_coder_payload(
                        instruction=instruction,
                        session=session,
                        knowledge=knowledge,
                        failure_context=None,
                    ),
                    max_tokens=2200,
                )
                code = _clean_llm_code(payload.get("code"))
                if code:
                    return _code_plan(
                        code,
                        source="llm",
                        explanation=str(payload.get("explanation") or "LLM generated analysis code."),
                        risk_notes=payload.get("risk_notes"),
                    )
            except (AgentLLMError, ValueError, TypeError) as exc:
                return _code_plan(
                    self.draft(instruction, session, knowledge),
                    source="rules_fallback",
                    explanation="LLM coder was unavailable or returned unusable code; rule fallback generated the cell.",
                    llm_error=str(exc),
                )
        return _code_plan(
            self.draft(instruction, session, knowledge),
            source="rules",
            explanation="Rule-based analyst coder generated the cell.",
        )

    def repair_plan(
        self,
        *,
        instruction: str,
        failed_code: str,
        error_message: str,
        session: dict[str, Any],
        suggestion: str,
        knowledge: dict[str, Any],
    ) -> dict[str, Any]:
        if self.llm_client is not None:
            try:
                payload = self.llm_client.complete_json(
                    role="coder",
                    instructions=_repair_instructions(session),
                    input_payload=_coder_payload(
                        instruction=instruction,
                        session=session,
                        knowledge=knowledge,
                        failure_context={
                            "failed_code": truncate_text(failed_code, 5000),
                            "error_message": truncate_text(error_message, 2400),
                            "reviewer_suggestion": truncate_text(suggestion, 1200),
                        },
                    ),
                    max_tokens=2400,
                )
                code = _clean_llm_code(payload.get("code"))
                if code:
                    return _code_plan(
                        code,
                        source="llm",
                        explanation=str(payload.get("explanation") or "LLM repaired the analysis code."),
                        risk_notes=payload.get("risk_notes"),
                        patch_intent=str(payload.get("patch_intent") or ""),
                    )
            except (AgentLLMError, ValueError, TypeError) as exc:
                return _code_plan(
                    self.repair(
                        instruction=instruction,
                        failed_code=failed_code,
                        error_message=error_message,
                        session=session,
                        suggestion=suggestion,
                    ),
                    source="rules_fallback",
                    explanation="LLM repair was unavailable or returned unusable code; rule fallback repaired the cell.",
                    llm_error=str(exc),
                    patch_intent="fallback_repair",
                )
        return _code_plan(
            self.repair(
                instruction=instruction,
                failed_code=failed_code,
                error_message=error_message,
                session=session,
                suggestion=suggestion,
            ),
            source="rules",
            explanation="Rule-based reviewer suggestion was applied.",
            patch_intent="rule_repair",
        )

    def draft(self, instruction: str, session: dict[str, Any], knowledge: dict[str, Any]) -> str:
        del knowledge
        lower = instruction.lower()
        profile = self._primary_profile(session)
        numeric = profile.get("roles", {}).get("numeric") or []
        if any(keyword in lower for keyword in ["corr", "correlation", "相关"]):
            return self._correlation_code(numeric)
        if any(keyword in lower for keyword in ["hist", "distribution", "分布", "直方图"]):
            column = self._requested_column(instruction, profile) or (numeric[0] if numeric else "")
            return self._histogram_code(column)
        if any(keyword in lower for keyword in ["scatter", "relationship", "散点"]):
            return self._scatter_code(numeric)
        if any(keyword in lower for keyword in ["regression", "ols", "回归"]):
            return self._ols_code(numeric)
        if re.search(r"\b(missing|null|na)\b", lower) or "缺失" in lower:
            return self._missing_code()
        if any(keyword in lower for keyword in ["head", "preview", "sample", "前几", "预览"]):
            return "print(df.head(10).to_string(index=False))"
        if any(keyword in lower for keyword in ["describe", "summary", "统计", "概览"]):
            return self._describe_code()
        return self._overview_code()

    def repair(self, *, instruction: str, failed_code: str, error_message: str, session: dict[str, Any], suggestion: str) -> str:
        del failed_code, suggestion
        lower_error = error_message.lower()
        profile = self._primary_profile(session)
        numeric = profile.get("roles", {}).get("numeric") or []
        if "keyerror" in lower_error or "not in index" in lower_error:
            return self._column_fallback_code(profile)
        if "no numeric" in lower_error or "could not convert" in lower_error:
            return self._describe_code()
        if "statsmodels" in lower_error or "singular" in lower_error or "exog" in lower_error:
            return self._correlation_code(numeric)
        if any(keyword in instruction.lower() for keyword in ["hist", "distribution", "分布"]):
            return self._histogram_code(numeric[0] if numeric else "")
        return self._overview_code()

    def _primary_profile(self, session: dict[str, Any]) -> dict[str, Any]:
        assets = session.get("assets") or []
        if not assets:
            return {"roles": {}, "column_names": []}
        return dict((assets[0] or {}).get("profile") or {})

    def _requested_column(self, instruction: str, profile: dict[str, Any]) -> str:
        columns = [str(column) for column in profile.get("column_names") or []]
        lowered = instruction.lower()
        quoted = []
        for match in re.findall(r"`([^`]+)`|'([^']+)'|\"([^\"]+)\"", instruction):
            quoted.extend(item for item in match if item)
        for item in quoted:
            return item.strip()
        for column in columns:
            if column.lower() in lowered:
                return column
        for pattern in [r"\bcolumn\s+([A-Za-z_][A-Za-z0-9_]*)", r"\bof\s+([A-Za-z_][A-Za-z0-9_]*)"]:
            match = re.search(pattern, instruction, re.IGNORECASE)
            if match:
                return match.group(1)
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", instruction):
            if token.lower() not in _COMMON_WORDS and "_" in token:
                return token
        return ""

    def _overview_code(self) -> str:
        return textwrap.dedent(
            """
            print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
            print("Columns:")
            print(", ".join(str(column) for column in df.columns))
            print("\\nDtypes:")
            print(df.dtypes.astype(str).to_string())
            print("\\nPreview:")
            print(df.head(8).to_string(index=False))
            """
        ).strip()

    def _describe_code(self) -> str:
        return textwrap.dedent(
            """
            print("Dataset shape:", df.shape)
            print("\\nNumeric summary:")
            print(df.describe(include="all").transpose().to_string())
            """
        ).strip()

    def _missing_code(self) -> str:
        return textwrap.dedent(
            """
            missing = df.isna().sum().sort_values(ascending=False)
            missing_rate = (df.isna().mean() * 100).round(2)
            result = pd.DataFrame({"missing_count": missing, "missing_rate_pct": missing_rate.loc[missing.index]})
            print(result.to_string())
            """
        ).strip()

    def _correlation_code(self, numeric: list[str]) -> str:
        if not numeric:
            return 'print("No numeric columns are available for correlation analysis.")'
        return textwrap.dedent(
            f"""
            numeric_columns = {numeric!r}
            corr = df[numeric_columns].corr(numeric_only=True).round(4)
            print(corr.to_string())
            """
        ).strip()

    def _histogram_code(self, column: str) -> str:
        if not column:
            return 'print("No numeric column is available for a histogram.")'
        return textwrap.dedent(
            f"""
            column = {column!r}
            series = pd.to_numeric(df[column], errors="coerce").dropna()
            if series.empty:
                raise ValueError(f"Column {{column}} has no numeric values to plot.")
            print(series.describe().to_string())
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.hist(series, bins=20, color="#2f6f73", alpha=0.82)
            ax.set_title(f"Distribution of {{column}}")
            ax.set_xlabel(column)
            ax.set_ylabel("Count")
            fig.tight_layout()
            """
        ).strip()

    def _scatter_code(self, numeric: list[str]) -> str:
        if len(numeric) < 2:
            return 'print("At least two numeric columns are required for a scatter plot.")'
        return textwrap.dedent(
            f"""
            x_column, y_column = {numeric[0]!r}, {numeric[1]!r}
            plot_frame = df[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
            print(plot_frame[[x_column, y_column]].corr().round(4).to_string())
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.scatter(plot_frame[x_column], plot_frame[y_column], alpha=0.75, color="#8f3f1f")
            ax.set_xlabel(x_column)
            ax.set_ylabel(y_column)
            ax.set_title(f"{{y_column}} vs {{x_column}}")
            fig.tight_layout()
            """
        ).strip()

    def _ols_code(self, numeric: list[str]) -> str:
        if len(numeric) < 2:
            return 'print("At least two numeric columns are required for OLS regression.")'
        dependent = numeric[0]
        independents = numeric[1: min(5, len(numeric))]
        return textwrap.dedent(
            f"""
            import statsmodels.api as sm
            dependent = {dependent!r}
            independents = {independents!r}
            model_frame = df[[dependent] + independents].apply(pd.to_numeric, errors="coerce").dropna()
            y = model_frame[dependent]
            x = sm.add_constant(model_frame[independents])
            result = sm.OLS(y, x).fit()
            print(result.summary().as_text())
            """
        ).strip()

    def _column_fallback_code(self, profile: dict[str, Any]) -> str:
        columns = profile.get("column_names") or []
        numeric = profile.get("roles", {}).get("numeric") or []
        return textwrap.dedent(
            f"""
            print("The requested column was not found. Available columns are:")
            print({columns!r})
            numeric_columns = {numeric!r}
            if numeric_columns:
                print("\\nFallback numeric summary:")
                print(df[numeric_columns].describe().transpose().to_string())
            else:
                print("\\nPreview:")
                print(df.head(8).to_string(index=False))
            """
        ).strip()


class ExecutionReviewer:
    def __init__(self, llm_client: AgentLLMClient | None = None) -> None:
        self.llm_client = llm_client

    def diagnose_plan(self, *, code: str, error_message: str, session: dict[str, Any]) -> dict[str, Any]:
        if self.llm_client is not None:
            try:
                payload = self.llm_client.complete_json(
                    role="reviewer",
                    instructions=_reviewer_instructions(session),
                    input_payload={
                        "failed_code": truncate_text(code, 5000),
                        "error_message": truncate_text(error_message, 3000),
                        "dataset_profiles": [asset.get("profile") for asset in session.get("assets") or []],
                    },
                    max_tokens=1200,
                )
                suggestion = str(payload.get("suggestion") or "").strip()
                if suggestion:
                    return {
                        "suggestion": truncate_text(suggestion, 1200),
                        "source": "llm",
                        "error_type": truncate_text(str(payload.get("error_type") or ""), 120),
                        "repair_strategy": truncate_text(str(payload.get("repair_strategy") or ""), 400),
                    }
            except (AgentLLMError, ValueError, TypeError) as exc:
                return {
                    "suggestion": self.diagnose(code=code, error_message=error_message, session=session),
                    "source": "rules_fallback",
                    "error_type": "",
                    "repair_strategy": "fallback_diagnosis",
                    "llm_error": truncate_text(str(exc), 600),
                }
        return {
            "suggestion": self.diagnose(code=code, error_message=error_message, session=session),
            "source": "rules",
            "error_type": "",
            "repair_strategy": "rule_diagnosis",
        }

    def diagnose(self, *, code: str, error_message: str, session: dict[str, Any]) -> str:
        del code
        columns = []
        assets = session.get("assets") or []
        if assets:
            columns = (assets[0].get("profile") or {}).get("column_names") or []
        if "KeyError" in error_message or "not in index" in error_message:
            return f"Use one of the available columns instead of the missing column. Available columns: {columns}"
        if "ModuleNotFoundError" in error_message:
            return "Use packages already available in the application environment."
        if "SyntaxError" in error_message:
            return "Return a single valid Python code block without shell syntax."
        return "Simplify the code, validate column names, and print an intermediate result before plotting or modeling."


def _data_lab_trusted_execution_enabled(settings: Settings) -> bool:
    return bool(getattr(settings, "data_lab_agent_trusted_execution_enabled", False))


def _artifact_quota(settings: Settings) -> dict[str, int]:
    return {
        "max_count": max(0, int(getattr(settings, "data_lab_agent_artifact_max_count", _DEFAULT_ARTIFACT_MAX_COUNT))),
        "max_total_bytes": max(
            0,
            int(getattr(settings, "data_lab_agent_artifact_max_bytes", _DEFAULT_ARTIFACT_MAX_BYTES)),
        ),
    }


def _path_is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def _execution_risk_audit(
    settings: Settings,
    *,
    execution_mode: str,
    trusted_execution_enabled: bool,
    output_dir_validated: bool,
    artifact_count: int = 0,
    artifact_total_size_bytes: int = 0,
    error_type: str = "",
) -> dict[str, Any]:
    return {
        "trusted_execution_enabled": trusted_execution_enabled,
        "trusted_execution_flag": "DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED",
        "runner": "local_python_subprocess" if trusted_execution_enabled else "not_executed",
        "sandbox_claim": "none",
        "ast_policy": "enforced" if trusted_execution_enabled else "not_reached",
        "timeout_seconds": max(1, int(settings.data_lab_agent_timeout_seconds)),
        "output_limit": max(1000, int(settings.data_lab_agent_output_limit)),
        "artifact_quota": _artifact_quota(settings),
        "output_dir_validated": output_dir_validated,
        "artifact_count": artifact_count,
        "artifact_total_size_bytes": artifact_total_size_bytes,
        "error_type": error_type,
    }


def _execution_trace(
    *,
    event: str,
    execution_mode: str,
    trusted_execution_enabled: bool,
    output_dir_validated: bool,
    error_type: str = "",
    returncode: int | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "event": event,
        "at": _utc_now(),
        "execution_mode": execution_mode,
        "trusted_execution_enabled": trusted_execution_enabled,
        "output_dir_validated": output_dir_validated,
    }
    if error_type:
        trace["error_type"] = error_type
    if returncode is not None:
        trace["returncode"] = returncode
    return trace


def _execution_error_result(
    settings: Settings,
    *,
    execution_mode: str,
    error: str,
    error_type: str,
    stdout: str = "",
    stderr: str = "",
    status: str = "error",
    trusted_execution_enabled: bool = True,
    output_dir_validated: bool = False,
    returncode: int | None = None,
) -> dict[str, Any]:
    limit = max(1000, int(settings.data_lab_agent_output_limit))
    return {
        "status": status,
        "execution_mode": execution_mode,
        "stdout": truncate_text(stdout, limit),
        "stderr": truncate_text(stderr, limit),
        "error": truncate_text(error, limit),
        "error_type": error_type,
        "artifacts": [],
        "artifact_manifest": _artifact_manifest([], quota=_artifact_quota(settings)),
        "trace": _execution_trace(
            event="blocked" if status == "blocked" else "error",
            execution_mode=execution_mode,
            trusted_execution_enabled=trusted_execution_enabled,
            output_dir_validated=output_dir_validated,
            error_type=error_type,
            returncode=returncode,
        ),
        "risk_audit": _execution_risk_audit(
            settings,
            execution_mode=execution_mode,
            trusted_execution_enabled=trusted_execution_enabled,
            output_dir_validated=output_dir_validated,
            error_type=error_type,
        ),
    }


def _trusted_execution_disabled_result(settings: Settings, *, requested_mode: str, message: str) -> dict[str, Any]:
    return _execution_error_result(
        settings,
        execution_mode="not_executed",
        error=message,
        error_type="trusted_execution_required",
        status="blocked",
        trusted_execution_enabled=False,
        output_dir_validated=False,
    )


def _validate_execution_paths(settings: Settings, *, work_dir: Path, output_dir: Path, execution_dir: Path) -> None:
    agent_root = _agent_root(settings)
    if not _path_is_within(work_dir, agent_root):
        raise ValueError("Data Lab Agent work directory is outside the configured agent storage root.")
    if output_dir.name != "outputs" or not _path_is_within(output_dir, work_dir):
        raise ValueError("Data Lab Agent output directory is outside the session work directory.")
    if not _path_is_within(execution_dir, work_dir):
        raise ValueError("Data Lab Agent execution directory is outside the session work directory.")


def _validated_session_work_dir(settings: Settings, session: dict[str, Any]) -> Path:
    work_dir = Path(str(session.get("work_dir") or "")).resolve()
    _validate_execution_paths(
        settings,
        work_dir=work_dir,
        output_dir=(work_dir / "outputs").resolve(),
        execution_dir=(work_dir / "execution").resolve(),
    )
    return work_dir


def _validate_artifacts(
    settings: Settings,
    *,
    work_dir: Path,
    output_dir: Path,
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quota = _artifact_quota(settings)
    if len(artifacts) > quota["max_count"]:
        raise DataLabExecutionPolicyError(
            f"Artifact quota exceeded: at most {quota['max_count']} artifact(s) may be created.",
            error_type="artifact_quota_exceeded",
        )
    cleaned: list[dict[str, Any]] = []
    total_size = 0
    for artifact in artifacts:
        raw_path = str(artifact.get("path") or "").strip()
        if not raw_path:
            raise DataLabExecutionPolicyError(
                "Artifact manifest contains an empty path.",
                error_type="artifact_manifest_invalid",
            )
        path = Path(raw_path).resolve()
        if not _path_is_within(path, output_dir):
            raise DataLabExecutionPolicyError(
                "Artifact path is outside the validated Data Lab Agent output directory.",
                error_type="artifact_path_invalid",
            )
        if not path.is_file():
            raise DataLabExecutionPolicyError(
                "Artifact manifest references a missing output file.",
                error_type="artifact_manifest_invalid",
            )
        size_bytes = int(path.stat().st_size)
        total_size += size_bytes
        if total_size > quota["max_total_bytes"]:
            raise DataLabExecutionPolicyError(
                f"Artifact quota exceeded: total artifact size is limited to {quota['max_total_bytes']} bytes.",
                error_type="artifact_quota_exceeded",
            )
        normalized = dict(artifact)
        normalized["path"] = str(path)
        normalized["relative_path"] = str(path.relative_to(work_dir))
        normalized["size_bytes"] = size_bytes
        cleaned.append(normalized)
    return cleaned


def _trusted_execution_contract(settings: Settings) -> dict[str, Any]:
    return {
        "enabled": _data_lab_trusted_execution_enabled(settings),
        "flag": "DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED",
        "runner": "local_python_subprocess" if _data_lab_trusted_execution_enabled(settings) else "not_executed",
        "sandbox_claim": "none",
        "artifact_quota": _artifact_quota(settings),
        "output_scope": "session_outputs_only",
    }


class TrustedPythonExecutor:
    def execute(
        self,
        settings: Settings,
        *,
        session: dict[str, Any],
        code: str,
        requested_mode: str = "",
    ) -> dict[str, Any]:
        if not _data_lab_trusted_execution_enabled(settings):
            raise DataLabTrustedExecutionDisabled(
                "Data Lab Agent code execution requires DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED=true. "
                "No Python code was executed."
            )
        validate_code_safety(code)
        work_dir = Path(str(session["work_dir"])).resolve()
        output_dir = (work_dir / "outputs").resolve()
        execution_dir = (work_dir / "execution").resolve()
        execution_mode = _select_execution_mode(settings, session=session, code=code, requested_mode=requested_mode)
        try:
            _validate_execution_paths(settings, work_dir=work_dir, output_dir=output_dir, execution_dir=execution_dir)
        except ValueError as exc:
            return _execution_error_result(
                settings,
                execution_mode=execution_mode,
                error=str(exc),
                error_type="output_directory_invalid",
                status="blocked",
                output_dir_validated=False,
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        execution_dir.mkdir(parents=True, exist_ok=True)
        runner_path = execution_dir / "runner.py"
        payload_path = execution_dir / f"payload-{uuid.uuid4().hex}.json"
        result_path = execution_dir / f"result-{uuid.uuid4().hex}.json"
        runner_path.write_text(_RUNNER_SCRIPT, encoding="utf-8")
        payload = {
            "work_dir": str(work_dir),
            "output_dir": str(output_dir),
            "result_path": str(result_path),
            "execution_mode": execution_mode,
            "bootstrap_cells": [_bootstrap_code(session)],
            "replay_cells": [cell.get("code", "") for cell in session.get("cells", []) if cell.get("status") == "success"],
            "current_code": code,
            "output_limit": max(1000, int(settings.data_lab_agent_output_limit)),
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(runner_path), str(payload_path)],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, int(settings.data_lab_agent_timeout_seconds)),
                env=_safe_subprocess_env(),
            )
        except subprocess.TimeoutExpired as exc:
            return _execution_error_result(
                settings,
                execution_mode=execution_mode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                error=f"Execution timed out after {settings.data_lab_agent_timeout_seconds} seconds.",
                error_type="execution_timeout",
                output_dir_validated=True,
            )
        finally:
            try:
                payload_path.unlink(missing_ok=True)
            except Exception:
                pass
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result_path.unlink(missing_ok=True)
            try:
                artifacts = _validate_artifacts(
                    settings,
                    work_dir=work_dir,
                    output_dir=output_dir,
                    artifacts=list(result.get("artifacts") or []),
                )
            except ValueError as exc:
                return _execution_error_result(
                    settings,
                    execution_mode=execution_mode,
                    error=str(exc),
                    error_type=str(getattr(exc, "error_type", "artifact_policy_violation")),
                    status="error",
                    output_dir_validated=True,
                )
            artifact_manifest = _artifact_manifest(artifacts, quota=_artifact_quota(settings))
            result["execution_mode"] = execution_mode
            result["artifacts"] = artifacts
            result["artifact_manifest"] = artifact_manifest
            result["error_type"] = str(result.get("error_type") or ("none" if result.get("status") == "success" else "execution_error"))
            result["trace"] = result.get("trace") or _execution_trace(
                event="success" if result.get("status") == "success" else "error",
                execution_mode=execution_mode,
                trusted_execution_enabled=True,
                output_dir_validated=True,
                error_type="" if result.get("status") == "success" else str(result.get("error_type") or "execution_error"),
                returncode=completed.returncode,
            )
            result["risk_audit"] = _execution_risk_audit(
                settings,
                execution_mode=execution_mode,
                trusted_execution_enabled=True,
                output_dir_validated=True,
                artifact_count=artifact_manifest["count"],
                artifact_total_size_bytes=artifact_manifest["total_size_bytes"],
                error_type="" if result.get("status") == "success" else str(result.get("error_type") or "execution_error"),
            )
            return _json_safe(result)
        return _execution_error_result(
            settings,
            execution_mode=execution_mode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            error=f"Execution process exited with code {completed.returncode}.",
            error_type="subprocess_error",
            output_dir_validated=True,
            returncode=completed.returncode,
        )


def _select_execution_mode(settings: Settings, *, session: dict[str, Any], code: str, requested_mode: str = "") -> str:
    raw = (
        requested_mode
        or str((session.get("executor") or {}).get("requested_mode") or "")
        or str(getattr(settings, "data_lab_agent_execution_mode", "subprocess_replay") or "")
    ).strip().lower()
    if raw not in {"subprocess_replay", "ipython_kernel", "auto"}:
        raw = "subprocess_replay"
    ipython_enabled = bool(getattr(settings, "data_lab_agent_ipython_enabled", False))
    if raw == "ipython_kernel":
        return "ipython_kernel" if ipython_enabled else "subprocess_replay"
    if raw == "auto" and ipython_enabled and _code_prefers_ipython(code):
        return "ipython_kernel"
    return "subprocess_replay"


def _code_prefers_ipython(code: str) -> bool:
    lowered = str(code or "").lower()
    return "display(" in lowered or "from IPython" in str(code or "")


def _artifact_manifest(artifacts: list[dict[str, Any]], *, quota: dict[str, int] | None = None) -> dict[str, Any]:
    image_count = 0
    total_size = 0
    names: list[str] = []
    for artifact in artifacts:
        content_type = str(artifact.get("content_type") or "")
        if content_type.startswith("image/"):
            image_count += 1
        total_size += int(artifact.get("size_bytes") or 0)
        if artifact.get("name"):
            names.append(str(artifact.get("name")))
    manifest = {
        "count": len(artifacts),
        "image_count": image_count,
        "total_size_bytes": total_size,
        "names": names[:20],
    }
    if quota is not None:
        manifest["quota"] = dict(quota)
        manifest["quota_exceeded"] = len(artifacts) > quota.get("max_count", len(artifacts)) or total_size > quota.get(
            "max_total_bytes", total_size
        )
    return manifest


def _safe_subprocess_env() -> dict[str, str]:
    keep = ["PATH", "Path", "SystemRoot", "TEMP", "TMP", "HOME", "USERPROFILE", "PYTHONPATH"]
    env = {key: value for key, value in os.environ.items() if key in keep}
    env["MPLBACKEND"] = "Agg"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def validate_code_safety(code: str) -> None:
    stripped = str(code or "").strip()
    if not stripped:
        raise SafetyViolation("No Python code was provided.")
    for pattern in _BLOCKED_TEXT_PATTERNS:
        if pattern.search(stripped):
            raise SafetyViolation("Shell commands and package installation are not allowed in Data Lab Agent code.")
    try:
        tree = ast.parse(stripped)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python code: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                root = name.split(".")[0]
                if root in _BLOCKED_IMPORT_ROOTS or (root not in _ALLOWED_IMPORT_ROOTS and root):
                    raise SafetyViolation(f"Importing {root!r} is not allowed in Data Lab Agent trusted execution.")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _BLOCKED_CALLS:
                raise SafetyViolation(f"Calling {func.id!r} is not allowed in Data Lab Agent trusted execution.")
            if isinstance(func, ast.Attribute) and func.attr in _BLOCKED_ATTRS:
                raise SafetyViolation(f"Calling attribute {func.attr!r} is not allowed in Data Lab Agent trusted execution.")
        if isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRS:
            raise SafetyViolation(f"Accessing attribute {node.attr!r} is not allowed in Data Lab Agent trusted execution.")


class ReportWriter:
    def build_report(self, session: dict[str, Any], llm_client: AgentLLMClient | None = None) -> str:
        lines = [
            f"# {session.get('title') or 'Data Lab Agent Report'}",
            "",
        ]
        narrative = self._llm_narrative(session, llm_client)
        if narrative:
            lines.extend(["## Narrative Summary", narrative, ""])
        lines.append("## Data Profile")
        for asset in session.get("assets") or []:
            profile = asset.get("profile") or {}
            lines.extend(
                [
                    f"- {asset.get('title')}: {profile.get('rows', 0)} rows, {profile.get('columns', 0)} columns.",
                    f"- Columns: {', '.join(profile.get('column_names') or [])}",
                    f"- Schema fingerprint: `{profile.get('schema_fingerprint', '')}`",
                ]
            )
            warnings = profile.get("quality_warnings") or []
            if warnings:
                lines.append("- Quality warnings: " + "; ".join(str(item) for item in warnings[:6]))
            targets = profile.get("candidate_targets") or []
            if targets:
                lines.append("- Candidate target columns: " + ", ".join(str(item) for item in targets))
        lines.extend(["", "## Knowledge Used"])
        cards = _session_knowledge_cards(session)
        if not cards:
            lines.append("No interface knowledge cards were used.")
        for card in cards[:12]:
            lines.append(f"- **{card.get('title')}** ({card.get('source_type')}): {card.get('summary')}")
        lines.extend(["", "## Analysis Steps"])
        step = 0
        for message in session.get("messages") or []:
            if message.get("role") != "assistant":
                continue
            if not message.get("code"):
                continue
            step += 1
            execution = message.get("execution") or {}
            lines.extend(
                [
                    f"### Step {step}: {message.get('status', 'completed')}",
                    "",
                    "```python",
                    str(message.get("code") or "").strip(),
                    "```",
                    "",
                    f"- Execution mode: `{message.get('execution_mode') or (execution.get('execution_mode') or '')}`",
                    f"- Coder source: `{message.get('coder_source') or ''}`",
                ]
            )
            stdout = str(execution.get("stdout") or "").strip()
            if stdout:
                lines.extend(["Output:", "", "```text", stdout[:4000], "```", ""])
            profile_snapshot = message.get("profile_snapshot") or execution.get("profile_snapshot") or {}
            if profile_snapshot:
                lines.append(
                    f"- Post-step profile: {profile_snapshot.get('rows', 0)} rows, "
                    f"{profile_snapshot.get('columns', 0)} columns, fingerprint `{profile_snapshot.get('schema_fingerprint', '')}`."
                )
            manifest = message.get("artifact_manifest") or execution.get("artifact_manifest") or {}
            if manifest:
                lines.append(
                    f"- Artifact manifest: {manifest.get('count', 0)} file(s), "
                    f"{manifest.get('image_count', 0)} image(s), {manifest.get('total_size_bytes', 0)} bytes."
                )
            for artifact in execution.get("artifacts") or []:
                path = artifact.get("path")
                if path:
                    lines.append(f"- Artifact: `{path}`")
        lines.extend(["", "## Repair And Human Intervention"])
        traces = [
            item
            for message in session.get("messages") or []
            for item in (message.get("repair_trace") or [])
        ]
        if not traces:
            lines.append("No automated repair was needed.")
        for item in traces:
            lines.append(
                f"- Attempt {item.get('attempt')}: {item.get('status')} via {item.get('reviewer_source', 'reviewer')} - "
                f"{str(item.get('error', ''))[:240]}"
            )
        interventions = [
            message.get("human_intervention")
            for message in session.get("messages") or []
            if isinstance(message.get("human_intervention"), dict)
            and (message.get("human_intervention") or {}).get("provided")
        ]
        if interventions:
            for item in interventions:
                lines.append(f"- Human code provided. Note: {item.get('note') or 'No note.'}")
        lines.extend(
            [
                "",
                "## Reproducibility Appendix",
                f"- Executor strategy: `{(session.get('executor') or {}).get('strategy', '')}`",
                f"- Active mode: `{(session.get('executor') or {}).get('active_mode', '')}`",
                f"- Successful cells: {len(session.get('cells') or [])}",
                f"- Safety events: {len(session.get('safety_events') or [])}",
                "",
                "## Summary",
                session.get("summary") or "The Data Lab Agent session is ready for review.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _llm_narrative(self, session: dict[str, Any], llm_client: AgentLLMClient | None) -> str:
        if llm_client is None:
            return ""
        try:
            payload = llm_client.complete_json(
                role="report",
                instructions=_report_instructions(session),
                input_payload=_report_payload(session),
                max_tokens=1200,
            )
        except (AgentLLMError, ValueError, TypeError):
            return ""
        return truncate_text(str(payload.get("summary") or ""), 2400)

    def write_notebook(self, session: dict[str, Any]) -> Path:
        work_dir = Path(str(session["work_dir"])).resolve()
        notebook_path = work_dir / "notebook.ipynb"
        cells: list[dict[str, Any]] = [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": _notebook_source([f"# {session.get('title') or 'Data Lab Agent Notebook'}\n"]),
            }
        ]
        cells.append(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": _notebook_source([_notebook_context_markdown(session)]),
            }
        )
        for message in session.get("messages") or []:
            if message.get("role") == "user":
                cells.append(
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": _notebook_source(
                            [
                                f"## User\n\n{message.get('content', '')}\n\n",
                                f"Intervention note: {message.get('intervention_note', '')}\n"
                                if message.get("intervention_note")
                                else "",
                            ]
                        ),
                    }
                )
                continue
            code = str(message.get("code") or "").strip()
            if not code:
                continue
            execution = message.get("execution") or {}
            outputs = []
            stdout = str(execution.get("stdout") or "")
            stderr = str(execution.get("stderr") or "")
            error = str(execution.get("error") or "")
            if stdout:
                outputs.append({"output_type": "stream", "name": "stdout", "text": _notebook_source([stdout])})
            if stderr or error:
                outputs.append({"output_type": "stream", "name": "stderr", "text": _notebook_source([stderr or error])})
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {
                        "data_lab_agent": {
                            "status": message.get("status"),
                            "execution_mode": message.get("execution_mode"),
                            "artifact_manifest": message.get("artifact_manifest") or {},
                            "profile_snapshot": message.get("profile_snapshot") or {},
                        }
                    },
                    "outputs": outputs,
                    "source": _notebook_source([code + "\n"]),
                }
            )
            artifacts = (message.get("execution") or {}).get("artifacts") or []
            if artifacts:
                cells.append(
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": _notebook_source(
                            ["Artifacts:\n"]
                            + [f"- `{artifact.get('relative_path') or artifact.get('path')}`\n" for artifact in artifacts]
                        ),
                    }
                )
        notebook = {
            "cells": cells,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        notebook_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
        return notebook_path


def _notebook_source(parts: list[str]) -> list[str]:
    text = "".join(parts)
    return text.splitlines(keepends=True) or [""]


def _notebook_context_markdown(session: dict[str, Any]) -> str:
    lines = ["## Session Context", ""]
    for asset in session.get("assets") or []:
        profile = asset.get("profile") or {}
        lines.append(f"- Dataset `{asset.get('title')}`: {profile.get('rows', 0)} rows, {profile.get('columns', 0)} columns.")
        if profile.get("schema_fingerprint"):
            lines.append(f"- Schema fingerprint: `{profile.get('schema_fingerprint')}`.")
    cards = _session_knowledge_cards(session)
    if cards:
        lines.extend(["", "Knowledge cards:"])
        for card in cards[:8]:
            lines.append(f"- {card.get('title')} ({card.get('source_type')})")
    return "\n".join(lines).strip() + "\n"


def create_agent_session(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_ids: list[str],
    title: str = "",
    language: str = "Chinese",
) -> dict[str, Any]:
    _require_enabled(settings)
    normalized_asset_ids = [str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()]
    if not normalized_asset_ids:
        raise ValueError("Select at least one dataset asset for a Data Lab Agent session.")
    run = create_data_lab_run(
        db,
        user=user,
        workspace=workspace,
        workflow_type=AGENT_WORKFLOW_TYPE,
        family=AGENT_FAMILY,
        method=AGENT_METHOD,
        title=title or "Data Lab Agent Session",
        source_asset_id=normalized_asset_ids[0],
        request_payload={"asset_ids": normalized_asset_ids, "title": title, "language": language},
    )
    work_dir = _session_work_dir(settings, run.id)
    assets_payload = []
    for asset_id in normalized_asset_ids:
        asset = _dataset_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
        local_path = work_dir / "inputs" / _safe_input_filename(asset)
        local_path.write_bytes(load_asset_bytes(settings, asset.file_path))
        frame = load_dataset_frame(settings, asset)
        assets_payload.append(
            {
                "id": asset.id,
                "asset_id": asset.id,
                "title": asset.title,
                "kind": asset.kind,
                "local_path": str(local_path),
                "asset": serialize_asset(asset),
                "profile": _profile_frame(frame, asset=asset, local_path=local_path),
            }
        )
    session = {
        "version": 2,
        "run_id": run.id,
        "title": title.strip() or "Data Lab Agent Session",
        "language": language.strip() or "Chinese",
        "work_dir": str(work_dir),
        "detail_path": f"/app/data-lab-agent?run={run.id}",
        "run_status": "ready",
        "summary": "Data Lab Agent session created.",
        "assets": assets_payload,
        "messages": [],
        "cells": [],
        "artifacts": [],
        "profile_snapshots": [],
        "safety_events": [],
        "executor": {
            "strategy": "trusted_local_python",
            "requested_mode": str(getattr(settings, "data_lab_agent_execution_mode", "subprocess_replay") or "subprocess_replay"),
            "active_mode": "not_executed"
            if not _data_lab_trusted_execution_enabled(settings)
            else "subprocess_replay",
            "trusted_execution_enabled": _data_lab_trusted_execution_enabled(settings),
            "trusted_execution": _trusted_execution_contract(settings),
            "sandbox_claim": "none",
            "ipython_enabled": bool(getattr(settings, "data_lab_agent_ipython_enabled", False)),
            "timeout_seconds": int(settings.data_lab_agent_timeout_seconds),
            "max_attempts": int(settings.data_lab_agent_max_attempts),
            "artifact_quota": _artifact_quota(settings),
        },
        "llm": resolve_agent_llm_config(settings, db, user=user, workspace=workspace).public_summary(),
        "math": {
            "mode": settings_math_mode(settings),
            "override_margin": float(getattr(settings, "agent_math_override_margin", 0.05)),
            "v2_state_summary": {},
            "internal_v2_state": {},
        },
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    session["math"]["internal_v2_state"] = _data_lab_internal_math_state(session, status="ready")
    session["math"]["v2_state_summary"] = _public_math_state_summary(session["math"]["internal_v2_state"])
    _assign_session(run, session)
    db.flush()
    return {"session": public_session_payload(session)}


def get_agent_session(db: Session, *, user: User, workspace: Workspace, run_id: str) -> dict[str, Any]:
    run = _run_or_raise(db, user=user, workspace=workspace, run_id=run_id)
    return {"session": public_session_payload(_session_from_run(run))}


def send_agent_message(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    run_id: str,
    message: str = "",
    user_code: str = "",
    intervention_note: str = "",
    execution_mode: str = "",
) -> dict[str, Any]:
    _require_enabled(settings)
    run = _run_or_raise(db, user=user, workspace=workspace, run_id=run_id)
    session = _session_from_run(run)
    clean_message = truncate_text(str(message or "").strip(), 4000)
    clean_user_code = str(user_code or "").strip()
    clean_intervention_note = truncate_text(str(intervention_note or "").strip(), 1600)
    requested_execution_mode = str(execution_mode or "").strip().lower()
    if not clean_message and not clean_user_code:
        raise ValueError("Provide a message or user_code.")
    user_record = {
        "id": uuid.uuid4().hex,
        "role": "user",
        "content": clean_message or "Manual code execution",
        "user_code": bool(clean_user_code),
        "intervention_note": clean_intervention_note,
        "created_at": _utc_now(),
    }
    session.setdefault("messages", []).append(user_record)
    math_mode = settings_math_mode(settings)
    override_margin = float(getattr(settings, "agent_math_override_margin", 0.05))
    session["math"] = dict(session.get("math") or {})
    session["math"]["mode"] = math_mode
    session["math"]["override_margin"] = override_margin
    knowledge = DataLabKnowledgeResolver().resolve(
        db,
        user=user,
        workspace=workspace,
        instruction=clean_message,
        session=session,
        mode=math_mode,
        override_margin=override_margin,
    )
    llm_config = resolve_agent_llm_config(settings, db, user=user, workspace=workspace)
    llm_client = AgentLLMClient(llm_config) if llm_config.ready else None
    session["llm"] = llm_config.public_summary()
    session.setdefault("executor", {})["trusted_execution_enabled"] = _data_lab_trusted_execution_enabled(settings)
    session.setdefault("executor", {})["trusted_execution"] = _trusted_execution_contract(settings)
    session.setdefault("executor", {})["artifact_quota"] = _artifact_quota(settings)
    session.setdefault("executor", {})["sandbox_claim"] = "none"
    if requested_execution_mode:
        session.setdefault("executor", {})["requested_mode"] = requested_execution_mode
    session_state = _data_lab_internal_math_state(
        session,
        instruction=clean_message or "Manual code execution",
        requested_execution_mode=requested_execution_mode,
        status=str(session.get("run_status") or "ready"),
    )
    session["math"]["internal_v2_state"] = session_state
    session["math"]["v2_state_summary"] = _public_math_state_summary(session_state)
    coder = AnalystCoder(llm_client=llm_client)
    reviewer = ExecutionReviewer(llm_client=llm_client)
    executor = TrustedPythonExecutor()
    repair_trace: list[dict[str, Any]] = []
    llm_trace_summary: list[dict[str, Any]] = []
    repair_decisions: list[dict[str, Any]] = []
    human_intervention: dict[str, Any] = {"required": False, "provided": bool(clean_user_code), "note": clean_intervention_note}
    if clean_user_code:
        code_plan = _code_plan(
            clean_user_code,
            source="human",
            explanation=clean_intervention_note or "Human-provided code was executed in the current session context.",
        )
        max_attempts = 0
    else:
        code_plan = coder.draft_plan(clean_message, session, knowledge)
        max_attempts = max(0, int(settings.data_lab_agent_max_attempts))
    code = str(code_plan.get("code") or "")
    llm_trace_summary.append(_plan_trace("coder", code_plan, llm_config))
    final_execution: dict[str, Any] = {}
    status = "error"
    content = ""
    for attempt in range(max_attempts + 1):
        try:
            final_execution = executor.execute(settings, session=session, code=code, requested_mode=requested_execution_mode)
        except DataLabTrustedExecutionDisabled as exc:
            event = {
                "at": _utc_now(),
                "type": "trusted_execution_required",
                "message": str(exc),
                "code_preview": code[:400],
            }
            session.setdefault("safety_events", []).append(event)
            final_execution = _trusted_execution_disabled_result(
                settings,
                requested_mode=requested_execution_mode,
                message=str(exc),
            )
            repair_decisions.append(
                {
                    "error_class": "feature_disabled",
                    "best_action": "block",
                    "reason": str(exc),
                    "error_type": "trusted_execution_required",
                    "attempt": attempt + 1,
                }
            )
            session_state.setdefault("M_t", {}).setdefault("recent_failure_classes", []).append("feature_disabled")
            session_state["M_t"]["recent_failure_classes"] = list(session_state["M_t"]["recent_failure_classes"])[-6:]
            status = "blocked"
            content = "Code execution is disabled until trusted execution is explicitly enabled."
            human_intervention = {
                "required": False,
                "provided": bool(clean_user_code),
                "note": clean_intervention_note,
                "reason": str(exc),
                "next_action": "Set DATA_LAB_AGENT_TRUSTED_EXECUTION_ENABLED=true only in a trusted deployment.",
            }
            break
        except SafetyViolation as exc:
            event = {"at": _utc_now(), "type": "safety_policy_violation", "message": str(exc), "code_preview": code[:400]}
            session.setdefault("safety_events", []).append(event)
            repair_decisions.append(
                build_data_lab_repair_decision(
                    error_message=str(exc),
                    attempt_index=attempt + 1,
                    max_attempts=max(1, max_attempts),
                    mode=math_mode,
                    has_human_code=bool(clean_user_code),
                    human_threshold=float(getattr(settings, "agent_math_human_threshold", 0.55)),
                    override_margin=override_margin,
                    session_state=session_state,
                )
            )
            session_state.setdefault("M_t", {}).setdefault("recent_failure_classes", []).append("safety")
            session_state["M_t"]["recent_failure_classes"] = list(session_state["M_t"]["recent_failure_classes"])[-6:]
            final_execution = _execution_error_result(
                settings,
                execution_mode="not_executed",
                error=str(exc),
                error_type="safety_policy_violation",
                status="blocked",
                trusted_execution_enabled=_data_lab_trusted_execution_enabled(settings),
                output_dir_validated=False,
            )
            status = "blocked"
            content = "Code was blocked by the Data Lab Agent safety policy."
            break
        except ValueError as exc:
            final_execution = _execution_error_result(
                settings,
                execution_mode="not_executed",
                error=str(exc),
                error_type="validation_error",
                trusted_execution_enabled=_data_lab_trusted_execution_enabled(settings),
                output_dir_validated=False,
            )
        status = str(final_execution.get("status") or "error")
        if status == "success":
            content = code_plan.get("explanation") or _assistant_success_text(final_execution)
            break
        error_message = str(final_execution.get("error") or final_execution.get("stderr") or "Execution failed.")
        decision_trace = build_data_lab_repair_decision(
            error_message=error_message,
            attempt_index=attempt + 1,
            max_attempts=max(1, max_attempts),
            mode=math_mode,
            has_human_code=bool(clean_user_code),
            human_threshold=float(getattr(settings, "agent_math_human_threshold", 0.55)),
            override_margin=override_margin,
            session_state=session_state,
        )
        repair_decisions.append(decision_trace)
        session_state.setdefault("M_t", {}).setdefault("recent_failure_classes", []).append(str(decision_trace.get("error_class") or "runtime"))
        session_state["M_t"]["recent_failure_classes"] = list(session_state["M_t"]["recent_failure_classes"])[-6:]
        if math_mode == "active" and decision_trace.get("best_action") == "block":
            final_execution["status"] = "blocked"
            content = "Execution was blocked because ARBITER judged terminal risk to dominate feasible repair actions."
            status = "blocked"
            human_intervention = {
                "required": False,
                "provided": bool(clean_user_code),
                "note": clean_intervention_note,
                "reason": truncate_text(error_message, 1200),
                "next_action": "Review the blocked code and lower execution risk before retrying.",
            }
            break
        if math_mode == "active" and decision_trace.get("best_action") == "ask_human":
            final_execution["status"] = "needs_human_intervention"
            content = "Execution requires human intervention because ARBITER ranked intervention above autonomous repair."
            status = "needs_human_intervention"
            human_intervention = {
                "required": True,
                "provided": bool(clean_user_code),
                "note": clean_intervention_note,
                "reason": truncate_text(error_message, 1200),
                "next_action": "Edit the generated Python cell and submit it as manual code.",
            }
            break
        if attempt >= max_attempts:
            content = "Execution failed after automated repair attempts. Human code review is required."
            status = "needs_human_intervention"
            human_intervention = {
                "required": True,
                "provided": bool(clean_user_code),
                "note": clean_intervention_note,
                "reason": truncate_text(error_message, 1200),
                "next_action": "Edit the generated Python cell and submit it as manual code.",
            }
            break
        diagnosis = reviewer.diagnose_plan(code=code, error_message=error_message, session=session)
        llm_trace_summary.append(_diagnosis_trace("reviewer", diagnosis, llm_config))
        repair_trace.append(
            {
                "attempt": attempt + 1,
                "status": "repair_requested",
                "error": truncate_text(error_message, 1000),
                "suggestion": diagnosis.get("suggestion", ""),
                "reviewer_source": diagnosis.get("source", ""),
                "error_type": diagnosis.get("error_type", ""),
                "repair_strategy": diagnosis.get("repair_strategy", ""),
                "code": code,
                "arbiter": decision_trace,
            }
        )
        code_plan = coder.repair_plan(
            instruction=clean_message,
            failed_code=code,
            error_message=error_message,
            session=session,
            suggestion=str(diagnosis.get("suggestion") or ""),
            knowledge=knowledge,
        )
        code = str(code_plan.get("code") or "")
        llm_trace_summary.append(_plan_trace("repair", code_plan, llm_config))
    if final_execution.get("status") == "success":
        profile_snapshot = final_execution.get("profile_snapshot") or {}
        cell = {
            "id": uuid.uuid4().hex,
            "status": "success",
            "code": code,
            "stdout": final_execution.get("stdout", ""),
            "stderr": final_execution.get("stderr", ""),
            "artifacts": final_execution.get("artifacts") or [],
            "artifact_manifest": final_execution.get("artifact_manifest") or _artifact_manifest(final_execution.get("artifacts") or []),
            "profile_snapshot": profile_snapshot,
            "execution_mode": final_execution.get("execution_mode") or "subprocess_replay",
            "risk_audit": final_execution.get("risk_audit") or {},
            "coder_source": code_plan.get("source", ""),
            "created_at": _utc_now(),
        }
        session.setdefault("cells", []).append(cell)
        session.setdefault("artifacts", []).extend(final_execution.get("artifacts") or [])
        if profile_snapshot:
            session.setdefault("profile_snapshots", []).append(
                {
                    "id": uuid.uuid4().hex,
                    "message_id": cell["id"],
                    "created_at": _utc_now(),
                    "profile": profile_snapshot,
                }
            )
    assistant_record = {
        "id": uuid.uuid4().hex,
        "role": "assistant",
        "content": content,
        "status": status,
        "code": code,
        "execution": final_execution,
        "execution_mode": final_execution.get("execution_mode") or "not_executed",
        "profile_snapshot": final_execution.get("profile_snapshot") or {},
        "artifact_manifest": final_execution.get("artifact_manifest") or _artifact_manifest(final_execution.get("artifacts") or []),
        "risk_audit": final_execution.get("risk_audit") or {},
        "repair_trace": repair_trace,
        "knowledge": knowledge,
        "knowledge_cards": knowledge.get("cards") or [],
        "human_intervention": human_intervention,
        "llm_trace_summary": llm_trace_summary,
        "math_trace": {
            "mode": math_mode,
            "retrieval": knowledge.get("arbiter") or {},
            "repair_decisions": repair_decisions,
            "v2_state_summary": _public_math_state_summary(session_state),
            "override_margin": override_margin,
        },
        "coder_source": code_plan.get("source", ""),
        "risk_notes": code_plan.get("risk_notes") or [],
        "created_at": _utc_now(),
    }
    session.setdefault("messages", []).append(assistant_record)
    session["summary"] = content
    session["run_status"] = status if status in {"blocked", "needs_human_intervention"} else "ready"
    session.setdefault("executor", {})["active_mode"] = final_execution.get("execution_mode") or "not_executed"
    session["math"]["internal_v2_state"] = _data_lab_internal_math_state(
        session,
        instruction=clean_message or "Manual code execution",
        requested_execution_mode=requested_execution_mode,
        status=session["run_status"],
    )
    session["math"]["v2_state_summary"] = _public_math_state_summary(session["math"]["internal_v2_state"])
    assistant_record["math_trace"]["v2_state_summary"] = dict(session["math"]["v2_state_summary"])
    session["updated_at"] = _utc_now()
    _assign_session(run, session)
    db.flush()
    return {"session": public_session_payload(session), "message": assistant_record}


def _assistant_success_text(execution: dict[str, Any]) -> str:
    artifacts = execution.get("artifacts") or []
    stdout = str(execution.get("stdout") or "").strip()
    if artifacts:
        return f"Analysis completed with {len(artifacts)} artifact(s)."
    if stdout:
        first_line = stdout.splitlines()[0][:160]
        return f"Analysis completed. First output: {first_line}"
    return "Analysis completed."


def _session_knowledge_cards(session: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    cards: list[dict[str, Any]] = []
    for message in session.get("messages") or []:
        for card in message.get("knowledge_cards") or (message.get("knowledge") or {}).get("cards") or []:
            if not isinstance(card, dict):
                continue
            card_id = str(card.get("id") or card.get("title") or "")
            if card_id in seen:
                continue
            seen.add(card_id)
            cards.append(card)
    return cards


def generate_agent_report(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    run_id: str,
) -> dict[str, Any]:
    _require_enabled(settings)
    run = _run_or_raise(db, user=user, workspace=workspace, run_id=run_id)
    session = _session_from_run(run)
    llm_config = resolve_agent_llm_config(settings, db, user=user, workspace=workspace)
    llm_client = AgentLLMClient(llm_config) if llm_config.ready else None
    report = ReportWriter().build_report(session, llm_client=llm_client)
    report_path = _validated_session_work_dir(settings, session) / "report.md"
    report_path.write_text(report, encoding="utf-8")
    session["report_path"] = str(report_path)
    session["summary"] = "Data Lab Agent report generated."
    session["updated_at"] = _utc_now()
    _assign_session(run, session)
    db.flush()
    return {
        "session": public_session_payload(session),
        "report": {
            "path": str(report_path),
            "markdown": report,
        },
    }


def export_agent_notebook(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    run_id: str,
) -> Path:
    _require_enabled(settings)
    run = _run_or_raise(db, user=user, workspace=workspace, run_id=run_id)
    session = _session_from_run(run)
    _validated_session_work_dir(settings, session)
    notebook_path = ReportWriter().write_notebook(session)
    session["notebook_path"] = str(notebook_path)
    session["updated_at"] = _utc_now()
    _assign_session(run, session)
    db.flush()
    return notebook_path


def public_session_payload(session: dict[str, Any]) -> dict[str, Any]:
    public = dict(session)
    math_payload = dict(public.get("math") or {})
    if math_payload:
        math_payload.pop("internal_v2_state", None)
        math_payload["v2_state_summary"] = _public_math_state_summary(dict((session.get("math") or {}).get("internal_v2_state") or {}))
        public["math"] = math_payload
    public["assets"] = [
        {
            "id": item.get("id"),
            "asset_id": item.get("asset_id"),
            "title": item.get("title"),
            "kind": item.get("kind"),
            "asset": item.get("asset"),
            "profile": item.get("profile"),
        }
        for item in session.get("assets") or []
    ]
    return _json_safe(public)


_RUNNER_SCRIPT = r'''
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import os
import sys
import traceback
import uuid


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


payload_path = Path(sys.argv[1])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
work_dir = Path(payload["work_dir"]).resolve()
output_dir = Path(payload["output_dir"]).resolve()
result_path = Path(payload["result_path"]).resolve()
execution_dir = result_path.parent.resolve()
limit = int(payload.get("output_limit") or 12000)
if output_dir.name != "outputs" or (work_dir not in output_dir.parents and output_dir != work_dir):
    result_path.write_text(
        json.dumps(
            {
                "status": "error",
                "stdout": "",
                "stderr": "",
                "error": "Output directory is outside the Data Lab Agent session work directory.",
                "error_type": "output_directory_invalid",
                "artifacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raise SystemExit(0)
output_dir.mkdir(parents=True, exist_ok=True)
os.chdir(work_dir)
namespace = {"__name__": "__data_lab_agent__"}
execution_mode = str(payload.get("execution_mode") or "subprocess_replay")
ipython_shell = None
if execution_mode == "ipython_kernel":
    try:
        from IPython.core.interactiveshell import InteractiveShell

        ipython_shell = InteractiveShell.instance()
        ipython_shell.user_ns.update(namespace)
        namespace = ipython_shell.user_ns
    except Exception:
        ipython_shell = None


def run_cell(code: str, label: str, *, capture: bool) -> dict:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        if capture:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                if ipython_shell is not None:
                    result = ipython_shell.run_cell(code, store_history=False)
                    if result.error_before_exec:
                        raise result.error_before_exec
                    if result.error_in_exec:
                        raise result.error_in_exec
                else:
                    exec(compile(code, label, "exec"), namespace)
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if ipython_shell is not None:
                    result = ipython_shell.run_cell(code, store_history=False)
                    if result.error_before_exec:
                        raise result.error_before_exec
                    if result.error_in_exec:
                        raise result.error_in_exec
                else:
                    exec(compile(code, label, "exec"), namespace)
        return {"ok": True, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
    except Exception:
        return {
            "ok": False,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "traceback": traceback.format_exc(),
        }


def snapshot() -> dict[str, int]:
    return {str(path.resolve()): path.stat().st_mtime_ns for path in output_dir.rglob("*") if path.is_file()}


def is_within(path: Path, parent: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
    except Exception:
        return False
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def is_lexically_within(path: Path, parent: Path) -> bool:
    try:
        path.absolute().relative_to(parent.absolute())
    except ValueError:
        return False
    return True


def non_output_snapshot() -> dict[str, dict[str, object]]:
    files = {}
    for path in work_dir.rglob("*"):
        if not path.is_file():
            continue
        scan_path = path.absolute()
        if is_lexically_within(scan_path, output_dir) or is_lexically_within(scan_path, execution_dir):
            continue
        try:
            resolved = path.resolve()
            mtime_ns = path.lstat().st_mtime_ns
        except Exception:
            continue
        files[str(scan_path)] = {"mtime_ns": mtime_ns, "resolved_path": str(resolved)}
    return files


def changed_non_output_files(before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]) -> list[str]:
    changed = []
    for raw_path, metadata in after.items():
        if raw_path not in before or before[raw_path] != metadata:
            changed.append(raw_path)
    return changed


def remove_created_non_output_files(before: dict[str, dict[str, object]], changed: list[str]) -> None:
    for raw_path in changed:
        if raw_path in before:
            continue
        path = Path(raw_path).absolute()
        if not is_lexically_within(path, work_dir) or is_lexically_within(path, output_dir) or is_lexically_within(path, execution_dir):
            continue
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def safe(value):
    try:
        import math
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {str(key): safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [safe(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "item"):
            return safe(value.item())
    except Exception:
        pass
    return str(value)


def dataframe_profile_snapshot():
    frame = namespace.get("df")
    if frame is None or not hasattr(frame, "head") or not hasattr(frame, "dtypes"):
        return {}
    try:
        schema = [{"name": str(column), "dtype": str(dtype)} for column, dtype in frame.dtypes.items()]
        return safe(
            {
                "profile_version": 2,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "column_names": [str(column) for column in frame.columns],
                "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
                "missing_by_column": {str(column): int(value) for column, value in frame.isna().sum().to_dict().items()},
                "schema_fingerprint": hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()[:16],
                "preview_rows": frame.head(6).where(frame.head(6).notna(), None).to_dict(orient="records"),
            }
        )
    except Exception:
        return {}


before = snapshot()
non_output_before = non_output_snapshot()
for index, code in enumerate(payload.get("bootstrap_cells") or []):
    result = run_cell(code, f"<bootstrap-{index}>", capture=False)
    if not result["ok"]:
        result_path.write_text(
            json.dumps(
                {
                    "status": "error",
                    "stdout": _truncate(result.get("stdout", ""), limit),
                    "stderr": _truncate(result.get("stderr", ""), limit),
                    "error": _truncate(result.get("traceback", ""), limit),
                    "error_type": "bootstrap_error",
                    "artifacts": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise SystemExit(0)

for index, code in enumerate(payload.get("replay_cells") or []):
    result = run_cell(code, f"<replay-{index}>", capture=False)
    if not result["ok"]:
        result_path.write_text(
            json.dumps(
                {
                    "status": "error",
                    "stdout": _truncate(result.get("stdout", ""), limit),
                    "stderr": _truncate(result.get("stderr", ""), limit),
                    "error": _truncate("Session replay failed:\n" + result.get("traceback", ""), limit),
                    "error_type": "session_replay_error",
                    "artifacts": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise SystemExit(0)

result = run_cell(payload.get("current_code") or "", "<current>", capture=True)
figure_error = ""
if result["ok"]:
    try:
        import matplotlib.pyplot as plt

        for figure_number in plt.get_fignums():
            figure = plt.figure(figure_number)
            figure_path = output_dir / f"figure-{uuid.uuid4().hex}.png"
            figure.savefig(figure_path, bbox_inches="tight")
        plt.close("all")
    except Exception:
        figure_error = traceback.format_exc()

after = snapshot()
artifacts = []
for raw_path, mtime in after.items():
    if raw_path not in before or before[raw_path] != mtime:
        path = Path(raw_path)
        artifacts.append(
            {
                "name": path.name,
                "path": str(path),
                "relative_path": str(path.relative_to(work_dir)) if work_dir in path.parents else path.name,
                "size_bytes": path.stat().st_size,
                "content_type": "image/png" if path.suffix.lower() == ".png" else "application/octet-stream",
            }
        )

non_output_changes = changed_non_output_files(non_output_before, non_output_snapshot())
if non_output_changes:
    remove_created_non_output_files(non_output_before, non_output_changes)
    payload_out = {
        "status": "error",
        "stdout": _truncate(result.get("stdout", ""), limit),
        "stderr": _truncate((result.get("stderr", "") or "") + (("\n" + figure_error) if figure_error else ""), limit),
        "error": _truncate("Execution attempted to create or modify files outside OUTPUT_DIR: " + ", ".join(non_output_changes[:5]), limit),
        "error_type": "file_write_outside_output",
        "artifacts": [],
        "profile_snapshot": {},
    }
    result_path.write_text(json.dumps(payload_out, ensure_ascii=False), encoding="utf-8")
    raise SystemExit(0)

payload_out = {
    "status": "success" if result["ok"] else "error",
    "stdout": _truncate(result.get("stdout", ""), limit),
    "stderr": _truncate((result.get("stderr", "") or "") + (("\n" + figure_error) if figure_error else ""), limit),
    "error": "" if result["ok"] else _truncate(result.get("traceback", ""), limit),
    "error_type": "none" if result["ok"] else "execution_error",
    "artifacts": artifacts,
    "profile_snapshot": dataframe_profile_snapshot() if result["ok"] else {},
}
result_path.write_text(json.dumps(payload_out, ensure_ascii=False), encoding="utf-8")
'''
