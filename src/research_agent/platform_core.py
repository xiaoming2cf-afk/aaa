from __future__ import annotations

import csv
import json
import math
import re
from statistics import NormalDist
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import os
import tempfile
from typing import Any

import fitz
import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from arch import arch_model
from statsmodels.tsa.api import VAR
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.sandbox.regression.gmm import IV2SLS
from statsmodels.tools.sm_exceptions import PerfectSeparationError
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .asset_storage import load_asset_bytes, store_asset_content
from .auth_support import (
    assert_login_allowed,
    clear_login_failures,
    purge_expired_sessions,
    record_login_failure,
)
from .config import Settings
from .entities import (
    DataAsset,
    DataLabRun,
    EconomicBriefing,
    IntegrationCredential,
    LabTemplate,
    KnowledgeCase,
    KnowledgeCaseItem,
    KnowledgeRecord,
    LiteratureEntry,
    User,
    UserSession,
    WorkspaceMemory,
    Workspace,
)
from .provider_catalog import apply_provider_defaults, get_provider_spec, is_local_provider_kind
from .security import (
    AccountLockedError,
    build_session_expiry,
    decrypt_secret,
    encrypt_secret,
    generate_session_token,
    hash_password,
    hash_token,
    validate_password_strength,
    validate_optional_source_url,
    validate_provider_base_url,
    verify_password,
)
from .utils import slugify, truncate_text


DATASET_KINDS = {"dataset_csv", "dataset_excel", "dataset_json"}
MAX_NOTE_CHARS = 500_000
MAX_WORKSPACE_MEMORY_CHARS = 4_000
WORKSPACE_MEMORY_LIMIT = 12
_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
ALLOWED_UPLOAD_KINDS = {
    "dataset_csv",
    "dataset_excel",
    "dataset_json",
    "document_pdf",
    "note_markdown",
    "note_text",
    "chart_png",
    "image_jpeg",
    "image_svg",
}
_KIND_EXTENSIONS = {
    "dataset_csv": {".csv"},
    "dataset_excel": {".xls", ".xlsx"},
    "dataset_json": {".json"},
    "document_pdf": {".pdf"},
    "note_markdown": {".md"},
    "note_text": {".txt"},
    "chart_png": {".png"},
    "image_jpeg": {".jpg", ".jpeg"},
    "image_svg": {".svg"},
}
_KIND_CONTENT_TYPES = {
    "dataset_csv": {"text/csv", "application/csv", "text/plain"},
    "dataset_excel": {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    "dataset_json": {"application/json", "text/json", "text/plain"},
    "document_pdf": {"application/pdf"},
    "note_markdown": {"text/markdown", "text/plain"},
    "note_text": {"text/plain"},
    "chart_png": {"image/png"},
    "image_jpeg": {"image/jpeg"},
    "image_svg": {"image/svg+xml", "text/plain"},
}

_PYPLOT: Any | None = None


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, set):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe_value(value.item())
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def _pyplot():
    global _PYPLOT
    if _PYPLOT is None:
        mpl_config_dir = Path(tempfile.gettempdir()) / "research_agent-mpl"
        mpl_config_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as pyplot

        _PYPLOT = pyplot
    return _PYPLOT


def _normalize_note_content(content: str) -> str:
    normalized = (content or "").strip()
    if len(normalized) < 2:
        raise ValueError("Content must be at least 2 characters.")
    if len(normalized) > MAX_NOTE_CHARS:
        raise ValueError(f"Content must be at most {MAX_NOTE_CHARS} characters.")
    return normalized


def _decode_text_sample(content: bytes) -> str:
    return content.decode("utf-8", errors="ignore")


def _looks_like_html_text(sample: str) -> bool:
    lowered = sample.lstrip().lower()
    return lowered.startswith(("<!doctype html", "<html", "<script", "<head", "<body"))


def _looks_like_csv_text(sample: str) -> bool:
    stripped = sample.strip()
    if not stripped or _looks_like_html_text(stripped):
        return False
    candidate = sample
    if not sample.endswith(("\n", "\r")) and "\n" in sample:
        candidate = sample.rsplit("\n", 1)[0]
    rows = [row for row in candidate.splitlines() if row.strip()]
    if len(rows) < 2:
        return False
    try:
        parsed_rows = [row for row in csv.reader(rows[:6]) if row]
    except csv.Error:
        return False
    widths = [len(row) for row in parsed_rows if len(row) > 1]
    if len(widths) < 2:
        return False
    baseline = widths[0]
    return sum(1 for width in widths if width == baseline) >= 2


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

BEGINNER_INTENT_RULES: list[dict[str, Any]] = [
    {
        "workflow_type": "data_processing",
        "processing_family": "visualization",
        "model_family": "",
        "model_type": "",
        "label": "Visualization",
        "terms": ["plot", "chart", "visualize", "visualization", "trend", "distribution", "图", "绘图", "可视化", "走势", "分布"],
        "reason": "The prompt focuses on inspection or plotting rather than estimation.",
    },
    {
        "workflow_type": "data_processing",
        "processing_family": "cleaning_transforms",
        "model_family": "",
        "model_type": "",
        "label": "Cleaning & Transforms",
        "terms": ["clean", "cleaning", "impute", "winsor", "outlier", "standardize", "normalize", "清洗", "插补", "缩尾", "异常值", "标准化", "归一化"],
        "reason": "The prompt focuses on cleaning or transformation before modeling.",
    },
    {
        "workflow_type": "data_processing",
        "processing_family": "time_series_features",
        "model_family": "",
        "model_type": "",
        "label": "Time-Series Features",
        "terms": ["lag", "lead", "return", "rolling", "difference", "time series feature", "滞后", "超前", "收益率", "滚动", "差分"],
        "reason": "The prompt explicitly mentions time-series feature construction.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "event_study",
        "label": "Event Study",
        "terms": ["event study", "dynamic treatment", "dynamic effect", "lead lag", "事件研究", "动态效应", "提前期", "滞后期"],
        "reason": "The prompt asks for dynamic effects around an event or treatment window.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "did",
        "label": "Difference-in-Differences",
        "terms": ["difference in differences", "did", "policy", "reform", "treated", "control group", "before after", "双重差分", "政策", "改革", "处理组", "对照组", "前后"],
        "reason": "The prompt suggests a policy or treatment comparison across groups and time.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "rdd",
        "label": "Regression Discontinuity",
        "terms": ["regression discontinuity", "rdd", "cutoff", "threshold", "score around", "断点回归", "阈值", "门槛", "分数附近"],
        "reason": "The prompt describes a cutoff-based design.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "iv_2sls",
        "label": "IV-2SLS",
        "terms": ["instrument", "iv", "endogenous", "exogenous shock", "工具变量", "内生性", "外生冲击"],
        "reason": "The prompt explicitly mentions endogeneity or instruments.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "gravity",
        "label": "Gravity Model",
        "terms": ["gravity", "trade", "export", "import", "bilateral", "distance", "贸易", "出口", "进口", "双边", "距离"],
        "reason": "The prompt focuses on bilateral flow relationships or trade-distance structure.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "arima",
        "label": "ARIMA Forecast",
        "terms": ["forecast", "predict", "univariate", "time series", "预测", "时间序列", "单变量"],
        "reason": "The prompt emphasizes forecasting one series over time.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "arch",
        "label": "ARCH",
        "terms": ["arch", "volatility clustering", "conditional volatility", "heteroskedasticity", "条件异方差", "波动聚集"],
        "reason": "The prompt asks for conditional volatility clustering in a single return series.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "garch",
        "label": "GARCH",
        "terms": ["garch", "persistent volatility", "conditional variance", "volatility persistence", "广义自回归条件异方差", "波动持续性"],
        "reason": "The prompt asks for persistent conditional variance dynamics.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "var",
        "label": "Vector Autoregression",
        "terms": ["var", "spillover", "interaction over time", "joint dynamics", "向量自回归", "溢出", "联动", "共同动态"],
        "reason": "The prompt suggests multivariate time-series dynamics.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "svar_irf",
        "label": "SVAR IRF",
        "terms": ["svar", "irf", "impulse response", "shock response", "structural var", "脉冲响应", "结构向量自回归"],
        "reason": "The prompt focuses on structural shocks and impulse-response analysis.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "virf",
        "label": "VIRF",
        "terms": ["virf", "volatility impulse response", "volatility shock", "garch irf", "波动脉冲响应"],
        "reason": "The prompt asks how volatility reacts over time after a shock.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "dy_connectedness",
        "label": "DY Connectedness",
        "terms": ["diebold yilmaz", "dy connectedness", "spillover index", "connectedness", "spillover table", "溢出指数", "连通性"],
        "reason": "The prompt focuses on generalized spillovers and connectedness indices.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "time_series_finance",
        "model_type": "bk_connectedness",
        "label": "BK Connectedness",
        "terms": ["barunik krehlik", "bk connectedness", "frequency connectedness", "frequency spillover", "频域连通性", "频域溢出"],
        "reason": "The prompt asks for frequency-domain connectedness across horizons.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "risk_management",
        "model_type": "historical_var",
        "label": "Historical VaR / ES",
        "terms": ["value at risk", "expected shortfall", "tail risk", "var", "es", "风险价值", "预期损失", "尾部风险"],
        "reason": "The prompt asks for risk or tail-loss diagnostics.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "derivatives_pricing",
        "model_type": "black_scholes",
        "label": "Black-Scholes",
        "terms": ["option", "call", "put", "strike", "derivative", "期权", "看涨", "看跌", "执行价", "衍生品"],
        "reason": "The prompt targets vanilla option pricing.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "portfolio_allocation",
        "model_type": "mean_variance",
        "label": "Mean-Variance Portfolio",
        "terms": ["portfolio", "allocation", "weights", "optimize portfolio", "投资组合", "资产配置", "权重"],
        "reason": "The prompt focuses on portfolio construction or allocation.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "asset_pricing",
        "model_type": "fama_french_3",
        "label": "Fama-French 3-Factor",
        "terms": ["fama french", "three factor", "factor model", "smb", "hml", "三因子", "因子模型"],
        "reason": "The prompt explicitly references multi-factor asset pricing.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "asset_pricing",
        "model_type": "capm",
        "label": "CAPM",
        "terms": ["capm", "beta", "market premium", "资产定价", "贝塔", "市场风险溢价"],
        "reason": "The prompt points to single-factor asset pricing or beta estimation.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "corporate_finance",
        "model_type": "altman_z",
        "label": "Altman Z-Score",
        "terms": ["bankruptcy", "distress", "z score", "default risk", "破产", "财务困境", "z值", "违约风险"],
        "reason": "The prompt focuses on corporate distress or default screening.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "macro_finance_dsge",
        "model_type": "taylor_rule",
        "label": "Taylor Rule",
        "terms": ["interest rate rule", "policy rate", "inflation gap", "output gap", "泰勒规则", "政策利率", "通胀缺口", "产出缺口"],
        "reason": "The prompt targets policy-rate response to macro gaps.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "fixed_effects",
        "label": "Fixed Effects",
        "terms": ["panel", "fixed effects", "firm year", "company year", "country year", "面板", "固定效应", "公司年度", "国家年度"],
        "reason": "The prompt suggests a panel structure with unit and time dimensions.",
    },
    {
        "workflow_type": "model",
        "processing_family": "",
        "model_family": "econometrics_baseline",
        "model_type": "logit",
        "label": "Logit",
        "terms": ["probability", "binary outcome", "default probability", "likelihood", "概率", "二元结果", "违约概率", "可能性"],
        "reason": "The prompt describes a binary outcome or probability question.",
    },
]

ROLE_KEYWORDS: dict[str, set[str]] = {
    "dependent": {"outcome", "dependent", "response", "target", "effect", "impact", "result", "因变量", "结果", "被解释", "影响", "收益", "回报", "利润", "销售", "收入", "价格", "增长", "风险", "波动", "通胀", "产出"},
    "independent": {"independent", "explanatory", "driver", "exposure", "factor", "key variable", "解释变量", "自变量", "驱动", "暴露", "因素"},
    "control": {"control", "covariate", "adjust", "baseline", "固定特征", "控制变量", "协变量", "调整"},
    "treatment": {"treatment", "policy", "reform", "shock", "intervention", "treated", "处理", "政策", "改革", "冲击", "干预", "试点"},
    "post": {"post", "after", "later", "post period", "事后", "政策后", "改革后", "之后"},
    "entity": {"firm", "company", "bank", "country", "city", "province", "region", "stock", "asset", "household", "entity", "unit", "企业", "公司", "银行", "国家", "城市", "省份", "地区", "股票", "资产", "个体", "单位"},
    "time": {"time", "date", "year", "quarter", "month", "week", "day", "period", "时间", "日期", "年份", "季度", "月份", "周", "天", "时期"},
    "event_time": {"event time", "relative time", "lead lag", "relative period", "事件时间", "相对时间", "提前期", "滞后期"},
    "running": {"running", "score", "cutoff", "threshold", "forcing", "门槛", "阈值", "分数", "运行变量"},
    "instrument": {"instrument", "iv", "exogenous", "工具", "工具变量", "外生"},
    "market": {"market", "benchmark", "mkt", "市场"},
    "risk_free": {"risk free", "rf", "无风险"},
    "smb": {"smb", "size factor", "规模因子"},
    "hml": {"hml", "value factor", "价值因子"},
    "distance": {"distance", "dist", "公里", "距离"},
    "origin_mass": {"origin", "exporter", "origin gdp", "起点", "出口方", "始发地"},
    "destination_mass": {"destination", "importer", "destination gdp", "终点", "进口方", "目的地"},
    "series": {"return", "price", "yield", "series", "收益率", "价格", "收益", "序列", "利率"},
    "impulse": {"impulse", "shock", "policy shock", "shock variable", "冲击", "脉冲"},
    "response": {"response", "responding variable", "affected series", "响应", "反应变量"},
    "spot": {"spot", "underlying", "现价", "标的"},
    "strike": {"strike", "执行价"},
    "maturity": {"maturity", "tenor", "expiry", "到期", "期限"},
    "rate": {"rate", "interest", "利率"},
    "volatility": {"volatility", "sigma", "波动率"},
    "working_capital": {"working capital", "营运资本"},
    "retained_earnings": {"retained earnings", "留存收益"},
    "ebit": {"ebit"},
    "market_equity": {"market equity", "market cap", "市值", "权益市值"},
    "total_assets": {"total assets", "assets", "总资产", "资产总额"},
    "total_liabilities": {"total liabilities", "liabilities", "总负债", "负债总额"},
    "sales": {"sales", "revenue", "turnover", "销售", "营收", "收入"},
    "net_income": {"net income", "profit", "净利润", "利润"},
    "revenue": {"revenue", "sales", "营收", "收入"},
    "equity": {"equity", "book equity", "净资产", "权益"},
    "inflation_gap": {"inflation gap", "inflation", "通胀缺口", "通胀"},
    "output_gap": {"output gap", "gdp gap", "产出缺口", "产出"},
}


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_preview_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _normalize_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in {"", "nan", "none", "nat", "null"}:
            return pd.NA
        return cleaned
    return value


def _unique_clean_columns(columns: list[Any]) -> tuple[list[str], dict[str, str]]:
    seen: dict[str, int] = {}
    cleaned_columns: list[str] = []
    source_map: dict[str, str] = {}
    for raw_column in columns:
        raw_text = str(raw_column).strip()
        base = slugify(raw_text or "column", max_length=48).replace("-", "_").strip("_") or "column"
        count = seen.get(base, 0)
        seen[base] = count + 1
        candidate = base if count == 0 else f"{base}_{count + 1}"
        cleaned_columns.append(candidate)
        source_map[candidate] = raw_text or candidate
    return cleaned_columns, source_map


def normalize_dataset_frame(frame: pd.DataFrame, *, drop_duplicates: bool = True) -> tuple[pd.DataFrame, dict[str, Any]]:
    prepared = frame.copy()
    cleaned_columns, source_map = _unique_clean_columns(list(prepared.columns))
    prepared.columns = cleaned_columns
    duplicate_rows = int(prepared.duplicated().sum())
    if drop_duplicates:
        prepared = prepared.drop_duplicates().copy()

    for column in prepared.columns:
        prepared[column] = prepared[column].map(_normalize_scalar)

    summary = {
        "source_columns": source_map,
        "duplicate_rows_detected": duplicate_rows,
        "rows_after_standardization": int(len(prepared)),
        "columns_after_standardization": list(prepared.columns),
    }
    return prepared, summary


def infer_column_role(series: pd.Series) -> str:
    if is_datetime64_any_dtype(series):
        return "date"
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    if is_numeric_dtype(non_null):
        unique_count = int(non_null.nunique(dropna=True))
        if unique_count <= 2:
            return "binary"
        return "numeric"

    numeric_candidate = pd.to_numeric(non_null, errors="coerce")
    numeric_share = float(numeric_candidate.notna().mean()) if len(non_null) else 0.0
    if numeric_share >= 0.9:
        unique_count = int(numeric_candidate.dropna().nunique())
        if unique_count <= 2:
            return "binary"
        return "numeric"

    text_values = non_null.astype(str).str.strip()
    lowered = text_values.str.lower()
    binary_tokens = {"0", "1", "true", "false", "yes", "no", "y", "n", "treated", "control", "pre", "post"}
    if text_values.nunique() <= 2 or set(lowered.unique()).issubset(binary_tokens):
        return "binary"

    date_candidate = pd.to_datetime(text_values, errors="coerce", format="mixed")
    date_share = float(date_candidate.notna().mean()) if len(text_values) else 0.0
    if date_share >= 0.8:
        return "date"

    unique_count = int(text_values.nunique())
    if unique_count <= min(20, max(3, len(text_values) // 2)):
        return "categorical"
    return "text"


def _column_profile(frame: pd.DataFrame, source_map: dict[str, str], column: str) -> dict[str, Any]:
    series = frame[column]
    role = infer_column_role(series)
    non_null = series.dropna()
    profile = {
        "name": column,
        "source_name": source_map.get(column, column),
        "role": role,
        "dtype": str(series.dtype),
        "missing_count": int(series.isna().sum()),
        "non_null_count": int(non_null.shape[0]),
        "unique_count": int(non_null.nunique(dropna=True)),
        "sample_values": [_serialize_preview_value(value) for value in non_null.head(4).tolist()],
    }

    numeric_series = pd.to_numeric(series, errors="coerce")
    if role in {"numeric", "binary"} and numeric_series.notna().any():
        clean_numeric = numeric_series.dropna()
        profile.update(
            {
                "mean": _safe_float(clean_numeric.mean()),
                "std": _safe_float(clean_numeric.std()),
                "min": _safe_float(clean_numeric.min()),
                "max": _safe_float(clean_numeric.max()),
            }
        )
    elif role == "date":
        date_series = pd.to_datetime(series, errors="coerce").dropna()
        if not date_series.empty:
            profile.update(
                {
                    "min": date_series.min().isoformat(),
                    "max": date_series.max().isoformat(),
                }
            )
    return profile


def _frame_preview_rows(frame: pd.DataFrame, *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {column: _serialize_preview_value(value) for column, value in row.items()}
        for row in frame.head(limit).to_dict(orient="records")
    ]


def validate_email(value: str) -> str:
    raw_email = str(value or "")
    if raw_email != raw_email.strip() or any(character.isspace() for character in raw_email):
        raise ValueError("A valid email address is required.")
    email = raw_email.lower()
    if len(email) > 320 or email.count("@") != 1:
        raise ValueError("A valid email address is required.")
    local_part, domain = email.split("@", 1)
    if (
        not local_part
        or not domain
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or domain.endswith(".")
        or ".." in domain
        or not _EMAIL_PATTERN.fullmatch(email)
    ):
        raise ValueError("A valid email address is required.")
    return email


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at.isoformat(),
    }


def serialize_workspace(workspace: Workspace) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "team_id": workspace.team_id,
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "research_domain": workspace.research_domain,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def serialize_integration(integration: IntegrationCredential) -> dict[str, Any]:
    provider = get_provider_spec(integration.kind, "local-model") or {}
    provider_name = integration.config_json.get("provider_name") or provider.get("label", integration.kind)
    docs_url = integration.config_json.get("docs_url") or provider.get("docs_url", "")
    return {
        "id": integration.id,
        "label": integration.label,
        "category": integration.category,
        "kind": integration.kind,
        "provider_name": provider_name,
        "docs_url": docs_url,
        "base_url": integration.base_url,
        "model": integration.model,
        "is_default": integration.is_default,
        "config": integration.config_json,
        "created_at": integration.created_at.isoformat(),
    }


def _template_source_value(metadata: dict[str, Any]) -> str:
    return str(metadata.get("template_name") or metadata.get("template_id") or "").strip()


def _variant_source_value(metadata: dict[str, Any]) -> str:
    label = str(metadata.get("variant_label") or "").strip()
    if label:
        return label
    variant_spec = metadata.get("variant_spec")
    if isinstance(variant_spec, dict) and variant_spec:
        return "custom"
    return ""


def _result_detail_path(
    metadata: dict[str, Any],
    *,
    record_id: str = "",
    asset_id: str = "",
    fallback: str = "",
) -> str:
    detail_path = str(metadata.get("detail_path") or metadata.get("result_detail_path") or "").strip()
    if detail_path:
        return detail_path
    workflow_type = str(metadata.get("workflow_type") or "").strip()
    if (workflow_type == "model" or metadata.get("model_type")) and record_id:
        return f"/data-lab/results/models/{record_id}"
    if workflow_type == "optimization" and record_id:
        return f"/data-lab/results/optimization/{record_id}"
    if workflow_type == "data_processing" and asset_id:
        return f"/data-lab/results/processing/{asset_id}"
    return fallback


def _status_bundle(*, status: str, reason: str, next_action: str, detail_path: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "detail_path": detail_path,
    }


def serialize_knowledge_record(record: KnowledgeRecord, *, include_content: bool = True) -> dict[str, Any]:
    content = record.content or ""
    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    archive_meta = metadata.get("archive", {}) if isinstance(metadata.get("archive"), dict) else {}
    archived_at = str(metadata.get("archived_at") or archive_meta.get("at") or "").strip()
    archived_reason = str(metadata.get("archived_reason") or archive_meta.get("reason") or "").strip()
    is_archived = bool(metadata.get("is_archived") or archive_meta.get("is_archived") or archived_at)
    detail_path = _result_detail_path(metadata, record_id=record.id, fallback="/knowledge-base")
    if is_archived:
        status_payload = _status_bundle(
            status="archived",
            reason=archived_reason or "This note is archived.",
            next_action="restore_or_review",
            detail_path="/knowledge-base",
        )
    elif metadata.get("workflow_type") == "optimization":
        status_payload = _status_bundle(
            status="ready",
            reason="Optimization result is ready for review.",
            next_action="open_detail",
            detail_path=detail_path,
        )
    elif metadata.get("workflow_type") == "model" or metadata.get("model_type"):
        status_payload = _status_bundle(
            status="ready",
            reason="Model result is ready for review.",
            next_action="open_detail",
            detail_path=detail_path,
        )
    elif metadata.get("briefing_id"):
        status_payload = _status_bundle(
            status="ready",
            reason="Briefing note is linked into the workspace knowledge base.",
            next_action="open_note",
            detail_path="/knowledge-base",
        )
    elif metadata.get("source_type") == "paper_library":
        status_payload = _status_bundle(
            status="ready",
            reason="Paper note is ready for reuse in cases or follow-up derivations.",
            next_action="open_note",
            detail_path="/knowledge-base",
        )
    else:
        status_payload = _status_bundle(
            status="ready",
            reason="Workspace note is available.",
            next_action="open_note",
            detail_path="/knowledge-base",
        )
    return {
        "id": record.id,
        "title": record.title,
        "content": content if include_content else "",
        "content_excerpt": truncate_text(content, 220),
        "content_length": len(content),
        "tags": record.tags_json,
        "metadata": metadata,
        "template_source": _template_source_value(metadata),
        "variant_source": _variant_source_value(metadata),
        "is_archived": is_archived,
        "archived_at": archived_at,
        "archived_reason": archived_reason,
        **status_payload,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def serialize_knowledge_case(
    case: KnowledgeCase,
    *,
    item_count: int = 0,
    latest_item_at: str = "",
    item_types: list[str] | None = None,
) -> dict[str, Any]:
    status_payload = _status_bundle(
        status="ready" if item_count else "empty",
        reason="Case contains linked workspace evidence." if item_count else "Case is empty and ready for the first item.",
        next_action="open_case" if item_count else "add_case_item",
        detail_path="/knowledge-base",
    )
    return {
        "id": case.id,
        "title": case.title,
        "description": case.description,
        "tags": case.tags_json,
        "metadata": case.metadata_json,
        "item_count": item_count,
        "latest_item_at": latest_item_at,
        "item_types": item_types or [],
        **status_payload,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


def serialize_knowledge_case_item(
    item: KnowledgeCaseItem,
    *,
    resolved_title: str = "",
    resolved_summary: str = "",
    resolved_detail_path: str = "",
    resolved_download_path: str = "",
    resolved_source_url: str = "",
    resolved_exists: bool = True,
) -> dict[str, Any]:
    metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
    status_payload = _status_bundle(
        status="ready" if resolved_exists else "missing",
        reason="Linked resource is available." if resolved_exists else "Linked resource is no longer available in this workspace.",
        next_action="open_detail" if resolved_exists and resolved_detail_path else "review_case_item",
        detail_path=resolved_detail_path,
    )
    return {
        "id": item.id,
        "case_id": item.case_id,
        "item_type": item.item_type,
        "ref_id": item.ref_id,
        "title": resolved_title or item.title_snapshot,
        "summary": resolved_summary or item.summary_snapshot,
        "title_snapshot": item.title_snapshot,
        "summary_snapshot": item.summary_snapshot,
        "metadata": metadata,
        "detail_path": resolved_detail_path,
        "download_path": resolved_download_path,
        "source_url": resolved_source_url,
        "exists": resolved_exists,
        **status_payload,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def serialize_asset(asset: DataAsset) -> dict[str, Any]:
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    filename = metadata.get("original_filename") or asset.title
    processing_result = metadata.get("processing_result") if isinstance(metadata.get("processing_result"), dict) else {}
    detail_path = _result_detail_path(processing_result or metadata, asset_id=asset.id, fallback="")
    if processing_result:
        status_payload = _status_bundle(
            status="ready",
            reason="Processing result is ready for review.",
            next_action="open_detail",
            detail_path=detail_path,
        )
    elif metadata.get("analysis_kind") == "plot":
        status_payload = _status_bundle(
            status="ready",
            reason="Visualization asset is ready for review.",
            next_action="open_detail" if detail_path else "download_asset",
            detail_path=detail_path,
        )
    else:
        status_payload = _status_bundle(
            status="ready",
            reason="Uploaded asset is stored in the workspace.",
            next_action="download_asset",
            detail_path=detail_path,
        )
    return {
        "id": asset.id,
        "kind": asset.kind,
        "title": asset.title,
        "filename": filename,
        "description": asset.description,
        "content_type": asset.content_type,
        "source_url": asset.source_url,
        "metadata": metadata,
        "download_path": f"/api/assets/{asset.id}/download",
        "template_source": _template_source_value(processing_result or metadata),
        "variant_source": _variant_source_value(processing_result or metadata),
        **status_payload,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }


def register_user(db: Session, *, email: str, password: str, full_name: str) -> User:
    normalized_email = validate_email(email)
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise ValueError("This email is already registered.")
    validate_password_strength(password, email=normalized_email)

    user = User(
        email=normalized_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    db.add(
        Workspace(
            owner_user_id=user.id,
            name="Economic Research Workspace",
            slug="economic-research-workspace",
            description="Primary private workspace for economics research operations.",
            research_domain="economics",
        )
    )
    db.flush()
    return user


def login_user(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_address: str = "",
) -> tuple[User, str]:
    normalized_email = validate_email(email)
    purge_expired_sessions(db)
    assert_login_allowed(db, email=normalized_email, ip_address=ip_address)
    user = db.scalar(select(User).where(User.email == normalized_email))
    user_locked_until = _ensure_utc(user.locked_until) if user else None
    if user and user_locked_until and user_locked_until > datetime.now(timezone.utc):
        raise AccountLockedError("This account is temporarily locked. Try again later.")
    if not user or not verify_password(password, user.password_hash):
        record_login_failure(db, email=normalized_email, ip_address=ip_address, user=user)
        raise PermissionError("Invalid email or password.")
    clear_login_failures(db, email=normalized_email, ip_address=ip_address, user=user)
    token = generate_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=build_session_expiry(settings),
        )
    )
    db.flush()
    return user, token


def logout_user_session(db: Session, *, token: str) -> None:
    if not token:
        return
    purge_expired_sessions(db)
    session_row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session_row:
        db.delete(session_row)
        db.flush()


def get_current_user(db: Session, token: str) -> User:
    purge_expired_sessions(db)
    session_row = db.scalar(
        select(UserSession).where(
            and_(
                UserSession.token_hash == hash_token(token),
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
    )
    if not session_row:
        raise PermissionError("Invalid or expired session token.")
    session_row.last_seen_at = datetime.now(timezone.utc)
    user = db.get(User, session_row.user_id)
    if not user or not user.is_active:
        raise PermissionError("The account is inactive.")
    user_locked_until = _ensure_utc(user.locked_until)
    if user_locked_until and user_locked_until > datetime.now(timezone.utc):
        raise AccountLockedError("This account is temporarily locked. Try again later.")
    return user


def get_current_user_optional(db: Session, token: str) -> User | None:
    if not token:
        return None
    try:
        return get_current_user(db, token)
    except PermissionError:
        return None


def create_workspace(
    db: Session,
    *,
    user: User,
    name: str,
    description: str = "",
    research_domain: str = "economics",
) -> Workspace:
    workspace = Workspace(
        owner_user_id=user.id,
        name=name.strip(),
        slug=slugify(name),
        description=description.strip(),
        research_domain=research_domain.strip() or "economics",
    )
    db.add(workspace)
    db.flush()
    return workspace


def list_workspaces(db: Session, *, user: User) -> list[Workspace]:
    return list(
        db.scalars(
            select(Workspace)
            .where(Workspace.owner_user_id == user.id)
            .order_by(Workspace.created_at.desc())
        )
    )


def get_workspace_for_user(db: Session, *, user: User, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    return workspace


def _workspace_memory_title(title: str, content: str) -> str:
    normalized = str(title or "").strip()
    if normalized:
        return truncate_text(normalized, 200)
    first_line = next((line.strip() for line in str(content or "").splitlines() if line.strip()), "")
    return truncate_text(first_line or "Workspace memory", 200)


def serialize_workspace_memory(memory: WorkspaceMemory, *, include_content: bool = True) -> dict[str, Any]:
    return {
        "id": memory.id,
        "title": memory.title,
        "content": memory.content if include_content else "",
        "content_excerpt": truncate_text(memory.content or "", 220),
        "metadata": memory.metadata_json if isinstance(memory.metadata_json, dict) else {},
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
    }


def list_workspace_memories(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    limit: int = WORKSPACE_MEMORY_LIMIT,
) -> list[WorkspaceMemory]:
    return list(
        db.scalars(
            select(WorkspaceMemory)
            .where(
                and_(
                    WorkspaceMemory.owner_user_id == user.id,
                    WorkspaceMemory.workspace_id == workspace.id,
                )
            )
            .order_by(WorkspaceMemory.updated_at.desc(), WorkspaceMemory.created_at.desc())
            .limit(max(1, min(limit, WORKSPACE_MEMORY_LIMIT)))
        )
    )


def get_owned_workspace_memory(
    db: Session,
    *,
    user: User,
    memory_id: str,
    workspace: Workspace | None = None,
) -> WorkspaceMemory:
    memory = db.get(WorkspaceMemory, memory_id)
    if not memory or memory.owner_user_id != user.id:
        raise FileNotFoundError("Workspace memory not found.")
    if workspace and memory.workspace_id != workspace.id:
        raise FileNotFoundError("Workspace memory not found.")
    return memory


def _prune_workspace_memories(db: Session, *, user: User, workspace: Workspace) -> None:
    rows = list(
        db.scalars(
            select(WorkspaceMemory)
            .where(
                and_(
                    WorkspaceMemory.owner_user_id == user.id,
                    WorkspaceMemory.workspace_id == workspace.id,
                )
            )
            .order_by(WorkspaceMemory.updated_at.desc(), WorkspaceMemory.created_at.desc())
        )
    )
    for row in rows[WORKSPACE_MEMORY_LIMIT:]:
        db.delete(row)


def create_workspace_memory(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    title: str = "",
    content: str,
    metadata: dict[str, Any] | None = None,
) -> WorkspaceMemory:
    normalized_content = _normalize_note_content(content)
    if len(normalized_content) > MAX_WORKSPACE_MEMORY_CHARS:
        raise ValueError(f"Memory content must be at most {MAX_WORKSPACE_MEMORY_CHARS} characters.")
    memory = WorkspaceMemory(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title=_workspace_memory_title(title, normalized_content),
        content=normalized_content,
        metadata_json=dict(metadata or {}) if isinstance(metadata, dict) else {},
    )
    db.add(memory)
    db.flush()
    _prune_workspace_memories(db, user=user, workspace=workspace)
    db.flush()
    return memory


def delete_workspace_memory(
    db: Session,
    *,
    user: User,
    memory_id: str,
    workspace: Workspace | None = None,
) -> None:
    memory = get_owned_workspace_memory(db, user=user, memory_id=memory_id, workspace=workspace)
    db.delete(memory)


def create_data_lab_run(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    workflow_type: str,
    family: str = "",
    method: str = "",
    title: str = "",
    source_asset_id: str = "",
    request_payload: dict[str, Any] | None = None,
) -> DataLabRun:
    run = DataLabRun(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        workflow_type=str(workflow_type or "processing").strip() or "processing",
        family=str(family or "").strip(),
        method=str(method or "").strip(),
        title=truncate_text(str(title or "").strip(), 240),
        source_asset_id=str(source_asset_id or "").strip() or None,
        request_json=_json_safe_value(dict(request_payload or {}) if isinstance(request_payload, dict) else {}),
    )
    db.add(run)
    db.flush()
    return run


def get_owned_data_lab_run(db: Session, *, user: User, run_id: str) -> DataLabRun:
    run = db.get(DataLabRun, run_id)
    if not run or run.owner_user_id != user.id:
        raise FileNotFoundError("Data Lab run not found.")
    return run


def finalize_data_lab_run_success(
    db: Session,
    *,
    user: User,
    run_id: str,
    title: str = "",
    summary: str = "",
    detail_path: str = "",
    result_asset_id: str = "",
    result_record_id: str = "",
    output_payload: dict[str, Any] | None = None,
) -> DataLabRun:
    run = get_owned_data_lab_run(db, user=user, run_id=run_id)
    run.status = "ready"
    if title.strip():
        run.title = truncate_text(title.strip(), 240)
    run.summary = truncate_text(str(summary or "").strip(), 600)
    run.detail_path = str(detail_path or "").strip()
    run.result_asset_id = str(result_asset_id or "").strip() or None
    run.result_record_id = str(result_record_id or "").strip() or None
    run.error_summary = ""
    run.output_json = _json_safe_value(dict(output_payload or {}) if isinstance(output_payload, dict) else {})
    run.finished_at = datetime.now(timezone.utc)
    run.updated_at = run.finished_at
    db.flush()
    return run


def finalize_data_lab_run_failure(
    db: Session,
    *,
    user: User,
    run_id: str,
    error: Exception | str,
    title: str = "",
    output_payload: dict[str, Any] | None = None,
) -> DataLabRun:
    run = get_owned_data_lab_run(db, user=user, run_id=run_id)
    run.status = "failed"
    if title.strip():
        run.title = truncate_text(title.strip(), 240)
    run.error_summary = truncate_text(str(error or "Data Lab run failed.").strip(), 600) or "Data Lab run failed."
    run.output_json = _json_safe_value(dict(output_payload or {}) if isinstance(output_payload, dict) else {})
    run.finished_at = datetime.now(timezone.utc)
    run.updated_at = run.finished_at
    db.flush()
    return run


def list_data_lab_runs(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    workflow_type: str = "",
    limit: int = 24,
) -> list[DataLabRun]:
    stmt = (
        select(DataLabRun)
        .where(
            and_(
                DataLabRun.owner_user_id == user.id,
                DataLabRun.workspace_id == workspace.id,
            )
        )
        .order_by(DataLabRun.updated_at.desc(), DataLabRun.started_at.desc(), DataLabRun.created_at.desc())
        .limit(max(1, min(limit, 120)))
    )
    rows = list(db.scalars(stmt))
    if workflow_type:
        rows = [row for row in rows if row.workflow_type == workflow_type]
    return rows


def serialize_data_lab_run(db: Session, *, user: User, run: DataLabRun) -> dict[str, Any]:
    output = dict(run.output_json or {}) if isinstance(run.output_json, dict) else {}
    updated_at = _ensure_utc(run.finished_at) or _ensure_utc(run.updated_at) or _ensure_utc(run.started_at)
    base = {
        "id": run.id,
        "run_id": run.id,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "family": run.family,
        "method": run.method,
        "title": run.title or output.get("title") or "Data Lab run",
        "summary": str(output.get("summary") or run.summary or "").strip(),
        "detail_path": run.detail_path or str(output.get("detail_path") or output.get("result_detail_path") or "").strip(),
        "result_detail_path": run.detail_path or str(output.get("result_detail_path") or output.get("detail_path") or "").strip(),
        "source_asset_id": run.source_asset_id or "",
        "result_asset_id": run.result_asset_id or "",
        "result_record_id": run.result_record_id or "",
        "ref_id": "",
        "download_path": "",
        "created_at": (_ensure_utc(run.started_at) or datetime.now(timezone.utc)).isoformat(),
        "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
        "metadata": {},
    }
    if run.status == "failed":
        reason = run.error_summary or "The latest run failed."
        if run.workflow_type == "model":
            base["metadata"] = {
                "workflow_type": "model",
                "model_family": run.family,
                "model_type": run.method,
                "model_label": run.title or run.method or "Model run",
            }
        elif run.workflow_type == "optimization":
            base["suite_label"] = run.title or "Optimization Suite"
        else:
            base["processing_family"] = run.family or "data_processing"
        return {
            **base,
            "reason": reason,
            "next_action": "review_failure",
        }

    if run.result_asset_id:
        asset = db.get(DataAsset, run.result_asset_id)
        if asset and asset.owner_user_id == user.id and asset.workspace_id == run.workspace_id:
            payload = serialize_asset(asset)
            payload["run_id"] = run.id
            payload["ref_id"] = asset.id
            payload["created_at"] = base["created_at"]
            payload["updated_at"] = base["updated_at"]
            payload["status"] = run.status
            if base["detail_path"]:
                payload["detail_path"] = base["detail_path"]
                payload["result_detail_path"] = base["detail_path"]
            return payload

    if run.result_record_id:
        record = db.get(KnowledgeRecord, run.result_record_id)
        if record and record.owner_user_id == user.id and record.workspace_id == run.workspace_id:
            payload = serialize_knowledge_record(record, include_content=False)
            payload["run_id"] = run.id
            payload["ref_id"] = record.id
            payload["created_at"] = base["created_at"]
            payload["updated_at"] = base["updated_at"]
            payload["status"] = run.status
            if base["detail_path"]:
                payload["detail_path"] = base["detail_path"]
                payload["result_detail_path"] = base["detail_path"]
            return payload

    return {
        **base,
        "reason": run.summary or "Run completed.",
        "next_action": "open_detail" if base["detail_path"] else "review_history",
    }


def create_integration(
    db: Session,
    settings: Settings,
    *,
    user: User,
    label: str,
    category: str,
    kind: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    is_default: bool = False,
    config: dict[str, Any] | None = None,
) -> IntegrationCredential:
    normalized_category = category.strip()
    normalized_kind = kind.strip()
    blocked_model_kinds = {
        "openai",
        "anthropic",
        "gemini",
        "ollama",
        "vllm",
        "lmstudio",
        "local_openai_compatible",
    }
    if normalized_category == "llm" or normalized_kind in blocked_model_kinds:
        raise ValueError("Runtime model integrations are not available in the current product scope.")
    if not api_key.strip() and not is_local_provider_kind(normalized_kind):
        raise ValueError("API key is required.")
    resolved_base_url, resolved_model, provider = apply_provider_defaults(
        kind=normalized_kind,
        base_url=base_url,
        model=model,
        default_openai_model=settings.model,
    )
    if provider and provider.get("category"):
        normalized_category = provider["category"]
    resolved_base_url = validate_provider_base_url(settings, resolved_base_url)
    if is_default:
        for current in db.scalars(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == normalized_category,
                    IntegrationCredential.is_default.is_(True),
                )
            )
        ):
            current.is_default = False
    config_json = dict(config or {})
    if provider:
        config_json.setdefault("provider_name", provider.get("label", normalized_kind))
        config_json.setdefault("docs_url", provider.get("docs_url", ""))
        config_json.setdefault("provider_family", provider.get("family", ""))
    integration = IntegrationCredential(
        owner_user_id=user.id,
        label=label.strip(),
        category=normalized_category,
        kind=normalized_kind,
        api_key_encrypted=encrypt_secret(settings, api_key.strip()) if api_key.strip() else "",
        base_url=resolved_base_url,
        model=resolved_model,
        is_default=is_default,
        config_json=config_json,
    )
    db.add(integration)
    db.flush()
    return integration


def list_integrations(db: Session, *, user: User) -> list[IntegrationCredential]:
    return list(
        db.scalars(
            select(IntegrationCredential)
            .where(IntegrationCredential.owner_user_id == user.id)
            .order_by(IntegrationCredential.category.asc(), IntegrationCredential.created_at.desc())
        )
    )


def resolve_integration(
    db: Session,
    *,
    user: User,
    integration_id: str | None = None,
    category: str = "llm",
) -> IntegrationCredential:
    if integration_id:
        integration = db.get(IntegrationCredential, integration_id)
        if not integration or integration.owner_user_id != user.id:
            raise FileNotFoundError("Integration not found.")
        return integration
    integration = db.scalar(
        select(IntegrationCredential).where(
            and_(
                IntegrationCredential.owner_user_id == user.id,
                IntegrationCredential.category == category,
                IntegrationCredential.is_default.is_(True),
            )
        )
    )
    if not integration:
        raise FileNotFoundError(f"No default {category} integration is configured.")
    return integration


def test_integration(db: Session, settings: Settings, *, user: User, integration_id: str) -> dict[str, Any]:
    integration = db.get(IntegrationCredential, integration_id)
    if not integration or integration.owner_user_id != user.id:
        raise FileNotFoundError("Integration not found.")
    if integration.category == "llm":
        return {
            "status": "unavailable",
            "preview": "Runtime model integrations are disabled in this deployment.",
            "reason": "Runtime provider management is not part of the current product scope.",
        }
    if integration.kind == "fred":
        try:
            response = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "FEDFUNDS",
                    "api_key": decrypt_secret(settings, integration.api_key_encrypted),
                    "file_type": "json",
                    "limit": 1,
                },
                timeout=20,
            )
            response.raise_for_status()
            return {"status": "ok", "preview": "FRED API key is valid."}
        except requests.Timeout:
            return {"status": "error", "preview": "Connection test failed.", "reason": "Provider request timed out."}
        except requests.RequestException:
            return {"status": "error", "preview": "Connection test failed.", "reason": "Provider request failed."}
    return {"status": "ok", "preview": "Integration stored successfully."}


def delete_integration(db: Session, *, user: User, integration_id: str) -> None:
    integration = db.get(IntegrationCredential, integration_id)
    if not integration or integration.owner_user_id != user.id:
        raise FileNotFoundError("Integration not found.")
    db.delete(integration)


def create_knowledge_record(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    title: str,
    content: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeRecord:
    metadata_payload = _json_safe_value(dict(metadata or {}) if isinstance(metadata, dict) else {})
    normalized_content = _normalize_note_content(content)
    record = KnowledgeRecord(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title=title.strip(),
        content=normalized_content,
        tags_json=list(dict.fromkeys(tag.strip() for tag in (tags or []) if tag.strip())),
        metadata_json=metadata_payload,
    )
    db.add(record)
    db.flush()
    if metadata_payload.get("workflow_type") == "model" or metadata_payload.get("model_type"):
        enriched_metadata = dict(metadata_payload)
        enriched_metadata.setdefault("workflow_type", "model")
        enriched_metadata.setdefault("result_record_id", record.id)
        enriched_metadata.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
        record.metadata_json = _json_safe_value(enriched_metadata)
        db.flush()
    return record


def is_knowledge_record_archived(record: KnowledgeRecord) -> bool:
    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    archive_meta = metadata.get("archive", {}) if isinstance(metadata.get("archive"), dict) else {}
    return bool(metadata.get("is_archived") or archive_meta.get("is_archived") or metadata.get("archived_at") or archive_meta.get("at"))


def list_knowledge_records(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    include_archived: bool = False,
) -> list[KnowledgeRecord]:
    rows = list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc())
        )
    )
    if include_archived:
        return rows
    return [row for row in rows if not is_knowledge_record_archived(row)]


def get_owned_knowledge_record(db: Session, *, user: User, record_id: str) -> KnowledgeRecord:
    record = db.get(KnowledgeRecord, record_id)
    if not record or record.owner_user_id != user.id:
        raise FileNotFoundError("Knowledge record not found.")
    return record


def get_owned_asset(db: Session, *, user: User, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id:
        raise FileNotFoundError("Asset not found.")
    return asset


def _normalize_tag_list(tags: list[str] | None) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in (tags or []) if str(tag).strip()))


def create_knowledge_case(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeCase:
    case = KnowledgeCase(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title=title.strip(),
        description=description.strip(),
        tags_json=_normalize_tag_list(tags),
        metadata_json=dict(metadata or {}) if isinstance(metadata, dict) else {},
    )
    db.add(case)
    db.flush()
    return case


def serialize_lab_template(template: LabTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "template_scope": template.template_scope,
        "workflow_type": template.workflow_type,
        "family": template.family,
        "method": template.method,
        "name": template.name,
        "description": template.description,
        "is_default": template.is_default,
        "specification": template.specification_json if isinstance(template.specification_json, dict) else {},
        "metadata": template.metadata_json if isinstance(template.metadata_json, dict) else {},
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
    }


def list_lab_templates(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    template_scope: str,
    workflow_type: str = "",
    family: str = "",
    method: str = "",
) -> list[LabTemplate]:
    stmt = (
        select(LabTemplate)
        .where(
            and_(
                LabTemplate.owner_user_id == user.id,
                LabTemplate.workspace_id == workspace.id,
                LabTemplate.template_scope == template_scope.strip(),
            )
        )
        .order_by(LabTemplate.is_default.desc(), LabTemplate.updated_at.desc(), LabTemplate.created_at.desc())
    )
    rows = list(db.scalars(stmt))
    if workflow_type:
        rows = [row for row in rows if row.workflow_type == workflow_type]
    if family:
        rows = [row for row in rows if row.family == family]
    if method:
        rows = [row for row in rows if row.method == method]
    return rows


def get_owned_lab_template(db: Session, *, user: User, template_id: str) -> LabTemplate:
    template = db.get(LabTemplate, template_id)
    if not template or template.owner_user_id != user.id:
        raise FileNotFoundError("Lab template not found.")
    return template


def create_lab_template(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    template_scope: str,
    workflow_type: str,
    family: str,
    method: str,
    name: str,
    description: str = "",
    specification: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    is_default: bool = False,
) -> LabTemplate:
    normalized_scope = template_scope.strip()
    normalized_workflow = workflow_type.strip()
    normalized_family = family.strip()
    normalized_method = method.strip()
    normalized_name = name.strip()
    if not normalized_scope:
        raise ValueError("Template scope is required.")
    if not normalized_workflow:
        raise ValueError("Workflow type is required.")
    if not normalized_name:
        raise ValueError("Template name is required.")
    if is_default:
        for existing in list_lab_templates(
            db,
            user=user,
            workspace=workspace,
            template_scope=normalized_scope,
            workflow_type=normalized_workflow,
            family=normalized_family,
            method=normalized_method,
        ):
            if existing.is_default:
                existing.is_default = False
    template = LabTemplate(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        template_scope=normalized_scope,
        workflow_type=normalized_workflow,
        family=normalized_family,
        method=normalized_method,
        name=normalized_name,
        description=description.strip(),
        is_default=bool(is_default),
        specification_json=dict(specification or {}) if isinstance(specification, dict) else {},
        metadata_json=dict(metadata or {}) if isinstance(metadata, dict) else {},
    )
    db.add(template)
    db.flush()
    return template


def list_knowledge_cases(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> list[KnowledgeCase]:
    return list(
        db.scalars(
            select(KnowledgeCase)
            .where(
                and_(
                    KnowledgeCase.owner_user_id == user.id,
                    KnowledgeCase.workspace_id == workspace.id,
                )
            )
            .order_by(KnowledgeCase.updated_at.desc(), KnowledgeCase.created_at.desc())
        )
    )


def get_owned_knowledge_case(db: Session, *, user: User, case_id: str) -> KnowledgeCase:
    case = db.get(KnowledgeCase, case_id)
    if not case or case.owner_user_id != user.id:
        raise FileNotFoundError("Knowledge case not found.")
    return case


def update_knowledge_case(
    db: Session,
    *,
    user: User,
    case_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeCase:
    case = get_owned_knowledge_case(db, user=user, case_id=case_id)
    if title is not None:
        case.title = title.strip()
    if description is not None:
        case.description = description.strip()
    if tags is not None:
        case.tags_json = _normalize_tag_list(tags)
    if metadata is not None and isinstance(metadata, dict):
        case.metadata_json = dict(metadata)
    case.updated_at = datetime.now(timezone.utc)
    db.flush()
    return case


def delete_knowledge_case(db: Session, *, user: User, case_id: str) -> None:
    case = get_owned_knowledge_case(db, user=user, case_id=case_id)
    db.delete(case)


def list_knowledge_case_items(
    db: Session,
    *,
    user: User,
    case: KnowledgeCase,
) -> list[KnowledgeCaseItem]:
    return list(
        db.scalars(
            select(KnowledgeCaseItem)
            .where(
                and_(
                    KnowledgeCaseItem.owner_user_id == user.id,
                    KnowledgeCaseItem.workspace_id == case.workspace_id,
                    KnowledgeCaseItem.case_id == case.id,
                )
            )
            .order_by(KnowledgeCaseItem.created_at.desc(), KnowledgeCaseItem.updated_at.desc())
        )
    )


def get_owned_knowledge_case_item(
    db: Session,
    *,
    user: User,
    case: KnowledgeCase,
    item_id: str,
) -> KnowledgeCaseItem:
    item = db.get(KnowledgeCaseItem, item_id)
    if not item or item.owner_user_id != user.id or item.case_id != case.id or item.workspace_id != case.workspace_id:
        raise FileNotFoundError("Knowledge case item not found.")
    return item


def _resolve_case_reference(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    item_type: str,
    ref_id: str,
) -> dict[str, Any]:
    normalized_type = item_type.strip().lower()
    if normalized_type == "knowledge_record":
        record = get_owned_knowledge_record(db, user=user, record_id=ref_id)
        if record.workspace_id != workspace.id:
            raise FileNotFoundError("Knowledge record not found.")
        metadata = dict(record.metadata_json or {})
        detail_path = _result_detail_path(metadata, record_id=record.id, fallback="/knowledge-base")
        return {
            "title": record.title,
            "summary": truncate_text(record.content or "", 240),
            "metadata": {
                "source_kind": "knowledge_record",
                "knowledge_record_id": record.id,
                "workflow_type": metadata.get("workflow_type", ""),
                "model_type": metadata.get("model_type", ""),
                "note_template": metadata.get("note_template", ""),
            },
            "detail_path": detail_path,
            "download_path": "",
            "source_url": str(metadata.get("landing_page_url") or metadata.get("source_url") or "").strip(),
        }
    if normalized_type == "data_asset":
        asset = get_owned_asset(db, user=user, asset_id=ref_id)
        if asset.workspace_id != workspace.id:
            raise FileNotFoundError("Asset not found.")
        asset_metadata = dict(asset.metadata_json or {})
        processing = asset_metadata.get("processing_result") if isinstance(asset_metadata.get("processing_result"), dict) else {}
        detail_path = _result_detail_path(processing or asset_metadata, asset_id=asset.id, fallback="")
        summary = str(asset.description or "").strip() or str(asset_metadata.get("summary") or "").strip()
        if not summary and processing:
            processing_summary = processing.get("summary") if isinstance(processing.get("summary"), dict) else {}
            rows_after_prepare = processing_summary.get("rows_after_prepare")
            if rows_after_prepare is not None:
                summary = f"Prepared rows: {rows_after_prepare}"
        return {
            "title": asset.title,
            "summary": truncate_text(summary or f"{asset.kind} saved in the private workspace.", 240),
            "metadata": {
                "source_kind": "data_asset",
                "asset_id": asset.id,
                "asset_kind": asset.kind,
                "analysis_kind": asset_metadata.get("analysis_kind", ""),
                "processing_family": processing.get("processing_family", ""),
            },
            "detail_path": detail_path,
            "download_path": f"/api/assets/{asset.id}/download",
            "source_url": asset.source_url,
        }
    if normalized_type == "briefing":
        briefing = db.get(EconomicBriefing, ref_id)
        if not briefing or briefing.owner_user_id != user.id or briefing.workspace_id != workspace.id:
            raise FileNotFoundError("Briefing not found.")
        return {
            "title": briefing.title,
            "summary": truncate_text(briefing.summary_markdown or "", 240),
            "metadata": {
                "source_kind": "briefing",
                "briefing_id": briefing.id,
                "headline_count": briefing.headline_count,
            },
            "detail_path": "/knowledge-base",
            "download_path": "",
            "source_url": "",
        }
    if normalized_type == "literature_entry":
        entry = db.get(LiteratureEntry, ref_id)
        if not entry or entry.owner_user_id != user.id or entry.workspace_id != workspace.id:
            raise FileNotFoundError("Literature entry not found.")
        return {
            "title": entry.title,
            "summary": truncate_text(entry.abstract or entry.venue or "", 240),
            "metadata": {
                "source_kind": "literature_entry",
                "literature_entry_id": entry.id,
                "openalex_id": entry.openalex_id,
                "doi": entry.doi,
                "publication_year": entry.publication_year,
            },
            "detail_path": "",
            "download_path": "",
            "source_url": entry.landing_page_url or entry.pdf_url or "",
        }
    raise ValueError("Unsupported case item type.")


def add_item_to_knowledge_case(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    case_id: str,
    item_type: str,
    ref_id: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[KnowledgeCaseItem, bool]:
    case = get_owned_knowledge_case(db, user=user, case_id=case_id)
    if case.workspace_id != workspace.id:
        raise FileNotFoundError("Knowledge case not found.")
    existing = db.scalar(
        select(KnowledgeCaseItem).where(
            and_(
                KnowledgeCaseItem.case_id == case.id,
                KnowledgeCaseItem.item_type == item_type.strip().lower(),
                KnowledgeCaseItem.ref_id == ref_id,
            )
        )
    )
    if existing:
        return existing, False
    resolved = _resolve_case_reference(db, user=user, workspace=workspace, item_type=item_type, ref_id=ref_id)
    payload = dict(metadata or {}) if isinstance(metadata, dict) else {}
    payload.update(resolved.get("metadata") or {})
    item = KnowledgeCaseItem(
        case_id=case.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        item_type=item_type.strip().lower(),
        ref_id=ref_id,
        title_snapshot=str(resolved.get("title") or "").strip(),
        summary_snapshot=str(resolved.get("summary") or "").strip(),
        metadata_json=payload,
    )
    db.add(item)
    case.updated_at = datetime.now(timezone.utc)
    db.flush()
    return item, True


def remove_item_from_knowledge_case(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    case_id: str,
    item_id: str,
) -> None:
    case = get_owned_knowledge_case(db, user=user, case_id=case_id)
    if case.workspace_id != workspace.id:
        raise FileNotFoundError("Knowledge case not found.")
    item = get_owned_knowledge_case_item(db, user=user, case=case, item_id=item_id)
    db.delete(item)
    case.updated_at = datetime.now(timezone.utc)
    db.flush()


def _build_case_item_payload(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    item: KnowledgeCaseItem,
) -> dict[str, Any]:
    try:
        resolved = _resolve_case_reference(db, user=user, workspace=workspace, item_type=item.item_type, ref_id=item.ref_id)
        return serialize_knowledge_case_item(
            item,
            resolved_title=str(resolved.get("title") or ""),
            resolved_summary=str(resolved.get("summary") or ""),
            resolved_detail_path=str(resolved.get("detail_path") or ""),
            resolved_download_path=str(resolved.get("download_path") or ""),
            resolved_source_url=str(resolved.get("source_url") or ""),
            resolved_exists=True,
        )
    except FileNotFoundError:
        return serialize_knowledge_case_item(item, resolved_exists=False)


def build_knowledge_case_detail(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    case_id: str,
) -> dict[str, Any]:
    case = get_owned_knowledge_case(db, user=user, case_id=case_id)
    if case.workspace_id != workspace.id:
        raise FileNotFoundError("Knowledge case not found.")
    items = list_knowledge_case_items(db, user=user, case=case)
    item_payloads = [_build_case_item_payload(db, user=user, workspace=workspace, item=item) for item in items]
    latest_item_at = items[0].created_at.isoformat() if items else ""
    item_types = sorted({payload["item_type"] for payload in item_payloads})
    return {
        "case": serialize_knowledge_case(
            case,
            item_count=len(item_payloads),
            latest_item_at=latest_item_at,
            item_types=item_types,
        ),
        "items": item_payloads,
    }

def _significance_stars(p_value: Any) -> str:
    numeric = _safe_float(p_value)
    if numeric is None:
        return ""
    if numeric < 0.01:
        return "***"
    if numeric < 0.05:
        return "**"
    if numeric < 0.1:
        return "*"
    return ""


def _format_number(value: Any, *, digits: int = 4) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.{digits}f}"


def _find_coefficient_row(rows: list[dict[str, Any]], *candidates: str) -> dict[str, Any] | None:
    if not rows:
        return None
    candidate_set = {candidate for candidate in candidates if candidate}
    for row in rows:
        if str(row.get("term", "")) in candidate_set:
            return row
    return None


def _result_table_names(result: dict[str, Any]) -> list[str]:
    tables = result.get("tables") or {}
    if isinstance(tables, dict):
        return [str(name) for name in tables.keys()]
    return []


def _result_figure_titles(result: dict[str, Any]) -> list[str]:
    figures = result.get("figures") or []
    titles: list[str] = []
    if isinstance(figures, list):
        for figure in figures:
            if isinstance(figure, dict):
                title = str(figure.get("title") or "").strip()
                if title:
                    titles.append(title)
    return titles


def _build_model_result_interpretation(result: dict[str, Any]) -> dict[str, Any]:
    model_type = str(result.get("model_type") or "").strip().lower()
    model_label = str(result.get("model_label") or model_type or "Model")
    specification = result.get("specification") or {}
    coefficients = result.get("coefficients") or []
    table_names = _result_table_names(result)
    figure_titles = _result_figure_titles(result)
    headline = f"{model_label} estimates are exposed in full so you can read the result and reproduce it manually."
    sections: list[dict[str, Any]] = []

    def add_section(title: str, items: list[str]) -> None:
        cleaned = [item for item in items if item]
        if cleaned:
            sections.append({"title": title, "items": cleaned})

    generic_outputs = []
    if coefficients:
        generic_outputs.append("Coefficient table is shown with standard errors, test statistics, p-values, and significance stars.")
    if table_names:
        generic_outputs.append(f"Supporting tables included: {', '.join(table_names)}.")
    if figure_titles:
        generic_outputs.append(f"Figures included: {', '.join(figure_titles)}.")
    add_section("What is shown on this page", generic_outputs)

    if model_type == "did":
        did_row = _find_coefficient_row(coefficients, "did_interaction")
        did_text = "The focal DID coefficient is `did_interaction`."
        if did_row:
            did_text = (
                f"The focal DID coefficient is `did_interaction` = {_format_number(did_row.get('coefficient'))}"
                f"{_significance_stars(did_row.get('p_value'))}."
            )
        add_section(
            "How to read the main result",
            [
                did_text,
                "A positive sign means the treated group rose more after treatment than the control group did over the same period.",
                "The 2x2 cell-means table should tell the same story as the regression coefficient.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "A coefficient table with treatment, post, and DID interaction terms.",
                "A 2x2 before/after by treated/control summary or plot.",
                "A discussion of parallel-trends plausibility and sample construction.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Check that treatment and post indicators are coded exactly as intended in the downloaded sample.",
                "Recompute the 2x2 cell means manually before trusting the DID coefficient.",
                "Re-estimate the regression with the documented covariance type and compare the `did_interaction` row term by term.",
            ],
        )
    elif model_type == "event_study":
        add_section(
            "How to read the main result",
            [
                "Use the dynamic-effects table and the event-study figure together: coefficients before treatment help diagnose pre-trends, while post-treatment coefficients show the effect path over time.",
                f"The omitted reference period is {specification.get('omitted_period', 'n/a')}. All dynamic coefficients are relative to that period.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "A dynamic coefficient table by relative event time.",
                "An event-study plot with confidence intervals and a clearly stated omitted period.",
                "A discussion of pre-trend behavior and event-window choice.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Verify the relative event-time variable and omitted period in the prepared sample.",
                "Check that the pre-treatment coefficients are approximately centered around zero if the identifying design relies on parallel pre-trends.",
                "Reproduce the plotted points from the dynamic-effects table horizon by horizon.",
            ],
        )
    elif model_type == "rdd":
        tau_row = _find_coefficient_row(coefficients, "rdd_treatment")
        tau_text = "The cutoff effect is carried by the `rdd_treatment` coefficient."
        if tau_row:
            tau_text = (
                f"The cutoff effect is `rdd_treatment` = {_format_number(tau_row.get('coefficient'))}"
                f"{_significance_stars(tau_row.get('p_value'))}."
            )
        add_section(
            "How to read the main result",
            [
                tau_text,
                "The fitted-line figure should show a visible jump at the cutoff if the local treatment effect is economically meaningful.",
                "Polynomial and bandwidth choices matter; always read the cutoff estimate together with the selected window.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "A local treatment-effect table around the cutoff.",
                "An RDD figure with separate fits on each side of the threshold.",
                "Bandwidth, polynomial-order, and treatment-assignment-rule disclosure.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Confirm the running variable and cutoff coding in the downloaded sample.",
                "Check whether the bandwidth filter leaves the same number of observations as reported.",
                "Rebuild the fitted lines using the same polynomial order and compare the local effect row.",
            ],
        )
    elif model_type in {"arch", "garch"}:
        add_section(
            "How to read the main result",
            [
                f"Volatility persistence is reported directly in the metrics panel and should normally be below 1. Current value: {_format_number(result.get('persistence'))}.",
                "The parameter table is the formal estimation output; the volatility-path chart shows how conditional volatility evolves through the sample.",
                "The forecast-volatility table and forecast chart extend the conditional variance path beyond the last observation.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "A parameter table with omega, alpha, and beta terms.",
                "A conditional-volatility figure over time.",
                "A short discussion of persistence and forecasted volatility.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Re-estimate the same ARCH/GARCH order on the downloaded return series.",
                "Check whether alpha plus beta matches the reported persistence.",
                "Recompute the forecast variance path and compare it step by step with the forecast table.",
            ],
        )
    elif model_type == "var":
        add_section(
            "How to read the main result",
            [
                "Read the coefficient table equation by equation because each endogenous series has its own regression block.",
                "The forecast table and figure summarize the joint path implied by the fitted system.",
                f"Use the selected lag order `{specification.get('lags', 'n/a')}` consistently when reproducing the system.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "Equation-level coefficient blocks or a compact companion-form summary.",
                "Forecast tables or dynamic plots for each series.",
                "Lag-order choice with AIC/BIC or another stated criterion.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Sort the sample by the declared time column before estimation.",
                "Re-estimate the VAR with the documented lag order and compare coefficient blocks equation by equation.",
                "Regenerate the forecast path using the final lag_order observations from the sample.",
            ],
        )
    elif model_type == "svar_irf":
        add_section(
            "How to read the main result",
            [
                f"The recursive identification is driven by the Cholesky ordering: {', '.join(specification.get('series_columns', []))}.",
                f"Shock variable: {specification.get('impulse_column', 'n/a')}. Response panels and the IRF table should match horizon by horizon.",
                "Use the cumulative IRF figure when you care about accumulated rather than one-period responses.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "An orthogonalized IRF figure.",
                "A cumulative IRF figure or cumulative response table when accumulation matters.",
                "A clear statement of ordering or other identification assumptions.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Do not change the variable ordering when reproducing the result.",
                "Rebuild the orthogonalized IRF using the same lag order and horizon.",
                "Compare the cumulative IRF figure against the cumulative response column in the IRF table.",
            ],
        )
    elif model_type == "virf":
        add_section(
            "How to read the main result",
            [
                f"The reported shock size is {specification.get('shock_size', 'n/a')} sigma.",
                "The volatility path shows the level of implied volatility after the shock, while the variance-response plot shows the raw variance adjustment.",
                "Persistence close to 1 means the shock decays slowly.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "Estimated GARCH parameters and persistence.",
                "A volatility impulse-response plot.",
                "A table listing volatility or variance responses by horizon.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Recover omega, alpha, and beta from the fitted GARCH(1,1) specification.",
                "Rebuild the VIRF path from the documented recurrence formula and shock size.",
                "Compare both the volatility and variance response outputs horizon by horizon.",
            ],
        )
    elif model_type == "dy_connectedness":
        add_section(
            "How to read the main result",
            [
                f"The total connectedness index is {_format_number(result.get('total_connectedness_index'), digits=2)} percent.",
                "The connectedness matrix shows how much of each variable's forecast error variance comes from shocks to the other variables.",
                "The directional spillover chart highlights which variables are net transmitters and receivers of shocks.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "A generalized FEVD connectedness matrix.",
                "Directional spillover measures (to, from, and net).",
                "A visual summary such as a heatmap or bar chart of net spillovers.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Rebuild the generalized FEVD with the same horizon and lag order.",
                "Check that row normalization matches the reported connectedness matrix.",
                "Recompute net spillovers from the matrix and compare them with the directional bar chart.",
            ],
        )
    elif model_type == "bk_connectedness":
        add_section(
            "How to read the main result",
            [
                "Each band isolates spillovers at a different horizon segment; compare short-, medium-, and long-run connectedness rather than collapsing everything into one number.",
                "The band-total connectedness chart summarizes how much spillover intensity sits in each frequency range.",
                "Band-specific matrices remain normalized within band, so they are for structural comparison rather than direct level comparison across bands.",
            ],
        )
        add_section(
            "What a normal paper should report",
            [
                "Band-specific connectedness matrices.",
                "A summary table of total connectedness by frequency band.",
                "A figure showing how connectedness is distributed across short, medium, and long horizons.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Rebuild the VAR with the same lag order before moving to the frequency decomposition.",
                "Use the documented short and medium horizon cutoffs exactly when reconstructing the bands.",
                "Check each band's total connectedness against the band summary chart and table.",
            ],
        )
    else:
        add_section(
            "How to read the main result",
            [
                "Use the metrics panel for headline diagnostics, then move to the coefficient table or supporting tables for the formal result.",
                "The specification block records the exact equation or parameterization that should be reproduced manually.",
            ],
        )
        add_section(
            "Manual replication focus",
            [
                "Download the referenced sample and rebuild all listed derived columns before estimation.",
                "Match the equation, regressors, covariance type, and sample filters exactly.",
                "Compare the resulting table or figure object term by term with the result shown here.",
            ],
        )
    return {
        "headline": headline,
        "sections": sections,
        "paper_outputs": table_names + figure_titles,
    }


def _build_processing_result_interpretation(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") or {}
    workflow_group = str(result.get("processing_family") or "data_processing")
    derived_columns = summary.get("derived_columns") or []
    operations = result.get("audit_trail", {}).get("operations") or {}
    transformed = operations.get("transformed_columns") if isinstance(operations, dict) else None
    sections = [
        {
            "title": "What this processing run produced",
            "items": [
                f"Prepared rows: {summary.get('rows_after_prepare', 'n/a')}.",
                f"Missing-value drops: {summary.get('rows_removed_for_missing_required', 'n/a')}.",
                f"Derived columns created: {', '.join(derived_columns) if derived_columns else 'none'}.",
            ],
        },
        {
            "title": "What a normal appendix should show",
            "items": [
                "A concise data-preparation log that lists the exact transformations applied in order.",
                "A preview or schema of the final prepared sample.",
                "A downloadable prepared dataset used for estimation.",
            ],
        },
        {
            "title": "Manual replication focus",
            "items": [
                "Reapply imputation, winsorization, transforms, feature construction, and filtering in the documented order.",
                "Verify row and column counts against the saved preparation summary.",
                f"Check transformation groups explicitly: {json.dumps(transformed, ensure_ascii=False) if transformed else 'no grouped transforms documented'}.",
            ],
        },
    ]
    return {
        "headline": f"{workflow_group.replace('_', ' ').title()} created a reproducible prepared sample with full audit metadata.",
        "sections": sections,
        "paper_outputs": ["Preparation summary", "Prepared sample preview", "Downloadable prepared dataset"],
    }


def search_knowledge_records(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    query: str,
    include_archived: bool = False,
) -> list[KnowledgeRecord]:
    search_value = f"%{query.strip()}%"
    rows = list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                    or_(
                        KnowledgeRecord.title.ilike(search_value),
                        KnowledgeRecord.content.ilike(search_value),
                    ),
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc())
        )
    )
    if include_archived:
        return rows
    return [row for row in rows if not is_knowledge_record_archived(row)]


def update_knowledge_record(
    db: Session,
    *,
    user: User,
    record_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> KnowledgeRecord:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    if title is not None:
        normalized_title = title.strip()
        if len(normalized_title) < 2:
            raise ValueError("Title must be at least 2 characters.")
        record.title = normalized_title
    if content is not None:
        normalized_content = _normalize_note_content(content)
        record.content = normalized_content
    if tags is not None:
        record.tags_json = list(dict.fromkeys(tag.strip() for tag in tags if tag and tag.strip()))
    if metadata is not None:
        merged_metadata = {
            **(record.metadata_json if isinstance(record.metadata_json, dict) else {}),
            **(metadata if isinstance(metadata, dict) else {}),
        }
        record.metadata_json = merged_metadata
    db.flush()
    return record


def archive_knowledge_record(
    db: Session,
    *,
    user: User,
    record_id: str,
    reason: str = "",
) -> KnowledgeRecord:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    archived_at = datetime.now(timezone.utc).isoformat()
    metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    metadata["is_archived"] = True
    metadata["archived_at"] = archived_at
    metadata["archived_reason"] = reason.strip()
    metadata["archive"] = {
        "is_archived": True,
        "at": archived_at,
        "reason": reason.strip(),
    }
    record.metadata_json = metadata
    db.flush()
    return record


def restore_knowledge_record(
    db: Session,
    *,
    user: User,
    record_id: str,
) -> KnowledgeRecord:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    metadata.pop("is_archived", None)
    metadata.pop("archived_at", None)
    metadata.pop("archived_reason", None)
    metadata.pop("archive", None)
    record.metadata_json = metadata
    db.flush()
    return record


def delete_knowledge_record(
    db: Session,
    *,
    user: User,
    record_id: str,
) -> KnowledgeRecord:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    db.delete(record)
    db.flush()
    return record


def find_related_knowledge_records(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    record_id: str,
    limit: int = 5,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    base_record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    if base_record.workspace_id != workspace.id:
        raise FileNotFoundError("Knowledge record not found.")
    base_tags = {str(tag).strip().lower() for tag in (base_record.tags_json or []) if str(tag).strip()}
    base_metadata = base_record.metadata_json if isinstance(base_record.metadata_json, dict) else {}
    candidates = [
        row
        for row in list_knowledge_records(db, user=user, workspace=workspace, include_archived=include_archived)
        if row.id != base_record.id
    ]
    ranked: list[tuple[int, str, KnowledgeRecord, list[str]]] = []
    for candidate in candidates:
        candidate_tags = {str(tag).strip().lower() for tag in (candidate.tags_json or []) if str(tag).strip()}
        candidate_metadata = candidate.metadata_json if isinstance(candidate.metadata_json, dict) else {}
        reasons: list[str] = []
        score = 0

        shared_tags = sorted(base_tags & candidate_tags)
        if shared_tags:
            score += len(shared_tags) * 4
            reasons.append(f"Shared tags: {', '.join(shared_tags[:4])}")

        shared_keys = [
            ("source_type", 3, "Shared note source"),
            ("note_template", 3, "Shared note template"),
            ("derivative_mode", 3, "Shared derivative note type"),
            ("briefing_id", 6, "Derived from the same private briefing"),
            ("openalex_id", 6, "Derived from the same paper"),
            ("model_type", 5, "Same model family output"),
            ("model_family", 4, "Shared model family"),
        ]
        for key, weight, label in shared_keys:
            base_value = str(base_metadata.get(key) or "").strip()
            candidate_value = str(candidate_metadata.get(key) or "").strip()
            if base_value and base_value == candidate_value:
                score += weight
                reasons.append(label)

        if not score:
            continue
        ranked.append(
            (
                score,
                candidate.updated_at.isoformat() if candidate.updated_at else candidate.created_at.isoformat(),
                candidate,
                reasons,
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        {
            **serialize_knowledge_record(candidate, include_content=False),
            "relation_score": score,
            "relation_reasons": reasons,
        }
        for score, _, candidate, reasons in ranked[: max(1, limit)]
    ]


def create_workspace_digest_record(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    max_memories: int = 4,
    max_notes: int = 6,
    max_briefings: int = 3,
    max_papers: int = 3,
    max_assets: int = 3,
) -> KnowledgeRecord:
    memories = list_workspace_memories(db, user=user, workspace=workspace, limit=max_memories)
    note_rows = [
        row
        for row in list_knowledge_records(db, user=user, workspace=workspace, include_archived=False)
        if str((row.metadata_json or {}).get("source_type") or "").strip() != "workspace_digest"
    ][: max_notes]
    briefings = list(
        db.scalars(
            select(EconomicBriefing)
            .where(
                and_(
                    EconomicBriefing.owner_user_id == user.id,
                    EconomicBriefing.workspace_id == workspace.id,
                )
            )
            .order_by(EconomicBriefing.created_at.desc())
            .limit(max_briefings)
        )
    )
    literature = list(
        db.scalars(
            select(LiteratureEntry)
            .where(
                and_(
                    LiteratureEntry.owner_user_id == user.id,
                    LiteratureEntry.workspace_id == workspace.id,
                )
            )
            .order_by(LiteratureEntry.updated_at.desc())
            .limit(max_papers)
        )
    )
    assets = list(
        db.scalars(
            select(DataAsset)
            .where(
                and_(
                    DataAsset.owner_user_id == user.id,
                    DataAsset.workspace_id == workspace.id,
                )
            )
            .order_by(DataAsset.updated_at.desc())
            .limit(max_assets)
        )
    )

    top_tags_counter: dict[str, int] = {}
    for note in note_rows:
        for tag in note.tags_json or []:
            normalized = str(tag).strip()
            if not normalized:
                continue
            top_tags_counter[normalized] = top_tags_counter.get(normalized, 0) + 1
    top_tags = [item for item, _ in sorted(top_tags_counter.items(), key=lambda pair: (-pair[1], pair[0]))[:6]]

    lines = [
        f"# Workspace Digest: {workspace.name}",
        "",
        "## Snapshot",
        "",
        f"- Memories included: {len(memories)}",
        f"- Notes included: {len(note_rows)}",
        f"- Briefings included: {len(briefings)}",
        f"- Papers included: {len(literature)}",
        f"- Assets included: {len(assets)}",
        f"- Top tags: {', '.join(top_tags) if top_tags else 'none'}",
        "",
        "## Workspace memories",
        "",
    ]
    if memories:
        for memory in memories:
            lines.extend(
                [
                    f"### {memory.title}",
                    f"- Updated: {memory.updated_at.isoformat()}",
                    f"- Excerpt: {truncate_text(memory.content or '', 220) or 'n/a'}",
                    "",
                ]
            )
    else:
        lines.extend(["- No workspace memories saved yet.", ""])

    lines.extend(
        [
        "## Recent notes",
        "",
        ]
    )
    if note_rows:
        for note in note_rows:
            excerpt = truncate_text(note.content or "", 220)
            lines.extend(
                [
                    f"### {note.title}",
                    f"- Tags: {', '.join(note.tags_json or []) or 'none'}",
                    f"- Updated: {note.updated_at.isoformat()}",
                    f"- Excerpt: {excerpt or 'n/a'}",
                    "",
                ]
            )
    else:
        lines.extend(["- No active notes available.", ""])

    lines.extend(["## Latest briefings", ""])
    if briefings:
        for briefing in briefings:
            lines.extend(
                [
                    f"- {briefing.title} | headlines: {briefing.headline_count} | created: {briefing.created_at.isoformat()}",
                ]
            )
    else:
        lines.append("- No private briefings yet.")
    lines.append("")

    lines.extend(["## Latest papers", ""])
    if literature:
        for item in literature:
            lines.append(f"- {item.title} | {item.publication_year or 'n/a'} | {item.venue or 'Unknown venue'}")
    else:
        lines.append("- No imported papers yet.")
    lines.append("")

    lines.extend(["## Latest assets", ""])
    if assets:
        for asset in assets:
            lines.append(f"- {asset.title} | {asset.kind} | updated: {asset.updated_at.isoformat()}")
    else:
        lines.append("- No assets yet.")
    lines.extend(
        [
            "",
            "## Next manual review checks",
            "",
            "- Confirm that the newest note, briefing, and paper agree on the current research focus.",
            "- Archive obsolete notes after synthesizing them into a digest or memo.",
            "- Use the Research Flow Lane on the homepage to continue from the latest private output.",
        ]
    )

    title = f"Workspace Digest: {workspace.name} ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})"
    return create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=title,
        content="\n".join(lines),
        tags=["workspace-digest", "cockpit", "knowledge-base", *top_tags[:3]],
        metadata={
            "source_type": "workspace_digest",
            "workspace_id": workspace.id,
            "included_memory_count": len(memories),
            "included_note_count": len(note_rows),
            "included_briefing_count": len(briefings),
            "included_paper_count": len(literature),
            "included_asset_count": len(assets),
            "top_tags": top_tags,
        },
    )


def build_model_result_detail(db: Session, *, user: User, record_id: str) -> dict[str, Any]:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    metadata = dict(record.metadata_json or {})
    if not metadata.get("model_type"):
        raise ValueError("This knowledge record is not a model result.")
    metadata.setdefault("workflow_type", "model")
    metadata.setdefault("model_family", _infer_model_family(str(metadata.get("model_type", ""))))
    metadata.setdefault("result_record_id", record.id)
    metadata.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
    metadata["detail_path"] = metadata["result_detail_path"]
    metadata["status"] = "ready"
    metadata["reason"] = "Model result is ready for review."
    metadata["next_action"] = "open_detail"
    metadata["template_source"] = _template_source_value(metadata)
    metadata["variant_source"] = _variant_source_value(metadata)
    metadata["interpretation"] = _build_model_result_interpretation(metadata)
    return {
        "record": serialize_knowledge_record(record),
        "result": metadata,
        "workspace_id": record.workspace_id,
    }


def classify_asset_kind(filename: str, content_type: str) -> str:
    lowered_name = filename.lower()
    lowered_type = (content_type or "").lower()
    if lowered_name.endswith(".csv") or lowered_type in {"text/csv", "application/csv"}:
        return "dataset_csv"
    if lowered_name.endswith(".xlsx") or lowered_name.endswith(".xls") or lowered_type in {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    } or (
        lowered_type == "application/octet-stream"
        and (lowered_name.endswith(".xls") or lowered_name.endswith(".xlsx"))
    ):
        return "dataset_excel"
    if lowered_name.endswith(".json") or lowered_type in {"application/json", "text/json"}:
        return "dataset_json"
    if lowered_name.endswith(".pdf") or lowered_type == "application/pdf":
        return "document_pdf"
    if lowered_name.endswith(".md") or lowered_type == "text/markdown":
        return "note_markdown"
    if lowered_name.endswith(".txt") or lowered_type == "text/plain":
        return "note_text"
    if lowered_name.endswith(".png") or lowered_type == "image/png":
        return "chart_png"
    if lowered_name.endswith(".jpg") or lowered_name.endswith(".jpeg") or lowered_type == "image/jpeg":
        return "image_jpeg"
    if lowered_name.endswith(".svg") or lowered_type == "image/svg+xml":
        return "image_svg"
    return "binary_file"


def sniff_asset_kind(content: bytes, *, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    prefix = content[:512]
    stripped = content.lstrip()
    if extension in {".xls", ".xlsx"} and prefix[:2] == b"PK":
        return "dataset_excel"
    if extension == ".xls" and prefix.startswith(b"\xd0\xcf\x11\xe0"):
        return "dataset_excel"
    if prefix.startswith(b"%PDF-"):
        return "document_pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "chart_png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image_jpeg"
    if extension == ".svg":
        sample = _decode_text_sample(stripped[:4096])
        lowered = sample.lstrip().lower()
        if "<html" in lowered or "<script" in lowered:
            return "binary_file"
        if lowered.startswith("<?xml"):
            svg_index = lowered.find("<svg")
            if svg_index == -1:
                return "binary_file"
            lowered = lowered[svg_index:]
        if lowered.startswith("<svg"):
            return "image_svg"
        return "binary_file"
    if extension == ".json":
        try:
            json.loads(_decode_text_sample(stripped))
        except Exception:
            return "binary_file"
        else:
            return "dataset_json"
    if extension == ".csv":
        sample = _decode_text_sample(content[:4096])
        if _looks_like_csv_text(sample):
            return "dataset_csv"
        return "binary_file"
    sample = _decode_text_sample(prefix)
    if extension in {".md", ".txt"}:
        if _looks_like_html_text(sample):
            return "binary_file"
        return "note_markdown" if extension == ".md" else "note_text"
    return classify_asset_kind(filename, "")


def _safe_asset_storage_name(filename: str, *, asset_kind: str, asset_id: str) -> str:
    extension = Path(filename).suffix.lower()
    allowed_extensions = _KIND_EXTENSIONS.get(asset_kind, set())
    if extension not in allowed_extensions:
        extension = sorted(allowed_extensions)[0] if allowed_extensions else ""
    return f"{asset_id}{extension}"


def extract_text_from_bytes(content: bytes, *, filename: str, content_type: str) -> str:
    kind = classify_asset_kind(filename, content_type)
    if kind == "document_pdf":
        document = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in document[: min(8, len(document))])
        return truncate_text(text, 20000)
    if kind in {"dataset_csv", "dataset_json", "note_markdown", "note_text"}:
        return truncate_text(content.decode("utf-8", errors="ignore"), 20000)
    return ""


def save_upload_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    filename: str,
    content: bytes,
    content_type: str,
    description: str = "",
    source_url: str = "",
) -> DataAsset:
    declared_kind = classify_asset_kind(filename, content_type)
    sniffed_kind = sniff_asset_kind(content, filename=filename)
    asset_kind = declared_kind if declared_kind == sniffed_kind else "binary_file"
    if asset_kind not in ALLOWED_UPLOAD_KINDS:
        raise ValueError("Unsupported upload type. Allowed types: csv, xlsx, xls, json, pdf, txt, md, png, jpg, jpeg, and svg.")
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type and normalized_content_type not in _KIND_CONTENT_TYPES.get(asset_kind, set()):
        raise ValueError("Upload content type does not match the selected file type.")
    normalized_source_url = validate_optional_source_url(source_url, field_name="Source URL")
    asset = DataAsset(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        kind=asset_kind,
        title=Path(filename).name,
        description=description.strip(),
        content_type=normalized_content_type,
        source_url=normalized_source_url,
        extracted_text=extract_text_from_bytes(content, filename=filename, content_type=content_type),
        metadata_json={"size_bytes": len(content), "original_filename": Path(filename).name},
    )
    db.add(asset)
    db.flush()

    safe_storage_name = _safe_asset_storage_name(filename, asset_kind=asset_kind, asset_id=asset.id)

    stored = store_asset_content(
        settings,
        user_id=user.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        filename=safe_storage_name,
        content=content,
        content_type=normalized_content_type,
    )
    asset.file_path = stored.reference
    asset.metadata_json = {
        **asset.metadata_json,
        **stored.metadata,
    }
    db.flush()
    return asset


def list_assets(db: Session, *, user: User, workspace: Workspace) -> list[DataAsset]:
    return list(
        db.scalars(
            select(DataAsset)
            .where(
                and_(
                    DataAsset.owner_user_id == user.id,
                    DataAsset.workspace_id == workspace.id,
                )
            )
            .order_by(DataAsset.updated_at.desc())
        )
    )


def search_assets(db: Session, *, user: User, workspace: Workspace, query: str) -> list[DataAsset]:
    search_value = f"%{query.strip()}%"
    return list(
        db.scalars(
            select(DataAsset)
            .where(
                and_(
                    DataAsset.owner_user_id == user.id,
                    DataAsset.workspace_id == workspace.id,
                    or_(
                        DataAsset.title.ilike(search_value),
                        DataAsset.description.ilike(search_value),
                        DataAsset.extracted_text.ilike(search_value),
                    ),
                )
            )
            .order_by(DataAsset.updated_at.desc())
        )
    )


def load_dataset_frame(settings: Settings, asset: DataAsset) -> pd.DataFrame:
    raw_bytes = load_asset_bytes(settings, asset.file_path)
    if asset.kind == "dataset_csv":
        return pd.read_csv(BytesIO(raw_bytes))
    if asset.kind == "dataset_excel":
        return pd.read_excel(BytesIO(raw_bytes))
    if asset.kind == "dataset_json":
        raw = json.loads(raw_bytes.decode("utf-8"))
        return pd.DataFrame(raw)
    raise ValueError("This asset is not a structured dataset.")


def _analysis_asset_or_raise(db: Session, *, user: User, workspace: Workspace, asset_id: str) -> DataAsset:
    asset = db.get(DataAsset, asset_id)
    if not asset or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
        raise FileNotFoundError("Dataset asset not found.")
    if asset.kind not in DATASET_KINDS:
        raise ValueError("This asset is not a structured dataset.")
    return asset


def _load_analysis_frame(
    settings: Settings,
    asset: DataAsset,
    *,
    drop_duplicates: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw_frame = load_dataset_frame(settings, asset)
    return normalize_dataset_frame(raw_frame, drop_duplicates=drop_duplicates)


def _coerce_binary_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum():
        return numeric.apply(lambda value: np.nan if pd.isna(value) else (1.0 if float(value) > 0 else 0.0))

    mapping = {
        "true": 1.0,
        "yes": 1.0,
        "y": 1.0,
        "1": 1.0,
        "treated": 1.0,
        "post": 1.0,
        "false": 0.0,
        "no": 0.0,
        "n": 0.0,
        "0": 0.0,
        "control": 0.0,
        "pre": 0.0,
    }
    return series.astype(str).str.strip().str.lower().map(mapping)


def _coerce_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _coerce_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _winsorize_series(series: pd.Series, lower_quantile: float, upper_quantile: float) -> pd.Series:
    clean = series.dropna()
    if clean.empty:
        return series
    lower = clean.quantile(lower_quantile)
    upper = clean.quantile(upper_quantile)
    return series.clip(lower=lower, upper=upper)


def _impute_series(series: pd.Series, method: str) -> pd.Series:
    normalized_method = (method or "none").strip().lower()
    if normalized_method in {"", "none"}:
        return series
    if normalized_method == "mean":
        return series.fillna(series.mean())
    if normalized_method == "median":
        return series.fillna(series.median())
    if normalized_method == "zero":
        return series.fillna(0)
    if normalized_method == "ffill":
        return series.ffill()
    if normalized_method == "bfill":
        return series.bfill()
    raise ValueError(f"Unsupported imputation method: {method}")


def _drop_outliers(
    sample: pd.DataFrame,
    columns: list[str],
    *,
    method: str,
    threshold: float,
) -> tuple[pd.DataFrame, int]:
    normalized_method = (method or "none").strip().lower()
    if normalized_method in {"", "none"} or not columns:
        return sample, 0

    mask = pd.Series(True, index=sample.index)
    if normalized_method == "iqr":
        for column in columns:
            clean = sample[column].dropna()
            if clean.empty:
                continue
            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1
            if pd.isna(iqr) or iqr == 0:
                continue
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            mask &= sample[column].isna() | sample[column].between(lower, upper)
    elif normalized_method == "zscore":
        for column in columns:
            clean = sample[column].dropna()
            if clean.empty:
                continue
            std = clean.std()
            if pd.isna(std) or std == 0:
                continue
            z_score = (sample[column] - clean.mean()) / std
            mask &= sample[column].isna() | (z_score.abs() <= threshold)
    else:
        raise ValueError(f"Unsupported outlier method: {method}")

    removed = int((~mask).sum())
    return sample.loc[mask].copy(), removed


def _prepare_selected_sample(
    frame: pd.DataFrame,
    *,
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    impute_columns: list[str] | None = None,
    impute_method: str = "none",
    winsorize_columns: list[str] | None = None,
    winsor_lower_quantile: float = 0.01,
    winsor_upper_quantile: float = 0.99,
    log_transform_columns: list[str] | None = None,
    standardize_columns: list[str] | None = None,
    minmax_scale_columns: list[str] | None = None,
    outlier_columns: list[str] | None = None,
    outlier_method: str = "none",
    outlier_threshold: float = 1.5,
    sort_column: str = "",
    time_group_column: str = "",
    difference_columns: list[str] | None = None,
    return_columns: list[str] | None = None,
    return_method: str = "simple",
    lag_columns: list[str] | None = None,
    lag_periods: int = 1,
    lead_columns: list[str] | None = None,
    lead_periods: int = 1,
    rolling_mean_columns: list[str] | None = None,
    rolling_volatility_columns: list[str] | None = None,
    rolling_window: int = 5,
    drop_duplicates: bool = True,
    drop_missing_required: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sample = frame.copy()
    duplicate_count = int(sample.duplicated().sum()) if drop_duplicates else 0
    if drop_duplicates:
        sample = sample.drop_duplicates().copy()

    include_columns = [column for column in (include_columns or []) if column]
    required_columns = [column for column in (required_columns or []) if column]
    numeric_columns = [column for column in (numeric_columns or []) if column]
    binary_columns = [column for column in (binary_columns or []) if column]
    date_columns = [column for column in (date_columns or []) if column]
    impute_columns = [column for column in (impute_columns or []) if column]
    winsorize_columns = [column for column in (winsorize_columns or []) if column]
    log_transform_columns = [column for column in (log_transform_columns or []) if column]
    standardize_columns = [column for column in (standardize_columns or []) if column]
    minmax_scale_columns = [column for column in (minmax_scale_columns or []) if column]
    outlier_columns = [column for column in (outlier_columns or []) if column]
    difference_columns = [column for column in (difference_columns or []) if column]
    return_columns = [column for column in (return_columns or []) if column]
    lag_columns = [column for column in (lag_columns or []) if column]
    lead_columns = [column for column in (lead_columns or []) if column]
    rolling_mean_columns = [column for column in (rolling_mean_columns or []) if column]
    rolling_volatility_columns = [column for column in (rolling_volatility_columns or []) if column]

    requested_columns = {
        *(include_columns or []),
        *required_columns,
        *numeric_columns,
        *binary_columns,
        *date_columns,
        *impute_columns,
        *winsorize_columns,
        *log_transform_columns,
        *standardize_columns,
        *minmax_scale_columns,
        *outlier_columns,
        *difference_columns,
        *return_columns,
        *lag_columns,
        *lead_columns,
        *rolling_mean_columns,
        *rolling_volatility_columns,
    }
    if sort_column:
        requested_columns.add(sort_column)
    if time_group_column:
        requested_columns.add(time_group_column)
    missing_columns = [column for column in requested_columns if column not in sample.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    if include_columns:
        if sort_column and sort_column not in include_columns:
            include_columns.append(sort_column)
        if time_group_column and time_group_column not in include_columns:
            include_columns.append(time_group_column)
        sample = sample[include_columns].copy()

    numeric_pipeline_columns = {
        *numeric_columns,
        *winsorize_columns,
        *log_transform_columns,
        *standardize_columns,
        *minmax_scale_columns,
        *outlier_columns,
        *difference_columns,
        *return_columns,
        *lag_columns,
        *lead_columns,
        *rolling_mean_columns,
        *rolling_volatility_columns,
    }
    if impute_method.strip().lower() in {"mean", "median", "zero"}:
        numeric_pipeline_columns.update(impute_columns)

    for column in numeric_pipeline_columns:
        if column in sample.columns:
            sample[column] = _coerce_numeric_series(sample[column])
    for column in binary_columns:
        if column in sample.columns:
            sample[column] = _coerce_binary_series(sample[column])
    for column in date_columns:
        if column in sample.columns:
            sample[column] = _coerce_date_series(sample[column])

    imputation_log: dict[str, str] = {}
    if impute_method.strip().lower() not in {"", "none"}:
        for column in impute_columns:
            if is_numeric_dtype(sample[column]) or impute_method.strip().lower() in {"ffill", "bfill"}:
                sample[column] = _impute_series(sample[column], impute_method)
                imputation_log[column] = impute_method.strip().lower()
            else:
                raise ValueError(f"Imputation method '{impute_method}' requires numeric columns for {column}.")

    winsorization_log: dict[str, dict[str, float]] = {}
    if winsorize_columns:
        if not (0 <= winsor_lower_quantile < winsor_upper_quantile <= 1):
            raise ValueError("Winsorization quantiles must satisfy 0 <= lower < upper <= 1.")
        for column in winsorize_columns:
            sample[column] = _winsorize_series(sample[column], winsor_lower_quantile, winsor_upper_quantile)
            winsorization_log[column] = {"lower": winsor_lower_quantile, "upper": winsor_upper_quantile}

    transformed_columns: dict[str, list[str]] = {"log": [], "zscore": [], "minmax": []}
    for column in log_transform_columns:
        if (sample[column].dropna() <= 0).any():
            raise ValueError(f"Log transform requires strictly positive values in column: {column}")
        sample[column] = np.log(sample[column])
        transformed_columns["log"].append(column)

    for column in standardize_columns:
        clean = sample[column].dropna()
        std = clean.std()
        if clean.empty or pd.isna(std) or std == 0:
            continue
        sample[column] = (sample[column] - clean.mean()) / std
        transformed_columns["zscore"].append(column)

    for column in minmax_scale_columns:
        clean = sample[column].dropna()
        if clean.empty:
            continue
        col_min = clean.min()
        col_max = clean.max()
        if pd.isna(col_min) or pd.isna(col_max) or col_max == col_min:
            continue
        sample[column] = (sample[column] - col_min) / (col_max - col_min)
        transformed_columns["minmax"].append(column)

    timeseries_requested = bool(
        difference_columns
        or return_columns
        or lag_columns
        or lead_columns
        or rolling_mean_columns
        or rolling_volatility_columns
    )
    if timeseries_requested and not sort_column:
        raise ValueError("Time-series preparation requires a sort column.")
    if lag_periods < 1 or lead_periods < 1:
        raise ValueError("Lag and lead periods must be at least 1.")
    if rolling_window < 2 and (rolling_mean_columns or rolling_volatility_columns):
        raise ValueError("Rolling window must be at least 2.")

    time_series_log: dict[str, Any] = {
        "sort_column": sort_column,
        "group_column": time_group_column,
        "difference_columns": [],
        "return_columns": [],
        "lag_columns": [],
        "lead_columns": [],
        "rolling_mean_columns": [],
        "rolling_volatility_columns": [],
    }
    derived_columns: list[str] = []
    if timeseries_requested:
        sort_keys = [column for column in [time_group_column, sort_column] if column]
        sample = sample.sort_values(sort_keys).copy()
        grouped = sample.groupby(time_group_column, dropna=False) if time_group_column else None

        def grouped_series(column: str):
            return grouped[column] if grouped is not None else sample[column]

        for column in difference_columns:
            derived_name = f"diff_{column}"
            sample[derived_name] = grouped_series(column).diff() if grouped is not None else sample[column].diff()
            time_series_log["difference_columns"].append(derived_name)
            derived_columns.append(derived_name)

        normalized_return_method = (return_method or "simple").strip().lower()
        for column in return_columns:
            shifted = grouped_series(column).shift(1) if grouped is not None else sample[column].shift(1)
            if normalized_return_method == "log":
                if (sample[column].dropna() <= 0).any():
                    raise ValueError(f"Log returns require strictly positive values in column: {column}")
                if (shifted.dropna() <= 0).any():
                    raise ValueError(f"Log returns require strictly positive lagged values in column: {column}")
                series = np.log(sample[column] / shifted)
            else:
                series = (sample[column] / shifted) - 1.0
            derived_name = f"{'logret' if normalized_return_method == 'log' else 'ret'}_{column}"
            sample[derived_name] = series
            time_series_log["return_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in lag_columns:
            derived_name = f"lag{int(lag_periods)}_{column}"
            sample[derived_name] = grouped_series(column).shift(int(lag_periods)) if grouped is not None else sample[column].shift(int(lag_periods))
            time_series_log["lag_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in lead_columns:
            derived_name = f"lead{int(lead_periods)}_{column}"
            sample[derived_name] = grouped_series(column).shift(-int(lead_periods)) if grouped is not None else sample[column].shift(-int(lead_periods))
            time_series_log["lead_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in rolling_mean_columns:
            derived_name = f"rollmean{int(rolling_window)}_{column}"
            if grouped is not None:
                sample[derived_name] = grouped[column].transform(lambda values: values.rolling(int(rolling_window)).mean())
            else:
                sample[derived_name] = sample[column].rolling(int(rolling_window)).mean()
            time_series_log["rolling_mean_columns"].append(derived_name)
            derived_columns.append(derived_name)

        for column in rolling_volatility_columns:
            derived_name = f"rollvol{int(rolling_window)}_{column}"
            if grouped is not None:
                sample[derived_name] = grouped[column].transform(lambda values: values.rolling(int(rolling_window)).std())
            else:
                sample[derived_name] = sample[column].rolling(int(rolling_window)).std()
            time_series_log["rolling_volatility_columns"].append(derived_name)
            derived_columns.append(derived_name)

    sample, outliers_removed = _drop_outliers(
        sample,
        outlier_columns,
        method=outlier_method,
        threshold=outlier_threshold,
    )

    rows_before_missing_drop = int(len(sample))
    if drop_missing_required and required_columns:
        sample = sample.dropna(subset=required_columns).copy()
    rows_after_missing_drop = int(len(sample))

    csv_ready = sample.copy()
    for column in csv_ready.columns:
        if is_datetime64_any_dtype(csv_ready[column]):
            csv_ready[column] = csv_ready[column].dt.strftime("%Y-%m-%dT%H:%M:%S")

    summary = {
        "rows_initial": int(len(frame)),
        "rows_after_prepare": int(len(sample)),
        "rows_removed_for_missing_required": int(rows_before_missing_drop - rows_after_missing_drop),
        "duplicate_rows_removed": duplicate_count,
        "columns": list(sample.columns),
        "required_columns": required_columns,
        "numeric_columns": numeric_columns,
        "binary_columns": binary_columns,
        "date_columns": date_columns,
        "imputed_columns": imputation_log,
        "winsorized_columns": winsorization_log,
        "transformed_columns": transformed_columns,
        "time_series_features": time_series_log,
        "derived_columns": derived_columns,
        "outlier_columns": outlier_columns,
        "outlier_method": outlier_method,
        "outlier_threshold": outlier_threshold,
        "outliers_removed": outliers_removed,
        "missing_by_column": {column: int(value) for column, value in sample.isna().sum().to_dict().items()},
    }
    return csv_ready, summary


def profile_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, meta = _load_analysis_frame(settings, asset, drop_duplicates=False)
    column_profiles = [_column_profile(frame, meta["source_columns"], column) for column in frame.columns]
    role_map: dict[str, list[str]] = {
        "numeric": [],
        "binary": [],
        "date": [],
        "categorical": [],
        "text": [],
        "empty": [],
    }
    for item in column_profiles:
        role_map.setdefault(item["role"], []).append(item["name"])

    suggested_models = ["ols"]
    if role_map["binary"] and role_map["numeric"]:
        suggested_models.extend(["logit", "probit"])
    if role_map["numeric"]:
        suggested_models.extend(["ppml", "rdd", "historical_var", "parametric_var", "ewma_volatility", "capm", "mean_variance", "minimum_variance", "risk_parity"])
    if role_map["numeric"] and len(role_map["binary"]) >= 2:
        suggested_models.extend(["did", "event_study"])
    if len(role_map["numeric"]) >= 3 and (role_map["categorical"] or role_map["text"] or role_map["date"]):
        suggested_models.extend(["fixed_effects", "arima", "var", "taylor_rule"])
    if len(role_map["numeric"]) >= 4:
        suggested_models.extend(["gravity", "iv_2sls", "panel_iv", "fama_french_3", "black_scholes", "binomial_option", "altman_z", "dupont"])
    suggested_models.append("rbc_dsge")
    suggested_models = list(dict.fromkeys(suggested_models))

    return {
        "asset": serialize_asset(asset),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows_detected": int(meta["duplicate_rows_detected"]),
        "column_profiles": column_profiles,
        "column_roles": role_map,
        "preview_rows": _frame_preview_rows(frame),
        "suggested_models": suggested_models,
        "source_columns": meta["source_columns"],
    }


def _analysis_text_tokens(text: str) -> list[str]:
    normalized = (text or "").replace("_", " ").replace("-", " ").lower()
    return [token for token in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", normalized) if token]


def _column_text_for_matching(column: dict[str, Any]) -> str:
    return f"{column.get('name', '')} {column.get('source_name', '')}".strip().lower()


def _column_token_set(column: dict[str, Any]) -> set[str]:
    return set(_analysis_text_tokens(_column_text_for_matching(column)))


def _column_exact_mention(prompt_lower: str, column: dict[str, Any]) -> bool:
    names = {str(column.get("name", "")).strip().lower(), str(column.get("source_name", "")).strip().lower()}
    return any(name and name in prompt_lower for name in names)


def _rank_variable_candidates(
    column_profiles: list[dict[str, Any]],
    *,
    prompt_text: str,
    role_name: str,
    expected_roles: set[str],
    role_keywords: set[str],
) -> list[dict[str, Any]]:
    prompt_lower = prompt_text.lower()
    prompt_tokens = set(_analysis_text_tokens(prompt_text))
    prompt_keyword_tokens: set[str] = set()
    for keyword in role_keywords:
        if keyword in prompt_lower:
            prompt_keyword_tokens.update(_analysis_text_tokens(keyword))

    ranked: list[dict[str, Any]] = []
    for column in column_profiles:
        column_tokens = _column_token_set(column)
        score = 0
        reasons: list[str] = []

        if expected_roles and column.get("role") in expected_roles:
            score += 4
            reasons.append(f"column role `{column.get('role')}` matches the expected {role_name} type")
        if role_name == "entity" and column.get("role") in {"categorical", "text"}:
            score += 2
            reasons.append("entity variables are often categorical or text-like identifiers")
        if role_name == "time" and column.get("role") == "date":
            score += 3
            reasons.append("time variables usually appear as parsed dates")
        if role_name == "post" and column.get("role") == "binary":
            score += 2
            reasons.append("post indicators are usually binary")
        if role_name == "treatment" and column.get("role") == "binary":
            score += 2
            reasons.append("treatment indicators are usually binary")

        if _column_exact_mention(prompt_lower, column):
            score += 8
            reasons.append("the column name is explicitly mentioned in the prompt")

        shared_prompt_tokens = sorted(prompt_tokens.intersection(column_tokens))
        if shared_prompt_tokens:
            score += min(3, len(shared_prompt_tokens)) * 2
            reasons.append(f"shares prompt terms: {', '.join(shared_prompt_tokens[:3])}")

        shared_role_tokens = sorted(prompt_keyword_tokens.intersection(column_tokens))
        if shared_role_tokens:
            score += min(3, len(shared_role_tokens)) * 3
            reasons.append(f"matches {role_name} keywords: {', '.join(shared_role_tokens[:3])}")

        if not score and expected_roles and column.get("role") in expected_roles:
            score = 1
            reasons.append("fallback candidate because the column role matches the expected type")

        if score <= 0:
            continue

        ranked.append(
            {
                "column": column.get("name"),
                "source_name": column.get("source_name"),
                "role": column.get("role"),
                "score": int(score),
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: (-int(item["score"]), str(item["column"])))
    return ranked


def _top_candidate(
    rankings: dict[str, list[dict[str, Any]]],
    role_name: str,
    *,
    exclude: set[str] | None = None,
) -> str:
    blocked = exclude or set()
    for item in rankings.get(role_name, []):
        value = str(item.get("column", ""))
        if value and value not in blocked:
            return value
    return ""


def _preferred_controls(
    column_profiles: list[dict[str, Any]],
    rankings: dict[str, list[dict[str, Any]]],
    *,
    exclude: set[str],
    limit: int = 3,
) -> list[str]:
    chosen: list[str] = []
    for item in rankings.get("control", []):
        value = str(item.get("column", ""))
        if value and value not in exclude and value not in chosen:
            chosen.append(value)
        if len(chosen) >= limit:
            return chosen
    for column in column_profiles:
        if column.get("role") == "numeric":
            value = str(column.get("name", ""))
            if value and value not in exclude and value not in chosen:
                chosen.append(value)
            if len(chosen) >= limit:
                break
    return chosen


def _choose_beginner_intent(prompt_text: str, profile: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    prompt_lower = prompt_text.lower()
    available_models = set(profile.get("suggested_models", []))
    best_rule: dict[str, Any] | None = None
    best_score = -1
    matched_terms: list[str] = []
    for rule in BEGINNER_INTENT_RULES:
        hits = [term for term in rule["terms"] if str(term) in prompt_lower]
        if not hits:
            continue
        if rule["workflow_type"] == "model" and available_models and str(rule["model_type"]) not in available_models:
            continue
        score = len(hits)
        if score > best_score:
            best_rule = rule
            best_score = score
            matched_terms = hits

    reasoning: list[str] = []
    if best_rule is None:
        has_time = bool(profile.get("column_roles", {}).get("date"))
        has_binary = len(profile.get("column_roles", {}).get("binary", [])) >= 2
        has_panel = has_time and bool(profile.get("column_roles", {}).get("categorical") or profile.get("column_roles", {}).get("text"))
        if has_binary and any(term in prompt_lower for term in ["policy", "reform", "政策", "改革", "treated", "treatment"]):
            best_rule = next(rule for rule in BEGINNER_INTENT_RULES if rule.get("model_type") == "did")
            matched_terms = ["policy-style treatment language"]
        elif has_time and any(term in prompt_lower for term in ["forecast", "predict", "预测"]):
            best_rule = next(rule for rule in BEGINNER_INTENT_RULES if rule.get("model_type") == "arima")
            matched_terms = ["forecast language"]
        elif has_panel:
            best_rule = next(rule for rule in BEGINNER_INTENT_RULES if rule.get("model_type") == "fixed_effects")
            matched_terms = ["panel-like dataset structure"]
        elif len(profile.get("column_roles", {}).get("binary", [])) >= 1 and any(term in prompt_lower for term in ["probability", "binary", "概率", "二元"]):
            best_rule = next(rule for rule in BEGINNER_INTENT_RULES if rule.get("model_type") == "logit")
            matched_terms = ["binary outcome language"]
        else:
            best_rule = {
                "workflow_type": "model",
                "processing_family": "",
                "model_family": "econometrics_baseline",
                "model_type": "ols",
                "label": "OLS",
                "reason": "No specific design dominates, so a baseline linear specification is the safest starting point.",
            }
            matched_terms = ["default baseline"]
    reasoning.append(str(best_rule["reason"]))
    if matched_terms:
        reasoning.append(f"Matched prompt signals: {', '.join(matched_terms[:5])}.")
    return best_rule, matched_terms, reasoning


def suggest_beginner_variable_plan(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    prompt_text: str,
) -> dict[str, Any]:
    prompt = prompt_text.strip()
    if len(prompt) < 8:
        raise ValueError("Please describe the research question in more detail.")

    profile = profile_dataset_asset(settings, db, user=user, workspace=workspace, asset_id=asset_id)
    column_profiles = profile.get("column_profiles", [])
    if not column_profiles:
        raise ValueError("The selected dataset does not expose any usable columns.")

    selected_intent, matched_terms, reasoning = _choose_beginner_intent(prompt, profile)
    workflow_type = str(selected_intent["workflow_type"])
    processing_family = str(selected_intent.get("processing_family") or "")
    model_family = str(selected_intent.get("model_family") or "")
    model_type = str(selected_intent.get("model_type") or "")

    rankings: dict[str, list[dict[str, Any]]] = {}
    ranking_specs = [
        ("dependent", {"numeric"}, ROLE_KEYWORDS["dependent"]),
        ("independent", {"numeric"}, ROLE_KEYWORDS["independent"]),
        ("control", {"numeric"}, ROLE_KEYWORDS["control"]),
        ("treatment", {"binary"}, ROLE_KEYWORDS["treatment"]),
        ("post", {"binary"}, ROLE_KEYWORDS["post"]),
        ("entity", {"categorical", "text"}, ROLE_KEYWORDS["entity"]),
        ("time", {"date", "categorical", "text"}, ROLE_KEYWORDS["time"]),
        ("event_time", {"numeric"}, ROLE_KEYWORDS["event_time"]),
        ("running", {"numeric"}, ROLE_KEYWORDS["running"]),
        ("instrument", {"numeric"}, ROLE_KEYWORDS["instrument"]),
        ("market", {"numeric"}, ROLE_KEYWORDS["market"]),
        ("risk_free", {"numeric"}, ROLE_KEYWORDS["risk_free"]),
        ("smb", {"numeric"}, ROLE_KEYWORDS["smb"]),
        ("hml", {"numeric"}, ROLE_KEYWORDS["hml"]),
        ("distance", {"numeric"}, ROLE_KEYWORDS["distance"]),
        ("origin_mass", {"numeric"}, ROLE_KEYWORDS["origin_mass"]),
        ("destination_mass", {"numeric"}, ROLE_KEYWORDS["destination_mass"]),
        ("series", {"numeric"}, ROLE_KEYWORDS["series"]),
        ("impulse", {"numeric"}, ROLE_KEYWORDS["impulse"]),
        ("response", {"numeric"}, ROLE_KEYWORDS["response"]),
        ("spot", {"numeric"}, ROLE_KEYWORDS["spot"]),
        ("strike", {"numeric"}, ROLE_KEYWORDS["strike"]),
        ("maturity", {"numeric"}, ROLE_KEYWORDS["maturity"]),
        ("rate", {"numeric"}, ROLE_KEYWORDS["rate"]),
        ("volatility", {"numeric"}, ROLE_KEYWORDS["volatility"]),
        ("working_capital", {"numeric"}, ROLE_KEYWORDS["working_capital"]),
        ("retained_earnings", {"numeric"}, ROLE_KEYWORDS["retained_earnings"]),
        ("ebit", {"numeric"}, ROLE_KEYWORDS["ebit"]),
        ("market_equity", {"numeric"}, ROLE_KEYWORDS["market_equity"]),
        ("total_assets", {"numeric"}, ROLE_KEYWORDS["total_assets"]),
        ("total_liabilities", {"numeric"}, ROLE_KEYWORDS["total_liabilities"]),
        ("sales", {"numeric"}, ROLE_KEYWORDS["sales"]),
        ("net_income", {"numeric"}, ROLE_KEYWORDS["net_income"]),
        ("revenue", {"numeric"}, ROLE_KEYWORDS["revenue"]),
        ("equity", {"numeric"}, ROLE_KEYWORDS["equity"]),
        ("inflation_gap", {"numeric"}, ROLE_KEYWORDS["inflation_gap"]),
        ("output_gap", {"numeric"}, ROLE_KEYWORDS["output_gap"]),
    ]
    for role_name, expected_roles, keywords in ranking_specs:
        rankings[role_name] = _rank_variable_candidates(
            column_profiles,
            prompt_text=prompt,
            role_name=role_name,
            expected_roles=expected_roles,
            role_keywords=keywords,
        )

    recommended: dict[str, Any] = {
        "workflow_type": workflow_type,
        "processing_family": processing_family,
        "model_family": model_family,
        "model_type": model_type,
    }
    prefill: dict[str, Any] = {"workflow_type": workflow_type}
    suggested_roles: list[dict[str, Any]] = []
    chosen_columns: set[str] = set()

    def add_role(role_key: str, label: str, value: str, role_type: str = "single") -> None:
        if not value:
            return
        chosen_columns.add(value)
        candidate = next((item for item in rankings.get(role_key, []) if item.get("column") == value), None)
        suggested_roles.append(
            {
                "role": role_key,
                "label": label,
                "type": role_type,
                "value": value,
                "source_name": candidate.get("source_name") if candidate else value,
                "reasoning": candidate.get("reasons", []) if candidate else [],
            }
        )

    if workflow_type == "data_processing":
        if processing_family == "visualization":
            x_column = _top_candidate(rankings, "time") or _top_candidate(rankings, "entity") or _top_candidate(rankings, "independent")
            y_column = _top_candidate(rankings, "dependent")
            prefill.update({"processing_family": "visualization", "plot_x_column": x_column, "plot_y_columns": [y_column] if y_column else [], "plot_group_column": _top_candidate(rankings, "entity"), "required_columns": [value for value in [x_column, y_column] if value]})
            add_role("time", "X variable", x_column)
            add_role("dependent", "Y variable", y_column)
            group_value = _top_candidate(rankings, "entity", exclude={x_column, y_column})
            if group_value:
                add_role("entity", "Group / color", group_value)
        elif processing_family == "time_series_features":
            sort_column = _top_candidate(rankings, "time")
            series_values = [str(item.get("column")) for item in rankings.get("series", []) if item.get("column")][:3]
            prefill.update({"processing_family": "time_series_features", "sort_column": sort_column, "time_group_column": _top_candidate(rankings, "entity"), "return_columns": series_values, "difference_columns": series_values[:2], "required_columns": [value for value in [sort_column, *series_values] if value]})
            add_role("time", "Sort / time column", sort_column)
            for value in series_values:
                add_role("series", "Series column", value, role_type="multi")
        else:
            dependent = _top_candidate(rankings, "dependent")
            independents = [str(item.get("column")) for item in rankings.get("independent", []) if item.get("column") and item.get("column") != dependent][:3]
            required_columns = [value for value in [dependent, *independents] if value]
            numeric_columns = [value for value in required_columns if value in set(profile.get("column_roles", {}).get("numeric", []))]
            binary_columns = [value for value in required_columns if value in set(profile.get("column_roles", {}).get("binary", []))]
            date_columns = [value for value in required_columns if value in set(profile.get("column_roles", {}).get("date", []))]
            prefill.update({"processing_family": processing_family or "sample_preparation", "include_columns": required_columns, "required_columns": required_columns, "numeric_columns": numeric_columns, "binary_columns": binary_columns, "date_columns": date_columns})
            add_role("dependent", "Priority variable", dependent)
            for value in independents:
                add_role("independent", "Supporting variable", value, role_type="multi")
    else:
        if model_type in {"logit", "probit"}:
            rankings["dependent"] = _rank_variable_candidates(column_profiles, prompt_text=prompt, role_name="dependent", expected_roles={"binary"}, role_keywords=ROLE_KEYWORDS["dependent"])
        dependent = _top_candidate(rankings, "dependent")
        if model_type == "var":
            series_columns = [str(item.get("column")) for item in rankings.get("series", []) if item.get("column")][:3]
            prefill.update({"model_family": model_family, "model_type": model_type, "series_columns": series_columns, "time_column": _top_candidate(rankings, "time")})
            for value in series_columns:
                add_role("series", "Series variable", value, role_type="multi")
        else:
            independents = [str(item.get("column")) for item in rankings.get("independent", []) if item.get("column") and item.get("column") != dependent][:3]
            controls = _preferred_controls(column_profiles, rankings, exclude={value for value in [dependent, *independents] if value})
            prefill.update({"model_family": model_family, "model_type": model_type, "dependent": dependent, "independents": independents, "controls": controls})
            add_role("dependent", "Recommended outcome variable", dependent)
            for value in independents:
                add_role("independent", "Recommended explanatory variable", value, role_type="multi")
            for value in controls:
                if value not in {role["value"] for role in suggested_roles}:
                    suggested_roles.append({"role": "control", "label": "Suggested control", "type": "multi", "value": value, "source_name": value, "reasoning": []})
        if model_type in {"did", "event_study"}:
            treatment = _top_candidate(rankings, "treatment", exclude=chosen_columns)
            prefill["treatment_column"] = treatment
            add_role("treatment", "Treatment indicator", treatment)
        if model_type == "did":
            post = _top_candidate(rankings, "post", exclude=chosen_columns)
            prefill["post_column"] = post
            add_role("post", "Post indicator", post)
        if model_type == "event_study":
            event_time = _top_candidate(rankings, "event_time", exclude=chosen_columns) or _top_candidate(rankings, "time", exclude=chosen_columns)
            prefill["event_time_column"] = event_time
            add_role("event_time", "Relative event time", event_time)
        if model_type in {"fixed_effects", "panel_iv", "event_study"}:
            entity = _top_candidate(rankings, "entity", exclude=chosen_columns)
            time_column = _top_candidate(rankings, "time", exclude=chosen_columns)
            prefill["entity_column"] = entity
            prefill["time_column"] = time_column
            add_role("entity", "Entity / unit column", entity)
            add_role("time", "Time column", time_column)
        if model_type == "rdd":
            running = _top_candidate(rankings, "running", exclude=chosen_columns)
            prefill["running_column"] = running
            add_role("running", "Running variable", running)
        if model_type == "gravity":
            origin_mass = _top_candidate(rankings, "origin_mass", exclude=chosen_columns) or _top_candidate(rankings, "independent", exclude=chosen_columns)
            destination_mass = _top_candidate(rankings, "destination_mass", exclude=chosen_columns | {origin_mass}) or _top_candidate(rankings, "control", exclude=chosen_columns | {origin_mass})
            distance = _top_candidate(rankings, "distance", exclude=chosen_columns | {origin_mass, destination_mass})
            prefill["origin_mass_column"] = origin_mass
            prefill["destination_mass_column"] = destination_mass
            prefill["distance_column"] = distance
            add_role("origin_mass", "Origin mass", origin_mass)
            add_role("destination_mass", "Destination mass", destination_mass)
            add_role("distance", "Distance variable", distance)
        if model_type in {"iv_2sls", "panel_iv"}:
            endogenous = prefill.get("independents", [None])[0] or _top_candidate(rankings, "independent", exclude=chosen_columns)
            instruments = [str(item.get("column")) for item in rankings.get("instrument", []) if item.get("column") and item.get("column") not in chosen_columns and item.get("column") != endogenous][:2]
            prefill["endogenous_column"] = str(endogenous or "")
            prefill["instrument_columns"] = instruments
            add_role("independent", "Endogenous regressor", str(endogenous or ""))
            for value in instruments:
                add_role("instrument", "Instrument variable", value, role_type="multi")
        if model_type in {"arima", "arch", "garch", "virf", "historical_var", "parametric_var", "ewma_volatility"}:
            time_column = _top_candidate(rankings, "time", exclude=chosen_columns)
            prefill["time_column"] = time_column
            add_role("time", "Time column", time_column)
        if model_type in {"arch", "garch", "virf"}:
            volatility_target = dependent or _top_candidate(rankings, "series", exclude=chosen_columns) or _top_candidate(rankings, "dependent", exclude=chosen_columns)
            prefill["dependent"] = volatility_target
            add_role("series", "Return series", volatility_target)
        if model_type in {"svar_irf", "dy_connectedness", "bk_connectedness"}:
            time_column = _top_candidate(rankings, "time", exclude=chosen_columns)
            series_values = [str(item.get("column")) for item in rankings.get("series", []) if item.get("column")][:4]
            prefill["time_column"] = time_column
            prefill["series_columns"] = series_values
            add_role("time", "Time column", time_column)
            for value in series_values:
                add_role("series", "System series", value, role_type="multi")
        if model_type == "svar_irf":
            impulse_value = _top_candidate(rankings, "impulse", exclude=chosen_columns) or (prefill.get("series_columns") or [None])[0]
            response_value = _top_candidate(rankings, "response", exclude=chosen_columns | {str(impulse_value or "")}) or ((prefill.get("series_columns") or [None, None])[1] if len(prefill.get("series_columns") or []) > 1 else "")
            prefill["impulse_column"] = impulse_value
            prefill["response_column"] = response_value
            add_role("impulse", "Impulse variable", str(impulse_value or ""))
            add_role("response", "Response variable", str(response_value or ""))
        if model_type in {"capm", "fama_french_3"}:
            market_column = _top_candidate(rankings, "market", exclude=chosen_columns)
            risk_free_column = _top_candidate(rankings, "risk_free", exclude=chosen_columns | {market_column})
            prefill["market_column"] = market_column
            prefill["risk_free_column"] = risk_free_column
            add_role("market", "Market factor", market_column)
            if risk_free_column:
                add_role("risk_free", "Risk-free rate", risk_free_column)
            if model_type == "fama_french_3":
                smb_column = _top_candidate(rankings, "smb", exclude=chosen_columns | {market_column, risk_free_column})
                hml_column = _top_candidate(rankings, "hml", exclude=chosen_columns | {market_column, risk_free_column, smb_column})
                prefill["smb_column"] = smb_column
                prefill["hml_column"] = hml_column
                add_role("smb", "SMB factor", smb_column)
                add_role("hml", "HML factor", hml_column)
        if model_type in {"mean_variance", "minimum_variance", "risk_parity"}:
            series_columns = [str(item.get("column")) for item in rankings.get("series", []) if item.get("column")][:4]
            prefill["series_columns"] = series_columns
            for value in series_columns:
                add_role("series", "Return series", value, role_type="multi")
        if model_type in {"black_scholes", "binomial_option"}:
            for role_key, field_name, label in [
                ("spot", "spot_column", "Spot price"),
                ("strike", "strike_column", "Strike"),
                ("maturity", "maturity_column", "Time to maturity"),
                ("rate", "rate_column", "Risk-free rate"),
                ("volatility", "volatility_column", "Volatility"),
            ]:
                value = _top_candidate(rankings, role_key, exclude=chosen_columns)
                prefill[field_name] = value
                add_role(role_key, label, value)
        if model_type == "altman_z":
            for role_key, field_name, label in [
                ("working_capital", "working_capital_column", "Working capital"),
                ("retained_earnings", "retained_earnings_column", "Retained earnings"),
                ("ebit", "ebit_column", "EBIT"),
                ("market_equity", "market_equity_column", "Market equity"),
                ("sales", "sales_column", "Sales"),
                ("total_assets", "total_assets_column", "Total assets"),
                ("total_liabilities", "total_liabilities_column", "Total liabilities"),
            ]:
                value = _top_candidate(rankings, role_key, exclude=chosen_columns)
                prefill[field_name] = value
                add_role(role_key, label, value)
        if model_type == "dupont":
            for role_key, field_name, label in [
                ("net_income", "net_income_column", "Net income"),
                ("revenue", "revenue_column", "Revenue"),
                ("total_assets", "total_assets_column", "Total assets"),
                ("equity", "equity_column", "Equity"),
            ]:
                value = _top_candidate(rankings, role_key, exclude=chosen_columns)
                prefill[field_name] = value
                add_role(role_key, label, value)
        if model_type == "taylor_rule":
            inflation_gap = _top_candidate(rankings, "inflation_gap", exclude=chosen_columns)
            output_gap = _top_candidate(rankings, "output_gap", exclude=chosen_columns | {inflation_gap})
            prefill["inflation_gap_column"] = inflation_gap
            prefill["output_gap_column"] = output_gap
            add_role("inflation_gap", "Inflation gap", inflation_gap)
            add_role("output_gap", "Output gap", output_gap)

    recommended_title = str(selected_intent.get("label") or (model_type or processing_family or "Data Lab"))
    manual_checklist = [
        "Read the suggested role cards and confirm they match the actual research design, not just the column names.",
        "Open the dataset profile and compare the selected columns against the preview rows before running the workbench.",
        "If the recommended model is DID, Event Study, RDD, or IV, manually verify the identifying variables before trusting the estimate.",
        "After applying the suggestions, open the detail page for the selected method family and check the manual checklist there as well.",
    ]
    if workflow_type == "model":
        manual_checklist.append("Treat the suggested controls as a starting point, not a final causal specification.")

    numeric_roles = set(profile.get("column_roles", {}).get("numeric", []))
    binary_roles = set(profile.get("column_roles", {}).get("binary", []))
    date_roles = set(profile.get("column_roles", {}).get("date", []))
    preparation_hints = {
        "required_columns": list(dict.fromkeys([role["value"] for role in suggested_roles if role["value"]])),
        "numeric_columns": list(dict.fromkeys([role["value"] for role in suggested_roles if role["value"] in numeric_roles])),
        "binary_columns": list(dict.fromkeys([role["value"] for role in suggested_roles if role["value"] in binary_roles])),
        "date_columns": list(dict.fromkeys([role["value"] for role in suggested_roles if role["value"] in date_roles])),
    }
    prefill.setdefault("required_columns", preparation_hints["required_columns"])
    prefill.setdefault("numeric_columns", preparation_hints["numeric_columns"])
    prefill.setdefault("binary_columns", preparation_hints["binary_columns"])
    prefill.setdefault("date_columns", preparation_hints["date_columns"])

    return {
        "prompt": prompt,
        "summary": f"Recommended starting workflow: {recommended_title}. Use it as a first-pass specification, then verify the variable roles manually.",
        "workflow_recommendation": {
            "workflow_type": workflow_type,
            "processing_family": processing_family,
            "model_family": model_family,
            "model_type": model_type,
            "label": recommended_title,
        },
        "reasoning": reasoning,
        "suggested_roles": suggested_roles,
        "preparation_hints": preparation_hints,
        "prefill": prefill,
        "candidate_rankings": rankings,
        "manual_checklist": manual_checklist,
        "transparency": {
            "prompt_tokens": _analysis_text_tokens(prompt),
            "matched_intent_terms": matched_terms,
            "dataset_signals": {
                "numeric_columns": len(profile.get("column_roles", {}).get("numeric", [])),
                "binary_columns": len(profile.get("column_roles", {}).get("binary", [])),
                "date_columns": len(profile.get("column_roles", {}).get("date", [])),
                "categorical_columns": len(profile.get("column_roles", {}).get("categorical", [])),
                "text_columns": len(profile.get("column_roles", {}).get("text", [])),
                "suggested_models": profile.get("suggested_models", []),
            },
        },
    }


def build_processing_result_detail(
    settings: Settings,
    db: Session,
    *,
    user: User,
    asset_id: str,
) -> dict[str, Any]:
    asset = get_owned_asset(db, user=user, asset_id=asset_id)
    if asset.kind not in DATASET_KINDS:
        raise ValueError("This asset is not a structured dataset.")
    workspace = db.get(Workspace, asset.workspace_id)
    if not workspace or workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    detail = (asset.metadata_json or {}).get("processing_result")
    asset_payload = serialize_asset(asset)
    if isinstance(asset_payload.get("metadata"), dict):
        asset_payload["metadata"] = {key: value for key, value in asset_payload["metadata"].items() if key != "processing_result"}
    if not isinstance(detail, dict):
        summary = (asset.metadata_json or {}).get("preparation_summary") or {}
        detail = {
            "workflow_type": "data_processing",
            "processing_family": summary.get("workflow_group") or "sample_preparation",
            "asset": asset_payload,
            "summary": summary,
            "audit_trail": {
                "source_asset_id": (asset.metadata_json or {}).get("source_asset_id"),
                "prepared_asset_id": asset.id,
                "prepared_download_url": f"/api/assets/{asset.id}/download",
                "manual_checklist": [
                    "Download the prepared sample and compare row counts, columns, and preview rows.",
                    "Reapply every documented transformation in order using the raw source asset.",
                    "Confirm derived columns and filters match the saved processing summary.",
                ],
                "operations": summary,
            },
            "result_detail_path": f"/data-lab/results/processing/{asset.id}",
        }
    profile = profile_dataset_asset(settings, db, user=user, workspace=workspace, asset_id=asset.id)
    if isinstance(profile.get("asset", {}).get("metadata"), dict):
        profile["asset"]["metadata"] = {
            key: value for key, value in profile["asset"]["metadata"].items() if key != "processing_result"
        }
    detail["asset"] = asset_payload
    detail["result_detail_path"] = detail.get("result_detail_path") or f"/data-lab/results/processing/{asset.id}"
    detail["detail_path"] = detail["result_detail_path"]
    detail["status"] = "ready"
    detail["reason"] = "Processing result is ready for review."
    detail["next_action"] = "open_detail"
    detail["template_source"] = _template_source_value(detail)
    detail["variant_source"] = _variant_source_value(detail)
    detail["profile"] = profile
    detail.setdefault("preview_rows", profile.get("preview_rows", []))
    detail["interpretation"] = _build_processing_result_interpretation(detail)
    detail["workspace_id"] = workspace.id
    return detail


def prepare_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    workflow_group: str = "sample_preparation",
    include_columns: list[str] | None = None,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    binary_columns: list[str] | None = None,
    date_columns: list[str] | None = None,
    impute_columns: list[str] | None = None,
    impute_method: str = "none",
    winsorize_columns: list[str] | None = None,
    winsor_lower_quantile: float = 0.01,
    winsor_upper_quantile: float = 0.99,
    log_transform_columns: list[str] | None = None,
    standardize_columns: list[str] | None = None,
    minmax_scale_columns: list[str] | None = None,
    outlier_columns: list[str] | None = None,
    outlier_method: str = "none",
    outlier_threshold: float = 1.5,
    sort_column: str = "",
    time_group_column: str = "",
    difference_columns: list[str] | None = None,
    return_columns: list[str] | None = None,
    return_method: str = "simple",
    lag_columns: list[str] | None = None,
    lag_periods: int = 1,
    lead_columns: list[str] | None = None,
    lead_periods: int = 1,
    rolling_mean_columns: list[str] | None = None,
    rolling_volatility_columns: list[str] | None = None,
    rolling_window: int = 5,
    drop_duplicates: bool = True,
    drop_missing_required: bool = True,
    template_id: str = "",
    template_name: str = "",
    variant_label: str = "",
    variant_spec: dict[str, Any] | None = None,
    effective_specification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    prepared_frame, summary = _prepare_selected_sample(
        frame,
        include_columns=include_columns,
        required_columns=required_columns,
        numeric_columns=numeric_columns,
        binary_columns=binary_columns,
        date_columns=date_columns,
        impute_columns=impute_columns,
        impute_method=impute_method,
        winsorize_columns=winsorize_columns,
        winsor_lower_quantile=winsor_lower_quantile,
        winsor_upper_quantile=winsor_upper_quantile,
        log_transform_columns=log_transform_columns,
        standardize_columns=standardize_columns,
        minmax_scale_columns=minmax_scale_columns,
        outlier_columns=outlier_columns,
        outlier_method=outlier_method,
        outlier_threshold=outlier_threshold,
        sort_column=sort_column,
        time_group_column=time_group_column,
        difference_columns=difference_columns,
        return_columns=return_columns,
        return_method=return_method,
        lag_columns=lag_columns,
        lag_periods=lag_periods,
        lead_columns=lead_columns,
        lead_periods=lead_periods,
        rolling_mean_columns=rolling_mean_columns,
        rolling_volatility_columns=rolling_volatility_columns,
        rolling_window=rolling_window,
        drop_duplicates=drop_duplicates,
        drop_missing_required=drop_missing_required,
    )
    csv_bytes = prepared_frame.to_csv(index=False).encode("utf-8")
    prepared_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-prepared.csv",
        content=csv_bytes,
        content_type="text/csv",
        description=f"Prepared analysis sample derived from {asset.title}",
    )
    preview_rows = _frame_preview_rows(prepared_frame)
    audit_trail = {
        "source_asset_id": asset.id,
        "source_asset_title": asset.title,
        "prepared_asset_id": prepared_asset.id,
        "prepared_download_url": f"/api/assets/{prepared_asset.id}/download",
        "template_id": template_id,
        "template_name": template_name,
        "variant_label": variant_label,
        "variant_spec": dict(variant_spec or {}) if isinstance(variant_spec, dict) else {},
        "effective_specification": dict(effective_specification or {}) if isinstance(effective_specification, dict) else {},
        "manual_checklist": [
            "Download the prepared asset and compare row/column counts with rows_after_prepare and columns.",
            "Reapply each cleaning step in order: imputation, winsorization, transforms, outlier filter, and missing-value filtering.",
            "Verify the preview_rows against the downloaded prepared sample.",
        ],
        "operations": {
            "required_columns": summary["required_columns"],
            "numeric_columns": summary["numeric_columns"],
            "binary_columns": summary["binary_columns"],
            "date_columns": summary["date_columns"],
            "imputed_columns": summary["imputed_columns"],
            "winsorized_columns": summary["winsorized_columns"],
            "transformed_columns": summary["transformed_columns"],
            "time_series_features": summary["time_series_features"],
            "derived_columns": summary["derived_columns"],
            "outlier_columns": summary["outlier_columns"],
            "outlier_method": summary["outlier_method"],
            "outlier_threshold": summary["outlier_threshold"],
            "drop_duplicates": drop_duplicates,
            "drop_missing_required": drop_missing_required,
            "workflow_group": workflow_group or "sample_preparation",
        },
    }
    processing_result = {
        "workflow_type": "data_processing",
        "processing_family": workflow_group or "sample_preparation",
        "template_id": template_id,
        "template_name": template_name,
        "variant_label": variant_label,
        "variant_spec": dict(variant_spec or {}) if isinstance(variant_spec, dict) else {},
        "effective_specification": dict(effective_specification or {}) if isinstance(effective_specification, dict) else {},
        "asset": serialize_asset(prepared_asset),
        "summary": summary,
        "preview_rows": preview_rows,
        "audit_trail": audit_trail,
        "result_detail_path": f"/data-lab/results/processing/{prepared_asset.id}",
        "detail_path": f"/data-lab/results/processing/{prepared_asset.id}",
        "status": "ready",
        "reason": "Processing result is ready for review.",
        "next_action": "open_detail",
        "template_source": template_name or template_id,
        "variant_source": variant_label or ("custom" if isinstance(variant_spec, dict) and variant_spec else ""),
    }
    prepared_asset.metadata_json = {
        **prepared_asset.metadata_json,
        "preparation_summary": summary,
        "source_asset_id": asset.id,
        "processing_result": processing_result,
    }
    db.flush()
    return processing_result


def _serialize_model_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    sample = frame[columns].copy()
    for column in columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    return sample.dropna().copy()


def _serialize_coefficients(result: Any) -> list[dict[str, Any]]:
    params = result.params
    if hasattr(params, "index"):
        term_names = list(params.index)
        param_values = params
    else:
        term_names = list(getattr(result.model, "exog_names", []))
        if not term_names:
            term_names = [f"x{i}" for i in range(len(params))]
        param_values = pd.Series(params, index=term_names)

    bse = result.bse if hasattr(result, "bse") else None
    if bse is None:
        bse = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(bse, "index"):
        bse = pd.Series(bse, index=term_names)

    tvalues = getattr(result, "tvalues", None)
    if tvalues is None:
        tvalues = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(tvalues, "index"):
        tvalues = pd.Series(tvalues, index=term_names)

    pvalues = getattr(result, "pvalues", None)
    if pvalues is None:
        pvalues = pd.Series([None] * len(term_names), index=term_names)
    elif not hasattr(pvalues, "index"):
        pvalues = pd.Series(pvalues, index=term_names)

    rows: list[dict[str, Any]] = []
    for name in term_names:
        rows.append(
            {
                "term": name,
                "coefficient": float(param_values[name]),
                "std_error": float(bse[name]) if name in bse.index and pd.notna(bse[name]) else None,
                "t_stat": float(tvalues[name]) if name in tvalues.index and pd.notna(tvalues[name]) else None,
                "p_value": float(pvalues[name]) if name in pvalues.index and pd.notna(pvalues[name]) else None,
            }
        )
    return rows


def _safe_result_float_attr(result: Any, attribute: str) -> float | None:
    try:
        value = getattr(result, attribute, None)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fit_ols(sample: pd.DataFrame, dependent: str, regressors: list[str], *, robust_covariance: bool = True) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(10, len(regressors) + 4):
        raise ValueError("Not enough complete observations for the selected model.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    return sm.OLS(sample[dependent], design).fit(cov_type="HC1" if robust_covariance else "nonrobust")


def _fit_binary_response(
    sample: pd.DataFrame,
    dependent: str,
    regressors: list[str],
    *,
    model_kind: str,
    robust_covariance: bool = True,
) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(20, len(regressors) * 3):
        raise ValueError("Not enough complete observations for the selected binary response model.")
    if sample[dependent].nunique(dropna=True) < 2:
        raise ValueError("Binary response models require both 0 and 1 outcomes.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    model_class = sm.Logit if model_kind == "logit" else sm.Probit
    try:
        fitted = model_class(sample[dependent], design).fit(
            disp=False,
            cov_type="HC1" if robust_covariance else "nonrobust",
        )
    except PerfectSeparationError as exc:
        raise ValueError("Perfect separation detected; try different regressors or a larger sample.") from exc
    except Exception as exc:
        raise ValueError(f"{model_kind.title()} estimation failed: {exc}") from exc
    return fitted


def _fit_iv_2sls(
    sample: pd.DataFrame,
    dependent: str,
    exogenous: list[str],
    endogenous: str,
    instruments: list[str],
    *,
    robust_covariance: bool = True,
) -> tuple[Any, str]:
    if not instruments:
        raise ValueError("IV-2SLS requires at least one instrument.")
    regressor_count = len(exogenous) + 1
    if len(sample) < max(12, regressor_count + len(instruments) + 4):
        raise ValueError("Not enough complete observations for IV-2SLS.")
    exog_design = pd.concat(
        [sm.add_constant(sample[exogenous], has_constant="add"), sample[[endogenous]]],
        axis=1,
    )
    instrument_design = pd.concat(
        [sm.add_constant(sample[exogenous], has_constant="add"), sample[instruments]],
        axis=1,
    )
    fitted = IV2SLS(sample[dependent], exog_design, instrument_design).fit()
    if robust_covariance:
        try:
            fitted = fitted.get_robustcov_results(cov_type="HC1")
            return fitted, "HC1"
        except Exception:
            return fitted, "nonrobust"
    return fitted, "nonrobust"


def _fit_ppml(sample: pd.DataFrame, dependent: str, regressors: list[str], *, robust_covariance: bool = True) -> Any:
    if not regressors:
        raise ValueError("At least one explanatory variable is required.")
    if len(sample) < max(12, len(regressors) + 4):
        raise ValueError("Not enough complete observations for PPML.")
    if (sample[dependent] < 0).any():
        raise ValueError("PPML requires a nonnegative dependent variable.")
    design = sm.add_constant(sample[regressors], has_constant="add")
    return sm.GLM(
        sample[dependent],
        design,
        family=sm.families.Poisson(),
    ).fit(cov_type="HC1" if robust_covariance else "nonrobust")


def _build_fe_dummies(
    sample: pd.DataFrame,
    *,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    entity_dummies = pd.get_dummies(sample[entity_column], prefix=f"fe_{entity_column}", drop_first=True, dtype=float)
    fe_frames = [entity_dummies]
    fe_labels = [entity_column]
    if include_time_effects and time_column:
        time_dummies = pd.get_dummies(sample[time_column], prefix=f"fe_{time_column}", drop_first=True, dtype=float)
        fe_frames.append(time_dummies)
        fe_labels.append(time_column)
    if not fe_frames:
        return pd.DataFrame(index=sample.index), fe_labels
    return pd.concat(fe_frames, axis=1), fe_labels


def _model_result_payload(
    *,
    model_type: str,
    model_label: str,
    asset: DataAsset,
    dependent: str,
    regressors: list[str],
    sample: pd.DataFrame,
    result: Any,
    narrative_lines: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = extra or {}
    covariance_type = extra.get("covariance_type") or getattr(result, "cov_type", "nonrobust")
    equation_terms = regressors if regressors else ["1"]
    payload = {
        "model_type": model_type,
        "model_label": model_label,
        "asset": serialize_asset(asset),
        "dependent": dependent,
        "regressors": regressors,
        "observations": int(getattr(result, "nobs", len(sample))),
        "r_squared": _safe_result_float_attr(result, "rsquared"),
        "adj_r_squared": _safe_result_float_attr(result, "rsquared_adj"),
        "pseudo_r_squared": _safe_result_float_attr(result, "prsquared"),
        "aic": _safe_result_float_attr(result, "aic"),
        "bic": _safe_result_float_attr(result, "bic"),
        "log_likelihood": _safe_result_float_attr(result, "llf"),
        "coefficients": _serialize_coefficients(result),
        "narrative": narrative_lines,
        "sample_columns": list(sample.columns),
        "sample_preview": _frame_preview_rows(sample, limit=5),
        "specification": {
            "model_type": model_type,
            "model_label": model_label,
            "dependent": dependent,
            "regressors": regressors,
            "covariance_type": covariance_type,
            "equation": f"{dependent} ~ {' + '.join(equation_terms)}",
        },
        "audit_trail": {
            "sample_asset_id": asset.id,
            "sample_title": asset.title,
            "sample_download_url": f"/api/assets/{asset.id}/download",
            "rows_used": int(len(sample)),
            "sample_columns": list(sample.columns),
            "covariance_type": covariance_type,
            "manual_checklist": [
                "Download the prepared sample asset referenced in sample_asset_id.",
                "Rebuild any derived regressors listed in derived_columns before estimation.",
                "Use the listed regressors, covariance_type, and sample filters to reproduce the model manually.",
                "Compare the reproduced coefficient table with the coefficients array term by term.",
            ],
        },
    }
    audit_extra = extra.pop("audit_trail", None)
    if audit_extra:
        payload["audit_trail"].update(audit_extra)
    payload.update(extra)
    return payload


def _nonregression_result_payload(
    *,
    model_type: str,
    model_label: str,
    asset: DataAsset,
    sample: pd.DataFrame | None,
    narrative_lines: list[str],
    specification: dict[str, Any],
    audit_trail: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    tables: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "model_type": model_type,
        "model_label": model_label,
        "asset": serialize_asset(asset),
        "observations": int(len(sample)) if sample is not None else 0,
        "narrative": narrative_lines,
        "specification": specification,
        "audit_trail": {
            "sample_asset_id": asset.id,
            "sample_title": asset.title,
            "sample_download_url": f"/api/assets/{asset.id}/download",
            **audit_trail,
        },
        "metrics": metrics or {},
        "tables": tables or {},
        "sample_columns": list(sample.columns) if sample is not None else [],
        "sample_preview": _frame_preview_rows(sample, limit=5) if sample is not None else [],
    }
    if extra:
        payload.update(extra)
    return payload


def _sort_sample_by_time(sample: pd.DataFrame, time_column: str) -> pd.DataFrame:
    if not time_column or time_column not in sample.columns:
        return sample
    prepared = sample.copy()
    parsed = pd.to_datetime(prepared[time_column], errors="coerce")
    if parsed.notna().sum():
        prepared["__sort_time"] = parsed
    else:
        numeric = pd.to_numeric(prepared[time_column], errors="coerce")
        if numeric.notna().sum():
            prepared["__sort_time"] = numeric
        else:
            prepared["__sort_time"] = prepared[time_column].astype(str)
    prepared = prepared.sort_values("__sort_time").drop(columns="__sort_time")
    return prepared


def _frame_records(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    view = frame.head(limit) if limit is not None else frame
    records: list[dict[str, Any]] = []
    for row in view.to_dict(orient="records"):
        records.append({str(key): _serialize_preview_value(value) for key, value in row.items()})
    return records


def _coerce_named_series(values: Any, names: list[str]) -> pd.Series:
    if values is None:
        return pd.Series([None] * len(names), index=names, dtype="object")
    if hasattr(values, "index"):
        series = pd.Series(values)
        return series.reindex(names)
    return pd.Series(list(values), index=names)


def _parameter_table(
    params: Any,
    *,
    std_errors: Any = None,
    tvalues: Any = None,
    pvalues: Any = None,
) -> list[dict[str, Any]]:
    if hasattr(params, "index"):
        names = [str(item) for item in params.index]
        param_series = pd.Series(params).reindex(names)
    else:
        values = list(params)
        names = [f"param_{index + 1}" for index in range(len(values))]
        param_series = pd.Series(values, index=names)
    std_series = _coerce_named_series(std_errors, names)
    t_series = _coerce_named_series(tvalues, names)
    p_series = _coerce_named_series(pvalues, names)
    rows: list[dict[str, Any]] = []
    for name in names:
        rows.append(
            {
                "term": name,
                "coefficient": _safe_float(param_series.get(name)),
                "std_error": _safe_float(std_series.get(name)),
                "t_stat": _safe_float(t_series.get(name)),
                "p_value": _safe_float(p_series.get(name)),
            }
        )
    return rows


def _save_model_figure_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    source_asset: DataAsset,
    figure: Any,
    filename_slug: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    _pyplot().close(figure)
    filename = f"{Path(source_asset.title).stem}-{filename_slug}.png"
    chart_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=filename,
        content=buffer.getvalue(),
        content_type="image/png",
        description=summary,
    )
    chart_asset.metadata_json = {
        **(chart_asset.metadata_json or {}),
        "analysis_kind": "model_figure",
        "source_model": title,
        "source_asset_id": source_asset.id,
        "summary": summary,
    }
    db.flush()
    return {
        "asset_id": chart_asset.id,
        "title": title,
        "summary": summary,
        "download_url": f"/api/assets/{chart_asset.id}/download",
        "asset": serialize_asset(chart_asset),
    }


def _prepare_time_series_sample(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    min_rows: int = 24,
) -> tuple[DataAsset, pd.DataFrame]:
    series_columns = [column for column in series_columns if column]
    if not series_columns:
        raise ValueError("At least one series column is required.")
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [*series_columns, *([time_column] if time_column else [])]
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in series_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    if len(sample) < min_rows:
        raise ValueError(f"At least {min_rows} complete observations are required for the selected time-series model.")
    return asset, sample


def _var_ma_matrices(coefs: np.ndarray, horizon: int) -> list[np.ndarray]:
    order, dimension, _ = coefs.shape
    matrices = [np.eye(dimension)]
    for step in range(1, horizon):
        current = np.zeros((dimension, dimension))
        for lag in range(1, min(order, step) + 1):
            current += coefs[lag - 1] @ matrices[step - lag]
        matrices.append(current)
    return matrices


def _generalized_fevd(
    coefs: np.ndarray,
    sigma_u: np.ndarray,
    *,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray]:
    matrices = _var_ma_matrices(coefs, horizon)
    count = sigma_u.shape[0]
    raw = np.zeros((count, count), dtype=float)
    for row_index in range(count):
        denominator = 0.0
        for matrix in matrices:
            denominator += float((matrix @ sigma_u @ matrix.T)[row_index, row_index])
        if denominator <= 0:
            continue
        for shock_index in range(count):
            sigma_jj = float(sigma_u[shock_index, shock_index])
            if sigma_jj <= 0:
                continue
            numerator = 0.0
            for matrix in matrices:
                impact = float((matrix @ sigma_u)[row_index, shock_index])
                numerator += (impact**2) / sigma_jj
            raw[row_index, shock_index] = numerator / denominator
    row_sums = raw.sum(axis=1, keepdims=True)
    normalized = np.divide(raw, row_sums, out=np.zeros_like(raw), where=row_sums > 0)
    return raw, normalized


def _connectedness_matrix_rows(matrix: np.ndarray, labels: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index, label in enumerate(labels):
        record = {"variable": label}
        for column_index, column_label in enumerate(labels):
            record[column_label] = float(matrix[row_index, column_index] * 100.0)
        rows.append(record)
    return rows


def _directional_connectedness_rows(matrix: np.ndarray, labels: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        from_others = float((matrix[index, :].sum() - matrix[index, index]) * 100.0)
        to_others = float((matrix[:, index].sum() - matrix[index, index]) * 100.0)
        rows.append(
            {
                "variable": label,
                "from_others": from_others,
                "to_others": to_others,
                "net": to_others - from_others,
                "own_share": float(matrix[index, index] * 100.0),
            }
        )
    return rows


def _connectedness_heatmap_figure(matrix: np.ndarray, labels: list[str], *, title: str) -> Any:
    figure, axis = _pyplot().subplots(figsize=(7.4, 5.8), dpi=160)
    image = axis.imshow(matrix * 100.0, cmap="YlGnBu")
    axis.set_xticks(range(len(labels)))
    axis.set_xticklabels(labels, rotation=35, ha="right")
    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels)
    axis.set_title(title)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            axis.text(
                column_index,
                row_index,
                f"{matrix[row_index, column_index] * 100.0:.1f}",
                ha="center",
                va="center",
                color="#10231d",
                fontsize=8,
            )
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Percent of forecast error variance")
    figure.tight_layout()
    return figure


def _band_frequency_masks(short_horizon: int, medium_horizon: int, frequencies: np.ndarray) -> list[tuple[str, np.ndarray]]:
    short_h = max(2, int(short_horizon))
    medium_h = max(short_h + 1, int(medium_horizon))
    short_cut = min(np.pi, 2.0 * np.pi / short_h)
    medium_cut = min(short_cut, 2.0 * np.pi / medium_h)
    short_mask = frequencies >= short_cut
    medium_mask = (frequencies >= medium_cut) & (frequencies < short_cut)
    long_mask = frequencies < medium_cut
    return [
        (f"Short (<= {short_h})", short_mask),
        (f"Medium ({short_h + 1}-{medium_h})", medium_mask),
        (f"Long (> {medium_h})", long_mask),
    ]


def _bk_frequency_connectedness(
    coefs: np.ndarray,
    sigma_u: np.ndarray,
    *,
    short_horizon: int,
    medium_horizon: int,
    truncation_horizon: int,
    grid_points: int = 256,
) -> list[dict[str, Any]]:
    matrices = _var_ma_matrices(coefs, max(int(truncation_horizon), int(medium_horizon) * 3, 80))
    frequencies = np.linspace(1e-4, np.pi, int(grid_points))
    count = sigma_u.shape[0]
    sigma_diag = np.diag(sigma_u).astype(float)
    total_power = np.zeros(count, dtype=float)
    band_raw: list[tuple[str, np.ndarray]] = []
    band_masks = _band_frequency_masks(short_horizon, medium_horizon, frequencies)
    for band_name, _ in band_masks:
        band_raw.append((band_name, np.zeros((count, count), dtype=float)))
    for frequency_index, omega in enumerate(frequencies):
        transfer = np.zeros((count, count), dtype=np.complex128)
        for lag, matrix in enumerate(matrices):
            transfer += matrix * np.exp(-1j * omega * lag)
        spectral = transfer @ sigma_u @ transfer.conjugate().T
        power = np.real(np.diag(spectral))
        total_power += power
        transformed = transfer @ sigma_u
        contrib = np.zeros((count, count), dtype=float)
        for row_index in range(count):
            for shock_index in range(count):
                if sigma_diag[shock_index] <= 0:
                    continue
                contrib[row_index, shock_index] = (abs(transformed[row_index, shock_index]) ** 2) / sigma_diag[shock_index]
        for band_index, (_, mask) in enumerate(band_masks):
            if mask[frequency_index]:
                band_raw[band_index][1][:] = band_raw[band_index][1] + contrib
    results: list[dict[str, Any]] = []
    for band_name, raw_matrix in band_raw:
        share_matrix = np.divide(raw_matrix, total_power[:, None], out=np.zeros_like(raw_matrix), where=total_power[:, None] > 0)
        band_row_sums = share_matrix.sum(axis=1, keepdims=True)
        normalized_matrix = np.divide(
            share_matrix,
            band_row_sums,
            out=np.zeros_like(share_matrix),
            where=band_row_sums > 0,
        )
        results.append(
            {
                "band": band_name,
                "share_matrix": share_matrix,
                "normalized_matrix": normalized_matrix,
                "band_variance_share": float(np.nanmean(band_row_sums)) if np.isfinite(band_row_sums).any() else 0.0,
                "total_connectedness_index": float(
                    ((normalized_matrix.sum() - np.trace(normalized_matrix)) / max(normalized_matrix.shape[0], 1)) * 100.0
                ),
            }
        )
    return results


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _black_scholes_price(
    *,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
    option_type: str,
) -> dict[str, float]:
    if spot <= 0 or strike <= 0 or maturity <= 0 or volatility <= 0:
        raise ValueError("Black-Scholes requires strictly positive spot, strike, maturity, and volatility.")
    sqrt_t = math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility**2) * maturity) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    if option_type == "put":
        price = strike * math.exp(-rate * maturity) * _normal_cdf(-d2) - spot * _normal_cdf(-d1)
        delta = _normal_cdf(d1) - 1.0
    else:
        price = spot * _normal_cdf(d1) - strike * math.exp(-rate * maturity) * _normal_cdf(d2)
        delta = _normal_cdf(d1)
    gamma = math.exp(-(d1**2) / 2.0) / (spot * volatility * sqrt_t * math.sqrt(2.0 * math.pi))
    return {"price": price, "delta": delta, "gamma": gamma, "d1": d1, "d2": d2}


def _binomial_option_price(
    *,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
    steps: int,
    option_type: str,
) -> float:
    if steps < 1:
        raise ValueError("Binomial option pricing requires at least one step.")
    if spot <= 0 or strike <= 0 or maturity <= 0 or volatility <= 0:
        raise ValueError("Binomial option pricing requires strictly positive spot, strike, maturity, and volatility.")
    dt = maturity / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    discount = math.exp(-rate * dt)
    probability = (math.exp(rate * dt) - down) / (up - down)
    if probability <= 0 or probability >= 1:
        raise ValueError("Invalid binomial probability. Check rate, volatility, maturity, and step count.")
    terminal = []
    for step in range(steps + 1):
        stock_price = spot * (up ** (steps - step)) * (down**step)
        if option_type == "put":
            payoff = max(strike - stock_price, 0.0)
        else:
            payoff = max(stock_price - strike, 0.0)
        terminal.append(payoff)
    values = terminal
    for level in range(steps, 0, -1):
        values = [
            discount * (probability * values[index] + (1 - probability) * values[index + 1])
            for index in range(level)
        ]
    return float(values[0])


def _risk_parity_weights(covariance: np.ndarray, *, iterations: int = 600, tolerance: float = 1e-7) -> np.ndarray:
    count = covariance.shape[0]
    weights = np.full(count, 1.0 / count)
    for _ in range(iterations):
        portfolio_variance = float(weights @ covariance @ weights)
        if portfolio_variance <= 0:
            break
        marginal = covariance @ weights
        risk_contrib = weights * marginal / math.sqrt(portfolio_variance)
        target = risk_contrib.sum() / count
        if np.max(np.abs(risk_contrib - target)) <= tolerance:
            break
        safe_rc = np.where(np.abs(risk_contrib) < 1e-12, 1e-12, risk_contrib)
        weights = weights * target / safe_rc
        weights = np.clip(weights, 1e-8, None)
        weights = weights / weights.sum()
    return weights


def clean_dataset_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, meta = _load_analysis_frame(settings, asset, drop_duplicates=True)
    summary = {
        "original_rows": int(meta["rows_after_standardization"] + meta["duplicate_rows_detected"]),
        "cleaned_rows": int(len(frame)),
        "dropped_rows": int(meta["duplicate_rows_detected"]),
        "columns_before": list(meta["source_columns"].values()),
        "columns_after": list(frame.columns),
        "missing_by_column": {column: int(value) for column, value in frame.isna().sum().to_dict().items()},
    }

    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    cleaned_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-cleaned.csv",
        content=csv_bytes,
        content_type="text/csv",
        description=f"Cleaned derivative of {asset.title}",
    )
    cleaned_asset.metadata_json = {
        **cleaned_asset.metadata_json,
        "cleaning_summary": summary,
        "source_asset_id": asset.id,
    }
    db.flush()
    return {"asset": serialize_asset(cleaned_asset), "summary": summary}


def run_ols_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str],
    robust_covariance: bool = True,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)

    required_columns = [dependent, *independents]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = _serialize_model_frame(frame, required_columns)
    fitted = _fit_ols(sample, dependent, independents, robust_covariance=robust_covariance)
    summary_lines = [
        f"OLS run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Regressors: {', '.join(independents)}.",
        f"Observations used: {int(fitted.nobs)}.",
        f"R-squared: {float(fitted.rsquared):.4f}.",
    ]
    payload = _model_result_payload(
        model_type="ols",
        model_label="Ordinary Least Squares",
        asset=asset,
        dependent=dependent,
        regressors=independents,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "residual_sum_squares": float(np.sum(np.square(fitted.resid))),
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent or regressor values are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"OLS summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["ols", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_did_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    treatment_column: str,
    post_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, treatment_column, post_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = pd.to_numeric(sample[dependent], errors="coerce")
    sample[treatment_column] = _coerce_binary_series(sample[treatment_column])
    sample[post_column] = _coerce_binary_series(sample[post_column])
    for column in controls:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    sample = sample.dropna().copy()
    sample["did_interaction"] = sample[treatment_column] * sample[post_column]

    regressors = [treatment_column, post_column, "did_interaction", *controls]
    fitted = _fit_ols(sample, dependent, regressors, robust_covariance=robust_covariance)
    did_effect = float(fitted.params.get("did_interaction", np.nan))
    cell_means = []
    grouped = sample.groupby([treatment_column, post_column])[dependent].agg(["mean", "count"]).reset_index()
    for _, row in grouped.iterrows():
        cell_means.append(
            {
                "treatment": int(row[treatment_column]),
                "post": int(row[post_column]),
                "mean": float(row["mean"]),
                "count": int(row["count"]),
            }
        )

    summary_lines = [
        f"DID run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Treatment indicator: {treatment_column}.",
        f"Post indicator: {post_column}.",
        f"Estimated DID effect: {did_effect:.4f}.",
    ]
    payload = _model_result_payload(
        model_type="did",
        model_label="Difference-in-Differences",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "treatment_column": treatment_column,
            "post_column": post_column,
            "did_effect": did_effect,
            "cell_means": cell_means,
            "audit_trail": {
                "derived_columns": ["did_interaction"],
                "filters": ["Rows with missing outcome, treatment, post indicator, or selected controls are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"DID summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["did", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_gravity_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    flow_column: str,
    origin_mass_column: str,
    destination_mass_column: str,
    distance_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [flow_column, origin_mass_column, destination_mass_column, distance_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")
    sample = sample.dropna().copy()
    positive_mask = (
        (sample[flow_column] >= 0)
        & (sample[origin_mass_column] > 0)
        & (sample[destination_mass_column] > 0)
        & (sample[distance_column] > 0)
    )
    dropped_nonpositive = int((~positive_mask).sum())
    sample = sample.loc[positive_mask].copy()
    if len(sample) < max(12, len(controls) + 5):
        raise ValueError("Not enough positive, complete observations for the gravity model.")

    sample["ln_flow"] = np.log1p(sample[flow_column])
    sample["ln_origin_mass"] = np.log(sample[origin_mass_column])
    sample["ln_destination_mass"] = np.log(sample[destination_mass_column])
    sample["ln_distance"] = np.log(sample[distance_column])

    regressors = ["ln_origin_mass", "ln_destination_mass", "ln_distance", *controls]
    fitted = _fit_ols(sample, "ln_flow", regressors, robust_covariance=robust_covariance)
    summary_lines = [
        f"Gravity model run on {asset.title}.",
        f"Flow variable: {flow_column}.",
        f"Mass variables: {origin_mass_column}, {destination_mass_column}.",
        f"Distance variable: {distance_column}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="gravity",
        model_label="Gravity Model",
        asset=asset,
        dependent="ln_flow",
        regressors=regressors,
        sample=sample[["ln_flow", *regressors]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "flow_column": flow_column,
            "origin_mass_column": origin_mass_column,
            "destination_mass_column": destination_mass_column,
            "distance_column": distance_column,
            "dropped_nonpositive_rows": dropped_nonpositive,
            "audit_trail": {
                "derived_columns": ["ln_flow", "ln_origin_mass", "ln_destination_mass", "ln_distance"],
                "filters": [
                    "Rows with missing flow, mass, distance, or selected controls are dropped.",
                    "Rows with negative flow or nonpositive mass/distance are excluded before log transforms.",
                ],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Gravity model summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["gravity", "dataset", "economics"],
        metadata=payload,
    )
    return payload


def run_ppml_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = _serialize_model_frame(frame, required_columns)
    fitted = _fit_ppml(sample, dependent, regressors, robust_covariance=robust_covariance)
    summary_lines = [
        f"PPML run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="ppml",
        model_label="PPML",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "mean_prediction": float(np.mean(fitted.predict())) if len(sample) else None,
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent or regressor values are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"PPML summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["ppml", "poisson", "econometrics"],
        metadata=payload,
    )
    return payload


def _event_period_label(period: int) -> str:
    if period < 0:
        return f"lead_{abs(period)}"
    if period > 0:
        return f"lag_{period}"
    return "event_0"


def run_event_study_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    treatment_column: str,
    event_time_column: str,
    controls: list[str] | None = None,
    entity_column: str = "",
    time_column: str = "",
    include_time_effects: bool = False,
    lead_window: int = 4,
    lag_window: int = 4,
    omitted_period: int = -1,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, treatment_column, event_time_column, *controls]
    if entity_column:
        required_columns.append(entity_column)
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample[treatment_column] = _coerce_binary_series(sample[treatment_column])
    sample[event_time_column] = _coerce_numeric_series(sample[event_time_column])
    for column in controls:
        sample[column] = _coerce_numeric_series(sample[column])
    if entity_column:
        sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()
    sample[event_time_column] = sample[event_time_column].round().astype(int)

    if lead_window < 0 or lag_window < 0:
        raise ValueError("Lead and lag windows must be nonnegative.")
    periods = list(range(-int(lead_window), int(lag_window) + 1))
    if omitted_period not in periods:
        raise ValueError("Omitted period must lie within the requested lead/lag window.")

    event_columns: list[str] = []
    dynamic_effects: list[dict[str, Any]] = []
    for period in periods:
        if period == omitted_period:
            continue
        column_name = f"event_{_event_period_label(period)}"
        sample[column_name] = (
            (sample[treatment_column] == 1.0) & (sample[event_time_column] == period)
        ).astype(float)
        if sample[column_name].sum() <= 0:
            sample = sample.drop(columns=[column_name])
            continue
        event_columns.append(column_name)
        dynamic_effects.append({"period": period, "column": column_name})

    if not event_columns:
        raise ValueError("No event-time cells are available in the selected window.")

    regressors = [*event_columns, *controls]
    fe_labels: list[str] = []
    derived_columns = event_columns.copy()
    if entity_column:
        fe_dummies, fe_labels = _build_fe_dummies(
            sample,
            entity_column=entity_column,
            time_column=time_column,
            include_time_effects=include_time_effects,
        )
        if not fe_dummies.empty:
            sample = pd.concat([sample, fe_dummies], axis=1)
            regressors.extend(list(fe_dummies.columns))
            derived_columns.extend(list(fe_dummies.columns))

    fitted = _fit_ols(sample[[dependent, *regressors]].copy(), dependent, regressors, robust_covariance=robust_covariance)
    effect_map = {row["column"]: row["period"] for row in dynamic_effects}
    for coefficient in _serialize_coefficients(fitted):
        period = effect_map.get(coefficient["term"])
        if period is not None:
            coefficient["period"] = period

    summary_lines = [
        f"Event study run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Treatment indicator: {treatment_column}.",
        f"Relative event-time column: {event_time_column}.",
        f"Window: [{-int(lead_window)}, {int(lag_window)}], omitted period {int(omitted_period)}.",
    ]
    dynamic_rows = [
        {
            "period": effect_map.get(item["term"]),
            "term": item["term"],
            "coefficient": item["coefficient"],
            "std_error": item["std_error"],
            "p_value": item["p_value"],
            "confidence_low": (
                float(item["coefficient"]) - 1.96 * float(item["std_error"])
                if item["coefficient"] is not None and item["std_error"] is not None
                else None
            ),
            "confidence_high": (
                float(item["coefficient"]) + 1.96 * float(item["std_error"])
                if item["coefficient"] is not None and item["std_error"] is not None
                else None
            ),
            "significance_stars": (
                "***"
                if item["p_value"] is not None and float(item["p_value"]) < 0.01
                else "**"
                if item["p_value"] is not None and float(item["p_value"]) < 0.05
                else "*"
                if item["p_value"] is not None and float(item["p_value"]) < 0.1
                else ""
            ),
        }
        for item in _serialize_coefficients(fitted)
        if item["term"] in effect_map
    ]
    dynamic_rows = sorted(dynamic_rows, key=lambda item: int(item["period"]))
    table_rows = [
        {
            "period": int(item["period"]),
            "term": item["term"],
            "coefficient": float(item["coefficient"]) if item["coefficient"] is not None else None,
            "std_error": float(item["std_error"]) if item["std_error"] is not None else None,
            "p_value": float(item["p_value"]) if item["p_value"] is not None else None,
            "confidence_low": float(item["confidence_low"]) if item["confidence_low"] is not None else None,
            "confidence_high": float(item["confidence_high"]) if item["confidence_high"] is not None else None,
            "significance_stars": item["significance_stars"],
        }
        for item in dynamic_rows
    ]
    window_rows = [
        {
            "window_start": -int(lead_window),
            "window_end": int(lag_window),
            "omitted_period": int(omitted_period),
            "periods_estimated": len(table_rows),
            "treated_observations": int(sample[treatment_column].sum()),
            "total_observations": int(len(sample)),
        }
    ]
    if dynamic_rows:
        periods_plot = np.array([int(item["period"]) for item in dynamic_rows], dtype=int)
        coefficients_plot = np.array([float(item["coefficient"]) for item in dynamic_rows], dtype=float)
        standard_errors = np.array([float(item["std_error"]) if item["std_error"] is not None else 0.0 for item in dynamic_rows], dtype=float)
        figure, axis = _pyplot().subplots(figsize=(9.4, 5.8), dpi=160)
        axis.errorbar(
            periods_plot,
            coefficients_plot,
            yerr=1.96 * standard_errors,
            fmt="o-",
            color="#0b5f45",
            ecolor="#84a98c",
            capsize=4,
            linewidth=1.8,
        )
        axis.axhline(0.0, color="#7c4d1c", linewidth=1.0, linestyle="--")
        axis.axvline(int(omitted_period), color="#c08c52", linewidth=1.0, linestyle=":")
        axis.set_title("Event-study dynamic treatment effects")
        axis.set_xlabel("Relative period")
        axis.set_ylabel("Coefficient")
        axis.grid(alpha=0.18, linestyle="--")
        figure.tight_layout()
        figure_asset = _save_model_figure_asset(
            settings,
            db,
            user=user,
            workspace=workspace,
            source_asset=asset,
            figure=figure,
            filename_slug="event-study",
            title="Event-study coefficient plot",
            summary="Dynamic treatment-effect plot with 95% confidence bands from the event-study regression.",
        )
    else:
        figure_asset = None
    payload = _model_result_payload(
        model_type="event_study",
        model_label="Event Study",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, treatment_column, event_time_column, *controls]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "treatment_column": treatment_column,
            "event_time_column": event_time_column,
            "control_columns": controls,
            "lead_window": int(lead_window),
            "lag_window": int(lag_window),
            "omitted_period": int(omitted_period),
            "dynamic_effects": dynamic_rows,
            "tables": {
                "event_study_table": table_rows,
                "event_study_window": window_rows,
            },
            "figures": [figure_asset] if figure_asset else [],
            "audit_trail": {
                "derived_columns": derived_columns,
                "filters": [
                    "Rows with missing outcome, treatment, event-time, or selected controls are dropped.",
                    f"Event window restricted to periods between {-int(lead_window)} and {int(lag_window)}.",
                ],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Event study summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["event_study", "dynamic_did", "econometrics"],
        metadata=payload,
    )
    return payload


def run_rdd_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    running_column: str,
    controls: list[str] | None = None,
    cutoff: float = 0.0,
    bandwidth: float = 0.0,
    polynomial_order: int = 1,
    treat_above_cutoff: bool = True,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    controls = [column for column in (controls or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, running_column, *controls]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if polynomial_order < 1 or polynomial_order > 3:
        raise ValueError("RDD polynomial order must be between 1 and 3.")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample[running_column] = _coerce_numeric_series(sample[running_column])
    for column in controls:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    sample["running_centered"] = sample[running_column] - float(cutoff)
    if bandwidth and bandwidth > 0:
        sample = sample.loc[sample["running_centered"].abs() <= float(bandwidth)].copy()
    if sample.empty:
        raise ValueError("RDD bandwidth leaves no usable observations.")

    if treat_above_cutoff:
        sample["rdd_treatment"] = (sample["running_centered"] >= 0).astype(float)
    else:
        sample["rdd_treatment"] = (sample["running_centered"] <= 0).astype(float)

    regressors = ["rdd_treatment"]
    derived_columns = ["running_centered", "rdd_treatment"]
    for power in range(1, int(polynomial_order) + 1):
        base_name = "running_centered" if power == 1 else f"running_centered_pow_{power}"
        if power > 1:
            sample[base_name] = sample["running_centered"] ** power
            derived_columns.append(base_name)
        regressors.append(base_name)
        interaction_name = f"rdd_treatment_x_{base_name}"
        sample[interaction_name] = sample["rdd_treatment"] * sample[base_name]
        regressors.append(interaction_name)
        derived_columns.append(interaction_name)
    regressors.extend(controls)

    fitted = _fit_ols(sample[[dependent, *regressors]].copy(), dependent, regressors, robust_covariance=robust_covariance)
    local_effect = float(fitted.params.get("rdd_treatment", np.nan))
    summary_lines = [
        f"RDD run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Running variable: {running_column}.",
        f"Cutoff: {float(cutoff):.4f}.",
        f"Local treatment effect at cutoff: {local_effect:.4f}.",
    ]
    grid = np.linspace(float(sample["running_centered"].min()), float(sample["running_centered"].max()), 120)
    left_grid = grid[grid < 0]
    right_grid = grid[grid >= 0]

    def predict_side(grid_values: np.ndarray, treated_value: float) -> np.ndarray:
        if grid_values.size == 0:
            return np.array([], dtype=float)
        design = pd.DataFrame({"const": np.ones(len(grid_values)), "rdd_treatment": treated_value}, index=np.arange(len(grid_values)))
        for power in range(1, int(polynomial_order) + 1):
            base_name = "running_centered" if power == 1 else f"running_centered_pow_{power}"
            base_values = grid_values if power == 1 else grid_values**power
            design[base_name] = base_values
            design[f"rdd_treatment_x_{base_name}"] = treated_value * base_values
        for column in controls:
            design[column] = float(sample[column].mean())
        design = design.reindex(columns=fitted.model.exog_names, fill_value=0.0)
        return np.asarray(design.to_numpy() @ np.asarray(fitted.params), dtype=float)

    figure, axis = _pyplot().subplots(figsize=(9.4, 5.8), dpi=160)
    scatter_frame = sample[[dependent, "running_centered", "rdd_treatment"]].copy()
    axis.scatter(
        scatter_frame.loc[scatter_frame["rdd_treatment"] == 0, "running_centered"],
        scatter_frame.loc[scatter_frame["rdd_treatment"] == 0, dependent],
        alpha=0.45,
        s=18,
        color="#0b5f45",
        label="Below cutoff",
    )
    axis.scatter(
        scatter_frame.loc[scatter_frame["rdd_treatment"] == 1, "running_centered"],
        scatter_frame.loc[scatter_frame["rdd_treatment"] == 1, dependent],
        alpha=0.45,
        s=18,
        color="#d97706",
        label="Above cutoff",
    )
    if left_grid.size:
        axis.plot(left_grid, predict_side(left_grid, 0.0), color="#14532d", linewidth=2.0)
    if right_grid.size:
        axis.plot(right_grid, predict_side(right_grid, 1.0), color="#b45309", linewidth=2.0)
    axis.axvline(0.0, color="#7c4d1c", linewidth=1.0, linestyle="--")
    axis.set_title("RDD fit around the cutoff")
    axis.set_xlabel(f"{running_column} - cutoff")
    axis.set_ylabel(dependent)
    axis.legend(loc="best")
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="rdd-fit",
        title="RDD scatter and fitted lines",
        summary="RDD plot with separate fitted curves on each side of the cutoff.",
    )

    def _fit_rdd_variant(local_bandwidth: float, local_polynomial_order: int) -> dict[str, Any] | None:
        local_sample = frame[required_columns].copy()
        local_sample[dependent] = _coerce_numeric_series(local_sample[dependent])
        local_sample[running_column] = _coerce_numeric_series(local_sample[running_column])
        for column in controls:
            local_sample[column] = _coerce_numeric_series(local_sample[column])
        local_sample = local_sample.dropna().copy()
        local_sample["running_centered"] = local_sample[running_column] - float(cutoff)
        if local_bandwidth > 0:
            local_sample = local_sample.loc[local_sample["running_centered"].abs() <= float(local_bandwidth)].copy()
        if len(local_sample) < max(12, 4 * local_polynomial_order):
            return None
        if treat_above_cutoff:
            local_sample["rdd_treatment"] = (local_sample["running_centered"] >= 0).astype(float)
        else:
            local_sample["rdd_treatment"] = (local_sample["running_centered"] <= 0).astype(float)
        local_regressors = ["rdd_treatment"]
        for power in range(1, int(local_polynomial_order) + 1):
            base_name = "running_centered" if power == 1 else f"running_centered_pow_{power}"
            if power > 1:
                local_sample[base_name] = local_sample["running_centered"] ** power
            local_regressors.append(base_name)
            interaction_name = f"rdd_treatment_x_{base_name}"
            local_sample[interaction_name] = local_sample["rdd_treatment"] * local_sample[base_name]
            local_regressors.append(interaction_name)
        local_regressors.extend(controls)
        try:
            local_fit = _fit_ols(
                local_sample[[dependent, *local_regressors]].copy(),
                dependent,
                local_regressors,
                robust_covariance=robust_covariance,
            )
        except Exception:
            return None
        return {
            "bandwidth": float(local_bandwidth),
            "polynomial_order": int(local_polynomial_order),
            "observations": int(len(local_sample)),
            "local_effect": float(local_fit.params.get("rdd_treatment", np.nan)),
            "std_error": _safe_float(local_fit.bse.get("rdd_treatment")) if hasattr(local_fit, "bse") else None,
            "p_value": _safe_float(local_fit.pvalues.get("rdd_treatment")) if hasattr(local_fit, "pvalues") else None,
        }

    candidate_bandwidths = []
    if bandwidth and bandwidth > 0:
        candidate_bandwidths = [max(float(bandwidth) * 0.75, 0.05), float(bandwidth), float(bandwidth) * 1.25]
    else:
        centered_abs = sample["running_centered"].abs()
        median_abs = float(centered_abs.median()) if len(centered_abs) else 0.0
        fallback = max(median_abs, 0.5)
        candidate_bandwidths = [max(fallback * 0.75, 0.05), fallback, fallback * 1.25]
    sensitivity_rows: list[dict[str, Any]] = []
    seen_specs: set[tuple[float, int]] = set()
    for bw in candidate_bandwidths:
        for order in sorted({max(1, int(polynomial_order) - 1), int(polynomial_order), min(3, int(polynomial_order) + 1)}):
            key = (round(float(bw), 6), int(order))
            if key in seen_specs:
                continue
            seen_specs.add(key)
            candidate = _fit_rdd_variant(float(bw), int(order))
            if candidate is not None:
                sensitivity_rows.append(candidate)
    if not sensitivity_rows:
        sensitivity_rows.append(
            {
                "bandwidth": float(bandwidth) if bandwidth and bandwidth > 0 else None,
                "polynomial_order": int(polynomial_order),
                "observations": int(len(sample)),
                "local_effect": local_effect,
                "std_error": _safe_float(fitted.bse.get("rdd_treatment")) if hasattr(fitted, "bse") else None,
                "p_value": _safe_float(fitted.pvalues.get("rdd_treatment")) if hasattr(fitted, "pvalues") else None,
            }
        )
    payload = _model_result_payload(
        model_type="rdd",
        model_label="RDD",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, running_column, *controls]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "running_column": running_column,
            "cutoff": float(cutoff),
            "bandwidth": float(bandwidth),
            "polynomial_order": int(polynomial_order),
            "treat_above_cutoff": bool(treat_above_cutoff),
            "local_effect": local_effect,
            "tables": {
                "bandwidth_sensitivity": sensitivity_rows,
                "rdd_design_audit": [
                    {
                        "cutoff": float(cutoff),
                        "bandwidth": float(bandwidth),
                        "polynomial_order": int(polynomial_order),
                        "treat_above_cutoff": bool(treat_above_cutoff),
                        "observations": int(len(sample)),
                    }
                ],
            },
            "figures": [figure_asset],
            "audit_trail": {
                "derived_columns": derived_columns,
                "filters": [
                    "Rows with missing outcome, running variable, or selected controls are dropped.",
                    f"Bandwidth filter: {float(bandwidth)}." if bandwidth and bandwidth > 0 else "No bandwidth filter applied.",
                ],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"RDD summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["rdd", "causal_inference", "econometrics"],
        metadata=payload,
    )
    return payload


def run_panel_iv_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    endogenous_column: str,
    instrument_columns: list[str] | None = None,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    exogenous = [column for column in [*(independents or []), *(controls or [])] if column]
    instruments = [column for column in (instrument_columns or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, endogenous_column, entity_column, *exogenous, *instruments]
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    numeric_columns = [dependent, endogenous_column, *exogenous, *instruments]
    for column in numeric_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()

    fe_dummies, fe_labels = _build_fe_dummies(
        sample,
        entity_column=entity_column,
        time_column=time_column,
        include_time_effects=include_time_effects,
    )
    if not fe_dummies.empty:
        sample = pd.concat([sample, fe_dummies], axis=1)
    expanded_exogenous = [*exogenous, *list(fe_dummies.columns)]
    fitted, covariance_type = _fit_iv_2sls(
        sample,
        dependent,
        exogenous=expanded_exogenous,
        endogenous=endogenous_column,
        instruments=instruments,
        robust_covariance=robust_covariance,
    )
    summary_lines = [
        f"Panel IV run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Endogenous regressor: {endogenous_column}.",
        f"Instruments: {', '.join(instruments)}.",
        f"Fixed effects: {', '.join(fe_labels)}.",
    ]
    payload = _model_result_payload(
        model_type="panel_iv",
        model_label="Panel IV",
        asset=asset,
        dependent=dependent,
        regressors=[*expanded_exogenous, endogenous_column],
        sample=sample[[dependent, endogenous_column, *exogenous, *instruments, entity_column] + ([time_column] if include_time_effects and time_column else [])].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "endogenous_column": endogenous_column,
            "instrument_columns": instruments,
            "exogenous_columns": exogenous,
            "entity_column": entity_column,
            "time_column": time_column if include_time_effects else "",
            "include_time_effects": include_time_effects,
            "entity_count": int(sample[entity_column].nunique()),
            "time_count": int(sample[time_column].nunique()) if include_time_effects and time_column else 0,
            "covariance_type": covariance_type,
            "covariance_note": "Panel IV uses conventional covariance when robust covariance is unavailable in the current backend."
            if robust_covariance and covariance_type != "HC1"
            else "",
            "audit_trail": {
                "derived_columns": list(fe_dummies.columns),
                "filters": [
                    "Rows with missing dependent, endogenous regressor, instrument, or selected controls are dropped.",
                ],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Panel IV summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["panel_iv", "instrumental_variables", "econometrics"],
        metadata=payload,
    )
    return payload


def run_arima_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    time_column: str = "",
    arima_order: tuple[int, int, int] = (1, 0, 0),
    forecast_steps: int = 5,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [dependent] + ([time_column] if time_column else [])
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    sample = sample.dropna(subset=[dependent]).copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    p, d, q = arima_order
    if len(sample) < max(20, p + d + q + 8):
        raise ValueError("Not enough observations for the selected ARIMA order.")
    fitted = ARIMA(sample[dependent], order=(p, d, q)).fit()
    forecast = fitted.forecast(steps=int(forecast_steps))
    x_actual = sample[time_column] if time_column else np.arange(1, len(sample) + 1)
    x_forecast = np.arange(len(sample) + 1, len(sample) + int(forecast_steps) + 1)
    figure, axis = _pyplot().subplots(figsize=(10.2, 5.8), dpi=160)
    axis.plot(x_actual, sample[dependent], color="#0b5f45", linewidth=1.6, label="Observed")
    axis.plot(x_forecast, np.asarray(forecast, dtype=float), color="#d97706", linewidth=1.8, marker="o", label="Forecast")
    axis.set_title(f"ARIMA({p}, {d}, {q}) forecast")
    axis.set_xlabel(time_column or "Observation")
    axis.set_ylabel(dependent)
    axis.legend(loc="best")
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="arima-forecast",
        title="ARIMA fitted series and forecast",
        summary=f"Observed {dependent} path with the ARIMA({p}, {d}, {q}) forecast extension.",
    )
    summary_lines = [
        f"ARIMA({p}, {d}, {q}) run on {asset.title}.",
        f"Target series: {dependent}.",
        f"Forecast horizon: {int(forecast_steps)} step(s).",
    ]
    return _model_result_payload(
        model_type="arima",
        model_label="ARIMA Forecast",
        asset=asset,
        dependent=dependent,
        regressors=[f"ARIMA({p},{d},{q})"],
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "model_family": "time_series_finance",
            "time_column": time_column,
            "forecast": [{"step": index + 1, "forecast": float(value)} for index, value in enumerate(np.asarray(forecast).tolist())],
            "figures": [figure_asset],
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing target values are dropped.", "Series is sorted by the selected time column before estimation." if time_column else "Series order follows the uploaded sample order."],
            },
        },
    )


def run_var_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    lags: int = 1,
    forecast_steps: int = 5,
) -> dict[str, Any]:
    series_columns = [column for column in series_columns if column]
    if len(series_columns) < 2:
        raise ValueError("VAR requires at least two series columns.")
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [*series_columns, *([time_column] if time_column else [])]
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in series_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    if len(sample) < max(18, len(series_columns) * (lags + 2)):
        raise ValueError("Not enough observations for VAR estimation.")
    fitted = VAR(sample[series_columns]).fit(maxlags=int(lags), trend="c")
    lag_order = int(fitted.k_ar)
    forecast_values = fitted.forecast(sample[series_columns].values[-lag_order:], steps=int(forecast_steps))
    coefficients: list[dict[str, Any]] = []
    for equation in fitted.names:
        for term in fitted.params.index:
            coefficients.append(
                {
                    "equation": equation,
                    "term": term,
                    "coefficient": float(fitted.params.loc[term, equation]),
                    "std_error": float(fitted.stderr.loc[term, equation]) if term in fitted.stderr.index else None,
                    "p_value": float(fitted.pvalues.loc[term, equation]) if term in fitted.pvalues.index else None,
                }
            )
    forecast_rows = [
        {"step": step, **{series_columns[index]: float(value) for index, value in enumerate(row)}}
        for step, row in enumerate(forecast_values, start=1)
    ]
    figure, axes = _pyplot().subplots(len(series_columns), 1, figsize=(10.8, 3.0 * len(series_columns)), dpi=160, sharex=False)
    if len(series_columns) == 1:
        axes = [axes]
    actual_x = sample[time_column] if time_column else np.arange(1, len(sample) + 1)
    forecast_x = np.arange(len(sample) + 1, len(sample) + int(forecast_steps) + 1)
    for axis, series_name in zip(axes, series_columns):
        axis.plot(actual_x, sample[series_name], color="#0b5f45", linewidth=1.4, label="Observed")
        axis.plot(forecast_x, forecast_values[:, series_columns.index(series_name)], color="#d97706", linewidth=1.6, marker="o", label="Forecast")
        axis.set_title(series_name)
        axis.grid(alpha=0.18, linestyle="--")
        axis.legend(loc="best")
    axes[-1].set_xlabel(time_column or "Observation")
    figure.suptitle("VAR forecast paths", y=1.01)
    figure.tight_layout()
    forecast_figure = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="var-forecast",
        title="VAR forecast paths",
        summary="Observed and forecast paths for each endogenous series from the fitted VAR.",
    )
    summary_lines = [
        f"VAR({lag_order}) run on {asset.title}.",
        f"Series: {', '.join(series_columns)}.",
        f"Forecast horizon: {int(forecast_steps)} step(s).",
    ]
    return _nonregression_result_payload(
        model_type="var",
        model_label="Vector Autoregression",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), *series_columns]].copy(),
        narrative_lines=summary_lines,
        specification={
            "model_type": "var",
            "model_family": "time_series_finance",
            "series_columns": series_columns,
            "time_column": time_column,
            "lags": lag_order,
            "forecast_steps": int(forecast_steps),
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), *series_columns],
            "manual_checklist": [
                "Download the sample asset and sort it by the listed time_column if one is provided.",
                "Estimate a VAR with the same lag order on the listed series columns.",
                "Compare coefficient blocks and forecast rows equation by equation.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        tables={"coefficients": coefficients, "forecast": forecast_rows},
        metrics={"lag_order": lag_order, "aic": float(fitted.aic), "bic": float(fitted.bic)},
        extra={"figures": [forecast_figure]},
    )


def run_arch_garch_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    dependent: str,
    time_column: str = "",
    p: int = 1,
    q: int = 1,
    forecast_steps: int = 5,
) -> dict[str, Any]:
    normalized_model = model_type.strip().lower()
    if normalized_model not in {"arch", "garch"}:
        raise ValueError("Unsupported conditional volatility model.")
    asset, sample = _prepare_time_series_sample(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        series_columns=[dependent],
        time_column=time_column,
        min_rows=max(60, 12 * (int(p) + int(q) + 1)),
    )
    series = sample[dependent].astype(float)
    if float(series.std()) <= 0:
        raise ValueError("Conditional volatility models require a series with non-zero variation.")
    if normalized_model == "arch":
        fitted = arch_model(series, mean="Constant", vol="ARCH", p=max(1, int(p)), dist="normal", rescale=False).fit(disp="off")
        label = "ARCH"
        q = 0
    else:
        fitted = arch_model(
            series,
            mean="Constant",
            vol="GARCH",
            p=max(1, int(p)),
            q=max(1, int(q)),
            dist="normal",
            rescale=False,
        ).fit(disp="off")
        label = "GARCH"
    conditional_vol = np.asarray(fitted.conditional_volatility, dtype=float)
    sample = sample.copy()
    sample["conditional_volatility"] = conditional_vol
    forecast = fitted.forecast(horizon=max(1, int(forecast_steps)), reindex=False)
    variance_path = np.asarray(forecast.variance.values[-1], dtype=float)
    volatility_forecast = np.sqrt(np.maximum(variance_path, 0.0))
    alpha_terms = [float(value) for key, value in fitted.params.items() if str(key).lower().startswith("alpha")]
    beta_terms = [float(value) for key, value in fitted.params.items() if str(key).lower().startswith("beta")]
    persistence = float(sum(alpha_terms) + sum(beta_terms))

    x_values = sample[time_column] if time_column else np.arange(1, len(sample) + 1)
    figure, axes = _pyplot().subplots(2, 1, figsize=(10.5, 7.2), dpi=160, sharex=False)
    axes[0].plot(x_values, sample[dependent], color="#0b5f45", linewidth=1.5)
    axes[0].set_title(f"{label} input series")
    axes[0].set_ylabel(dependent)
    axes[0].grid(alpha=0.18, linestyle="--")
    axes[1].plot(x_values, sample["conditional_volatility"], color="#d97706", linewidth=1.6)
    axes[1].set_title("Estimated conditional volatility")
    axes[1].set_ylabel("sigma_t")
    axes[1].set_xlabel(time_column or "Observation")
    axes[1].grid(alpha=0.18, linestyle="--")
    figure.tight_layout()
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug=f"{normalized_model}-volatility-path",
        title=f"{label} volatility path",
        summary=f"{label} conditional volatility path estimated from {dependent}.",
    )
    forecast_figure, forecast_axis = _pyplot().subplots(figsize=(9.2, 5.4), dpi=160)
    forecast_steps_axis = np.arange(1, len(volatility_forecast) + 1)
    forecast_axis.plot(forecast_steps_axis, volatility_forecast, marker="o", linewidth=1.8, color="#7c3aed")
    forecast_axis.set_title(f"{label} forecast volatility path")
    forecast_axis.set_xlabel("Forecast horizon")
    forecast_axis.set_ylabel("Forecast volatility")
    forecast_axis.grid(alpha=0.18, linestyle="--")
    forecast_figure.tight_layout()
    forecast_figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=forecast_figure,
        filename_slug=f"{normalized_model}-forecast-volatility",
        title=f"{label} forecast volatility",
        summary=f"{label} multi-step forecast volatility path.",
    )
    parameter_table = _parameter_table(
        fitted.params,
        std_errors=getattr(fitted, "std_err", None),
        tvalues=getattr(fitted, "tvalues", None),
        pvalues=getattr(fitted, "pvalues", None),
    )
    return _nonregression_result_payload(
        model_type=normalized_model,
        model_label=label,
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), dependent, "conditional_volatility"]].copy(),
        narrative_lines=[
            f"{label} run on {asset.title}.",
            f"Target series: {dependent}.",
            f"Order: p={int(p)}, q={int(q)}.",
            f"Estimated persistence: {persistence:.4f}.",
        ],
        specification={
            "model_type": normalized_model,
            "model_family": "time_series_finance",
            "return_column": dependent,
            "time_column": time_column,
            "p": int(p),
            "q": int(q),
            "forecast_steps": int(forecast_steps),
            "equation": "sigma_t^2 = omega + alpha(L) * eps_t^2 + beta(L) * sigma_{t-1}^2",
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), dependent, "conditional_volatility"],
            "manual_checklist": [
                "Download the sample asset and verify the time ordering before re-estimation.",
                "Re-estimate the same ARCH/GARCH order and compare the parameter table term by term.",
                "Check the conditional-volatility figure against the downloaded volatility path.",
            ],
            "derived_columns": ["conditional_volatility"],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        metrics={
            "log_likelihood": _safe_float(getattr(fitted, "loglikelihood", None)),
            "aic": _safe_float(getattr(fitted, "aic", None)),
            "bic": _safe_float(getattr(fitted, "bic", None)),
            "persistence": persistence,
            "latest_volatility": float(sample["conditional_volatility"].iloc[-1]),
        },
        tables={
            "parameter_table": parameter_table,
            "volatility_forecast": [
                {"step": index + 1, "forecast_volatility": float(value)}
                for index, value in enumerate(volatility_forecast.tolist())
            ],
            "volatility_preview": _frame_records(
                sample[[*([time_column] if time_column else []), dependent, "conditional_volatility"]],
                limit=12,
            ),
        },
        extra={"figures": [figure_asset, forecast_figure_asset]},
    )


def run_svar_irf_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    lags: int = 1,
    horizon: int = 12,
    impulse_column: str = "",
    response_column: str = "",
) -> dict[str, Any]:
    asset, sample = _prepare_time_series_sample(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        series_columns=series_columns,
        time_column=time_column,
        min_rows=max(48, len(series_columns) * (int(lags) + 6)),
    )
    fitted = VAR(sample[series_columns]).fit(maxlags=int(lags), trend="c")
    lag_order = int(fitted.k_ar)
    if lag_order < 1:
        raise ValueError("SVAR IRF requires at least one estimated lag.")
    impulse = impulse_column if impulse_column in series_columns else series_columns[0]
    response_targets = [response_column] if response_column in series_columns else list(series_columns)
    irf = fitted.irf(int(horizon))
    orth_irfs = np.asarray(irf.orth_irfs, dtype=float)
    cumulative_irfs = np.cumsum(orth_irfs, axis=0)
    impulse_index = series_columns.index(impulse)
    table_rows: list[dict[str, Any]] = []
    for step in range(int(horizon) + 1):
        for response_name in response_targets:
            response_index = series_columns.index(response_name)
            table_rows.append(
                {
                    "horizon": step,
                    "impulse": impulse,
                    "response": response_name,
                    "irf": float(orth_irfs[step, response_index, impulse_index]),
                    "cumulative_irf": float(cumulative_irfs[step, response_index, impulse_index]),
                }
            )
    figure, axis = _pyplot().subplots(figsize=(9.8, 6.2), dpi=160)
    steps = np.arange(int(horizon) + 1)
    for response_name in response_targets:
        response_index = series_columns.index(response_name)
        axis.plot(steps, orth_irfs[:, response_index, impulse_index], marker="o", linewidth=1.6, label=response_name)
    axis.axhline(0.0, color="#7c4d1c", linewidth=1.0, linestyle="--")
    axis.set_title(f"Recursive IRF: shock to {impulse}")
    axis.set_xlabel("Horizon")
    axis.set_ylabel("Response")
    axis.legend(loc="best")
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="svar-irf",
        title=f"SVAR IRF for {impulse}",
        summary=f"Recursive structural impulse response chart for a shock to {impulse}.",
    )
    cumulative_figure, cumulative_axis = _pyplot().subplots(figsize=(9.8, 6.2), dpi=160)
    for response_name in response_targets:
        response_index = series_columns.index(response_name)
        cumulative_axis.plot(
            steps,
            cumulative_irfs[:, response_index, impulse_index],
            marker="o",
            linewidth=1.6,
            label=response_name,
        )
    cumulative_axis.axhline(0.0, color="#7c4d1c", linewidth=1.0, linestyle="--")
    cumulative_axis.set_title(f"Cumulative recursive IRF: shock to {impulse}")
    cumulative_axis.set_xlabel("Horizon")
    cumulative_axis.set_ylabel("Cumulative response")
    cumulative_axis.legend(loc="best")
    cumulative_axis.grid(alpha=0.18, linestyle="--")
    cumulative_figure.tight_layout()
    cumulative_figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=cumulative_figure,
        filename_slug="svar-cumulative-irf",
        title=f"Cumulative SVAR IRF for {impulse}",
        summary=f"Cumulative recursive structural impulse responses for a shock to {impulse}.",
    )
    return _nonregression_result_payload(
        model_type="svar_irf",
        model_label="SVAR IRF",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), *series_columns]].copy(),
        narrative_lines=[
            f"Recursive SVAR IRF run on {asset.title}.",
            f"Cholesky ordering: {', '.join(series_columns)}.",
            f"Impulse variable: {impulse}.",
            f"Responses shown: {', '.join(response_targets)}.",
        ],
        specification={
            "model_type": "svar_irf",
            "model_family": "time_series_finance",
            "series_columns": series_columns,
            "time_column": time_column,
            "lags": lag_order,
            "horizon": int(horizon),
            "impulse_column": impulse,
            "response_column": response_column or "all",
            "identification": "Recursive (Cholesky) ordering",
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), *series_columns],
            "manual_checklist": [
                "Verify the series ordering because recursive identification depends on it.",
                "Re-estimate the VAR with the same lag order and reproduce the orthogonalized IRF externally.",
                "Compare the impulse-response table and chart horizon by horizon.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        metrics={"lag_order": lag_order, "aic": float(fitted.aic), "bic": float(fitted.bic), "horizon": int(horizon)},
        tables={"irf_table": table_rows},
        extra={"figures": [figure_asset, cumulative_figure_asset]},
    )


def run_virf_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    time_column: str = "",
    p: int = 1,
    q: int = 1,
    horizon: int = 12,
    shock_size: float = 1.0,
) -> dict[str, Any]:
    if int(p) != 1 or int(q) != 1:
        raise ValueError("VIRF currently supports a fitted GARCH(1,1) specification only.")
    asset, sample = _prepare_time_series_sample(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        series_columns=[dependent],
        time_column=time_column,
        min_rows=80,
    )
    series = sample[dependent].astype(float)
    fitted = arch_model(series, mean="Constant", vol="GARCH", p=1, q=1, dist="normal", rescale=False).fit(disp="off")
    params = fitted.params
    omega = float(params.get("omega", np.var(series)))
    alpha = float(next((value for key, value in params.items() if str(key).lower().startswith("alpha")), 0.0))
    beta = float(next((value for key, value in params.items() if str(key).lower().startswith("beta")), 0.0))
    persistence = alpha + beta
    unconditional_variance = float(np.var(series))
    if omega > 0 and persistence < 0.999:
        unconditional_variance = max(omega / max(1.0 - persistence, 1e-6), 1e-10)
    baseline_volatility = math.sqrt(unconditional_variance)
    normalized_shock = max(float(shock_size), 0.05)
    first_step_variance = omega + alpha * (normalized_shock**2) * unconditional_variance + beta * unconditional_variance
    variance_path = [max(first_step_variance, 1e-12)]
    for step in range(2, int(horizon) + 1):
        variance_path.append(unconditional_variance + (persistence ** (step - 1)) * (first_step_variance - unconditional_variance))
    response_rows = [
        {
            "horizon": step,
            "variance": float(value),
            "volatility": float(math.sqrt(max(value, 0.0))),
            "volatility_response": float(math.sqrt(max(value, 0.0)) - baseline_volatility),
        }
        for step, value in enumerate(variance_path, start=1)
    ]
    figure, axis = _pyplot().subplots(figsize=(9.4, 5.8), dpi=160)
    horizons = [row["horizon"] for row in response_rows]
    volatility_path = [row["volatility"] for row in response_rows]
    axis.plot(horizons, volatility_path, marker="o", linewidth=1.8, label="Shock path")
    axis.axhline(baseline_volatility, color="#0b5f45", linestyle="--", linewidth=1.3, label="Baseline volatility")
    axis.set_title("Volatility impulse response")
    axis.set_xlabel("Horizon")
    axis.set_ylabel("Volatility")
    axis.legend(loc="best")
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="virf",
        title="Volatility impulse response",
        summary=f"VIRF path from a {normalized_shock:.2f} sigma shock under a fitted GARCH(1,1) model.",
    )
    variance_figure, variance_axis = _pyplot().subplots(figsize=(9.4, 5.8), dpi=160)
    variance_axis.plot(
        horizons,
        [row["variance"] for row in response_rows],
        marker="o",
        linewidth=1.8,
        color="#0f766e",
        label="Variance path",
    )
    variance_axis.axhline(unconditional_variance, color="#7c4d1c", linestyle="--", linewidth=1.2, label="Baseline variance")
    variance_axis.set_title("Variance impulse response")
    variance_axis.set_xlabel("Horizon")
    variance_axis.set_ylabel("Variance")
    variance_axis.legend(loc="best")
    variance_axis.grid(alpha=0.18, linestyle="--")
    variance_figure.tight_layout()
    variance_figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=variance_figure,
        filename_slug="virf-variance",
        title="Variance impulse response",
        summary="Variance response path implied by the fitted GARCH(1,1) volatility shock.",
    )
    return _nonregression_result_payload(
        model_type="virf",
        model_label="VIRF",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), dependent]].copy(),
        narrative_lines=[
            f"VIRF run on {asset.title}.",
            f"Series: {dependent}.",
            f"Fitted GARCH(1,1) persistence: {persistence:.4f}.",
            f"Shock size: {normalized_shock:.2f} sigma.",
        ],
        specification={
            "model_type": "virf",
            "model_family": "time_series_finance",
            "return_column": dependent,
            "time_column": time_column,
            "p": 1,
            "q": 1,
            "horizon": int(horizon),
            "shock_size": normalized_shock,
            "equation": "E[h_{t+s}|shock] for a fitted GARCH(1,1) process",
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), dependent],
            "manual_checklist": [
                "Re-estimate the same GARCH(1,1) model and record omega, alpha, and beta.",
                "Rebuild the VIRF path from the documented shock_size and persistence formula.",
                "Compare the volatility-response table and the chart horizon by horizon.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        metrics={
            "omega": omega,
            "alpha": alpha,
            "beta": beta,
            "persistence": persistence,
            "baseline_volatility": baseline_volatility,
            "shock_size": normalized_shock,
        },
        tables={"parameter_table": _parameter_table(params, std_errors=getattr(fitted, "std_err", None)), "virf_path": response_rows},
        extra={"figures": [figure_asset, variance_figure_asset]},
    )


def run_dy_connectedness_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    lags: int = 1,
    horizon: int = 10,
) -> dict[str, Any]:
    asset, sample = _prepare_time_series_sample(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        series_columns=series_columns,
        time_column=time_column,
        min_rows=max(48, len(series_columns) * (int(lags) + 6)),
    )
    fitted = VAR(sample[series_columns]).fit(maxlags=int(lags), trend="c")
    lag_order = int(fitted.k_ar)
    if lag_order < 1:
        raise ValueError("DY connectedness requires at least one estimated lag.")
    _, normalized = _generalized_fevd(np.asarray(fitted.coefs), np.asarray(fitted.sigma_u), horizon=max(2, int(horizon)))
    directional_rows = _directional_connectedness_rows(normalized, series_columns)
    total_connectedness = float(((normalized.sum() - np.trace(normalized)) / max(len(series_columns), 1)) * 100.0)
    figure = _connectedness_heatmap_figure(normalized, series_columns, title="Diebold-Yilmaz connectedness")
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="dy-connectedness",
        title="DY connectedness heatmap",
        summary="Diebold-Yilmaz spillover heatmap from generalized forecast-error variance decomposition.",
    )
    directional_figure, directional_axis = _pyplot().subplots(figsize=(9.4, 5.6), dpi=160)
    directional_axis.bar(
        [row["variable"] for row in directional_rows],
        [row["net"] for row in directional_rows],
        color=["#0b5f45" if float(row["net"]) >= 0 else "#b45309" for row in directional_rows],
    )
    directional_axis.axhline(0.0, color="#7c4d1c", linestyle="--", linewidth=1.0)
    directional_axis.set_title("Net directional spillovers")
    directional_axis.set_ylabel("Net spillover")
    directional_axis.grid(alpha=0.18, linestyle="--", axis="y")
    directional_figure.tight_layout()
    directional_figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=directional_figure,
        filename_slug="dy-net-spillovers",
        title="DY net directional spillovers",
        summary="Net spillover bar chart derived from the Diebold-Yilmaz connectedness matrix.",
    )
    return _nonregression_result_payload(
        model_type="dy_connectedness",
        model_label="DY Connectedness",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), *series_columns]].copy(),
        narrative_lines=[
            f"DY connectedness run on {asset.title}.",
            f"Series: {', '.join(series_columns)}.",
            f"FEVD horizon: {int(horizon)}.",
            f"Total connectedness index: {total_connectedness:.2f}.",
        ],
        specification={
            "model_type": "dy_connectedness",
            "model_family": "time_series_finance",
            "series_columns": series_columns,
            "time_column": time_column,
            "lags": lag_order,
            "horizon": int(horizon),
            "identification": "Generalized FEVD",
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), *series_columns],
            "manual_checklist": [
                "Re-estimate the VAR using the same lag order and sample.",
                "Rebuild the generalized FEVD at the documented horizon.",
                "Compare the connectedness matrix, directional spillovers, and heatmap cell by cell.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        metrics={"lag_order": lag_order, "horizon": int(horizon), "total_connectedness_index": total_connectedness},
        tables={
            "connectedness_matrix": _connectedness_matrix_rows(normalized, series_columns),
            "directional_spillovers": directional_rows,
        },
        extra={"figures": [figure_asset, directional_figure_asset]},
    )


def run_bk_connectedness_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    series_columns: list[str],
    time_column: str = "",
    lags: int = 1,
    truncation_horizon: int = 80,
    short_horizon: int = 5,
    medium_horizon: int = 20,
) -> dict[str, Any]:
    asset, sample = _prepare_time_series_sample(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        series_columns=series_columns,
        time_column=time_column,
        min_rows=max(60, len(series_columns) * (int(lags) + 8)),
    )
    fitted = VAR(sample[series_columns]).fit(maxlags=int(lags), trend="c")
    lag_order = int(fitted.k_ar)
    if lag_order < 1:
        raise ValueError("BK connectedness requires at least one estimated lag.")
    band_results = _bk_frequency_connectedness(
        np.asarray(fitted.coefs),
        np.asarray(fitted.sigma_u),
        short_horizon=int(short_horizon),
        medium_horizon=int(medium_horizon),
        truncation_horizon=int(truncation_horizon),
    )
    figure, axes = _pyplot().subplots(
        1,
        len(band_results),
        figsize=(5.6 * len(band_results), 5.0),
        dpi=160,
        constrained_layout=True,
    )
    if len(band_results) == 1:
        axes = [axes]
    for axis, band_result in zip(axes, band_results):
        matrix = band_result["normalized_matrix"]
        image = axis.imshow(matrix * 100.0, cmap="YlOrBr")
        axis.set_title(band_result["band"])
        axis.set_xticks(range(len(series_columns)))
        axis.set_xticklabels(series_columns, rotation=35, ha="right")
        axis.set_yticks(range(len(series_columns)))
        axis.set_yticklabels(series_columns)
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                axis.text(
                    column_index,
                    row_index,
                    f"{matrix[row_index, column_index] * 100.0:.1f}",
                    ha="center",
                    va="center",
                    color="#402107",
                    fontsize=7,
                )
    figure.colorbar(image, ax=axes, fraction=0.035, pad=0.02, label="Within-band normalized percent")
    figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=figure,
        filename_slug="bk-connectedness",
        title="BK frequency connectedness",
        summary="Frequency-domain connectedness heatmaps across short, medium, and long horizons.",
    )
    summary_figure, summary_axis = _pyplot().subplots(figsize=(8.8, 5.2), dpi=160)
    band_labels = [band_result["band"] for band_result in band_results]
    band_tci = [float(band_result["total_connectedness_index"]) for band_result in band_results]
    summary_axis.bar(band_labels, band_tci, color=["#d97706", "#0b5f45", "#7c3aed"][: len(band_results)])
    summary_axis.set_title("Band total connectedness")
    summary_axis.set_ylabel("Total connectedness index")
    summary_axis.grid(alpha=0.18, linestyle="--", axis="y")
    summary_figure.tight_layout()
    summary_figure_asset = _save_model_figure_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        source_asset=asset,
        figure=summary_figure,
        filename_slug="bk-band-summary",
        title="BK band connectedness summary",
        summary="Band-level total connectedness index across short, medium, and long frequencies.",
    )
    table_payload: dict[str, Any] = {
        "band_total_connectedness": [
            {
                "band": band_result["band"],
                "total_connectedness_index": float(band_result["total_connectedness_index"]),
                "band_variance_share": float(band_result["band_variance_share"]),
            }
            for band_result in band_results
        ]
    }
    for band_result in band_results:
        band_slug = band_result["band"].split(" ")[0].lower()
        table_payload[f"{band_slug}_connectedness_matrix"] = _connectedness_matrix_rows(
            band_result["normalized_matrix"],
            series_columns,
        )
        table_payload[f"{band_slug}_directional_spillovers"] = _directional_connectedness_rows(
            band_result["normalized_matrix"],
            series_columns,
        )
    return _nonregression_result_payload(
        model_type="bk_connectedness",
        model_label="BK Connectedness",
        asset=asset,
        sample=sample[[*([time_column] if time_column else []), *series_columns]].copy(),
        narrative_lines=[
            f"BK connectedness run on {asset.title}.",
            f"Series: {', '.join(series_columns)}.",
            f"Frequency bands use short horizon {int(short_horizon)} and medium horizon {int(medium_horizon)}.",
            "Each heatmap is normalized within its band so spillover structure can be compared directly.",
        ],
        specification={
            "model_type": "bk_connectedness",
            "model_family": "time_series_finance",
            "series_columns": series_columns,
            "time_column": time_column,
            "lags": lag_order,
            "short_horizon": int(short_horizon),
            "medium_horizon": int(medium_horizon),
            "truncation_horizon": int(truncation_horizon),
            "identification": "Barunik-Krehlik style frequency connectedness decomposition",
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": [*([time_column] if time_column else []), *series_columns],
            "manual_checklist": [
                "Re-estimate the VAR with the same lag order and coefficient matrices.",
                "Rebuild the frequency-band connectedness decomposition using the documented short and medium horizons.",
                "Compare the band matrices, total connectedness values, and heatmap labels band by band.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing selected series values are dropped."],
        },
        metrics={
            "lag_order": lag_order,
            "short_horizon": int(short_horizon),
            "medium_horizon": int(medium_horizon),
            "truncation_horizon": int(truncation_horizon),
        },
        tables=table_payload,
        extra={"figures": [figure_asset, summary_figure_asset]},
    )


def run_altman_z_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    working_capital_column: str,
    retained_earnings_column: str,
    ebit_column: str,
    market_equity_column: str,
    sales_column: str,
    total_assets_column: str,
    total_liabilities_column: str,
) -> dict[str, Any]:
    required_columns = [working_capital_column, retained_earnings_column, ebit_column, market_equity_column, sales_column, total_assets_column, total_liabilities_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    positive_mask = (sample[total_assets_column] > 0) & (sample[total_liabilities_column] > 0)
    sample = sample.loc[positive_mask].copy()
    if sample.empty:
        raise ValueError("Altman Z-score requires positive total assets and total liabilities.")
    sample["altman_z"] = 1.2 * (sample[working_capital_column] / sample[total_assets_column]) + 1.4 * (sample[retained_earnings_column] / sample[total_assets_column]) + 3.3 * (sample[ebit_column] / sample[total_assets_column]) + 0.6 * (sample[market_equity_column] / sample[total_liabilities_column]) + 1.0 * (sample[sales_column] / sample[total_assets_column])
    sample["distress_zone"] = np.where(sample["altman_z"] < 1.81, "distress", np.where(sample["altman_z"] < 2.99, "grey", "safe"))
    latest = sample.iloc[-1]
    return _nonregression_result_payload(
        model_type="altman_z",
        model_label="Altman Z-Score",
        asset=asset,
        sample=sample[required_columns + ["altman_z", "distress_zone"]].copy(),
        narrative_lines=[f"Altman Z-score computed on {asset.title}.", f"Latest Z-score: {float(latest['altman_z']):.4f}.", f"Latest zone: {latest['distress_zone']}."],
        specification={
            "model_type": "altman_z",
            "model_family": "corporate_finance",
            "equation": "1.2*(WC/TA)+1.4*(RE/TA)+3.3*(EBIT/TA)+0.6*(MVE/TL)+1.0*(Sales/TA)",
            "input_columns": {"working_capital": working_capital_column, "retained_earnings": retained_earnings_column, "ebit": ebit_column, "market_equity": market_equity_column, "sales": sales_column, "total_assets": total_assets_column, "total_liabilities": total_liabilities_column},
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": required_columns,
            "manual_checklist": [
                "Recompute each ratio term using the listed accounting columns.",
                "Apply the standard Altman weights to reproduce altman_z.",
                "Check the distress-zone cutoff against 1.81 and 2.99.",
            ],
            "derived_columns": ["altman_z", "distress_zone"],
            "filters": ["Rows with missing inputs are dropped.", "Rows with nonpositive total assets or total liabilities are removed."],
        },
        metrics={"latest_score": float(latest["altman_z"]), "mean_score": float(sample["altman_z"].mean()), "distress_share": float((sample["distress_zone"] == "distress").mean())},
        tables={"score_preview": _frame_preview_rows(sample[required_columns + ["altman_z", "distress_zone"]].copy(), limit=10)},
    )


def run_dupont_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    net_income_column: str,
    revenue_column: str,
    total_assets_column: str,
    equity_column: str,
) -> dict[str, Any]:
    required_columns = [net_income_column, revenue_column, total_assets_column, equity_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    positive_mask = (sample[revenue_column] != 0) & (sample[total_assets_column] != 0) & (sample[equity_column] != 0)
    sample = sample.loc[positive_mask].copy()
    if sample.empty:
        raise ValueError("DuPont analysis requires nonzero revenue, total assets, and equity.")
    sample["profit_margin"] = sample[net_income_column] / sample[revenue_column]
    sample["asset_turnover"] = sample[revenue_column] / sample[total_assets_column]
    sample["equity_multiplier"] = sample[total_assets_column] / sample[equity_column]
    sample["roe_dupont"] = sample["profit_margin"] * sample["asset_turnover"] * sample["equity_multiplier"]
    latest = sample.iloc[-1]
    return _nonregression_result_payload(
        model_type="dupont",
        model_label="DuPont Analysis",
        asset=asset,
        sample=sample[required_columns + ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"]].copy(),
        narrative_lines=[f"DuPont analysis computed on {asset.title}.", f"Latest ROE decomposition: {float(latest['roe_dupont']):.4f}."],
        specification={
            "model_type": "dupont",
            "model_family": "corporate_finance",
            "equation": "ROE = (NetIncome/Revenue) * (Revenue/Assets) * (Assets/Equity)",
            "input_columns": {"net_income": net_income_column, "revenue": revenue_column, "total_assets": total_assets_column, "equity": equity_column},
        },
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": required_columns,
            "manual_checklist": [
                "Compute profit margin, asset turnover, and equity multiplier from the listed accounting columns.",
                "Multiply the three terms to reproduce roe_dupont.",
                "Compare the latest-row decomposition with the preview table.",
            ],
            "derived_columns": ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"],
            "filters": ["Rows with missing inputs are dropped.", "Rows with zero revenue, assets, or equity are removed."],
        },
        metrics={"latest_roe": float(latest["roe_dupont"]), "mean_roe": float(sample["roe_dupont"].mean())},
        tables={"dupont_preview": _frame_preview_rows(sample[required_columns + ["profit_margin", "asset_turnover", "equity_multiplier", "roe_dupont"]].copy(), limit=10)},
    )


def run_risk_metric_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    return_column: str,
    time_column: str = "",
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
    ewma_lambda: float = 0.94,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    required_columns = [return_column] + ([time_column] if time_column else [])
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    sample[return_column] = _coerce_numeric_series(sample[return_column])
    sample = sample.dropna().copy()
    if time_column:
        sample = _sort_sample_by_time(sample, time_column)
    if len(sample) < 20:
        raise ValueError("Risk models require at least 20 return observations.")
    returns = sample[return_column].astype(float)
    alpha = 1.0 - float(confidence_level)
    if not (0 < alpha < 1):
        raise ValueError("Confidence level must lie between 0 and 1.")
    if holding_period_days < 1:
        raise ValueError("Holding period must be at least 1 day.")
    normal = NormalDist()

    if model_type == "historical_var":
        raw_var = float(returns.quantile(alpha))
        tail = returns.loc[returns <= raw_var]
        expected_shortfall = float(tail.mean()) if not tail.empty else raw_var
        label = "Historical VaR / ES"
        equation = "VaR_alpha = empirical quantile; ES_alpha = mean(returns <= VaR_alpha)"
        metrics = {"confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "var": -raw_var * math.sqrt(holding_period_days), "expected_shortfall": -expected_shortfall * math.sqrt(holding_period_days), "mean_return": float(returns.mean()), "volatility": float(returns.std())}
        derived_columns: list[str] = []
    elif model_type == "parametric_var":
        z_value = normal.inv_cdf(alpha)
        mean_return = float(returns.mean())
        volatility = float(returns.std())
        raw_var = mean_return + z_value * volatility
        es = mean_return - volatility * (math.exp(-(z_value**2) / 2.0) / math.sqrt(2.0 * math.pi)) / alpha
        label = "Parametric VaR / ES"
        equation = "VaR_alpha = mu + z_alpha*sigma under normality"
        metrics = {"confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "var": -raw_var * math.sqrt(holding_period_days), "expected_shortfall": -es * math.sqrt(holding_period_days), "mean_return": mean_return, "volatility": volatility}
        derived_columns = []
    else:
        normalized_lambda = float(ewma_lambda)
        if not (0 < normalized_lambda < 1):
            raise ValueError("EWMA lambda must lie between 0 and 1.")
        ewma_variance = float(np.var(returns))
        volatility_path = []
        for value in returns.astype(float):
            ewma_variance = normalized_lambda * ewma_variance + (1 - normalized_lambda) * float(value) ** 2
            volatility_path.append(math.sqrt(max(ewma_variance, 0.0)))
        label = "EWMA Volatility"
        equation = "sigma_t^2 = lambda*sigma_{t-1}^2 + (1-lambda)*r_{t-1}^2"
        sample = sample.copy()
        sample["ewma_volatility"] = volatility_path
        metrics = {"ewma_lambda": normalized_lambda, "latest_volatility": float(volatility_path[-1]), "mean_return": float(returns.mean()), "volatility": float(returns.std())}
        derived_columns = ["ewma_volatility"]

    risk_summary_rows = [
        {
            "confidence_level": float(confidence_level),
            "holding_period_days": int(holding_period_days),
            "var": float(metrics["var"]) if metrics.get("var") is not None else None,
            "expected_shortfall": (
                float(metrics["expected_shortfall"])
                if metrics.get("expected_shortfall") is not None
                else (float(metrics["var"]) if metrics.get("var") is not None else None)
            ),
            "mean_return": float(metrics["mean_return"]) if metrics.get("mean_return") is not None else None,
            "volatility": float(metrics["volatility"]) if metrics.get("volatility") is not None else None,
            "ewma_lambda": float(metrics["ewma_lambda"]) if model_type == "ewma_volatility" else None,
            "latest_volatility": float(metrics["latest_volatility"]) if model_type == "ewma_volatility" else None,
        }
    ]
    risk_series_rows = _frame_preview_rows(sample, limit=25)
    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=sample,
        narrative_lines=[f"{label} run on {asset.title}.", f"Return series: {return_column}."],
        specification={"model_type": model_type, "model_family": "risk_management", "equation": equation, "return_column": return_column, "time_column": time_column, "confidence_level": float(confidence_level), "holding_period_days": int(holding_period_days), "ewma_lambda": float(ewma_lambda)},
        audit_trail={
            "rows_used": int(len(sample)),
            "sample_columns": list(sample.columns),
            "manual_checklist": [
                "Download the sample asset and sort it by the listed time_column if one is provided.",
                "Recompute the return distribution statistics and the stated risk metric formula.",
                "Compare the reproduced VaR/ES or EWMA volatility against the metrics block.",
            ],
            "derived_columns": derived_columns,
            "filters": ["Rows with missing selected return values are dropped."],
        },
        metrics=metrics,
        tables={
            "risk_summary": risk_summary_rows,
            "series_preview": risk_series_rows,
        },
    )


def run_option_pricing_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    spot_column: str,
    strike_column: str,
    maturity_column: str,
    rate_column: str,
    volatility_column: str,
    option_type: str = "call",
    option_steps: int = 50,
) -> dict[str, Any]:
    required_columns = [spot_column, strike_column, maturity_column, rate_column, volatility_column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    if sample.empty:
        raise ValueError("No complete observations are available for option pricing.")
    records = []
    truncated = sample.head(500).copy()
    for _, row in truncated.iterrows():
        if model_type == "binomial_option":
            records.append(
                {
                    "price": _binomial_option_price(
                        spot=float(row[spot_column]),
                        strike=float(row[strike_column]),
                        maturity=float(row[maturity_column]),
                        rate=float(row[rate_column]),
                        volatility=float(row[volatility_column]),
                        steps=int(option_steps),
                        option_type=option_type,
                    )
                }
            )
        else:
            records.append(
                _black_scholes_price(
                    spot=float(row[spot_column]),
                    strike=float(row[strike_column]),
                    maturity=float(row[maturity_column]),
                    rate=float(row[rate_column]),
                    volatility=float(row[volatility_column]),
                    option_type=option_type,
                )
            )
    valuations = pd.DataFrame(records)
    preview = pd.concat([truncated.reset_index(drop=True), valuations], axis=1)
    latest = preview.iloc[-1]
    label = "Binomial Option Pricing" if model_type == "binomial_option" else "Black-Scholes"
    equation = "CRR binomial tree backward induction" if model_type == "binomial_option" else "Closed-form Black-Scholes-Merton pricing formula"
    pricing_rows = _frame_preview_rows(preview, limit=25)
    greek_rows = [
        {
            "latest_price": float(latest["price"]),
            "mean_price": float(preview["price"].mean()),
            "delta": float(latest["delta"]) if "delta" in latest and pd.notna(latest["delta"]) else None,
            "gamma": float(latest["gamma"]) if "gamma" in latest and pd.notna(latest["gamma"]) else None,
            "d1": float(latest["d1"]) if "d1" in latest and pd.notna(latest["d1"]) else None,
            "d2": float(latest["d2"]) if "d2" in latest and pd.notna(latest["d2"]) else None,
            "option_type": option_type,
            "option_steps": int(option_steps),
        }
    ]
    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=preview,
        narrative_lines=[f"{label} run on {asset.title}.", f"Option type: {option_type}.", f"Latest price: {float(latest['price']):.4f}."],
        specification={
            "model_type": model_type,
            "model_family": "derivatives_pricing",
            "equation": equation,
            "input_columns": {"spot": spot_column, "strike": strike_column, "maturity": maturity_column, "rate": rate_column, "volatility": volatility_column},
            "option_type": option_type,
            "option_steps": int(option_steps),
        },
        audit_trail={
            "rows_used": int(len(preview)),
            "sample_columns": list(preview.columns),
            "manual_checklist": [
                "Download the sample asset and reproduce the pricing inputs row by row.",
                "Use the same option_type and option_steps when applicable.",
                "Compare the reproduced option values against the preview table and latest price metric.",
            ],
            "derived_columns": list(valuations.columns),
            "filters": ["Rows with missing pricing inputs are dropped.", "Only the first 500 complete rows are priced for stability."],
        },
        metrics={"latest_price": float(latest["price"]), "mean_price": float(preview["price"].mean())},
        tables={
            "pricing_table": pricing_rows,
            "pricing_greeks_summary": greek_rows,
        },
    )


def run_taylor_rule_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    inflation_gap_column: str,
    output_gap_column: str,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [inflation_gap_column, output_gap_column, *[column for column in (controls or []) if column]]
    payload = run_ols_analysis(
        settings,
        db,
        user=user,
        workspace=workspace,
        asset_id=asset_id,
        dependent=dependent,
        independents=regressors,
        robust_covariance=robust_covariance,
    )
    payload["model_type"] = "taylor_rule"
    payload["model_label"] = "Taylor Rule"
    payload["model_family"] = "macro_finance_dsge"
    payload["inflation_gap_column"] = inflation_gap_column
    payload["output_gap_column"] = output_gap_column
    payload["specification"]["model_type"] = "taylor_rule"
    payload["specification"]["model_family"] = "macro_finance_dsge"
    payload["specification"]["equation"] = f"{dependent} ~ {inflation_gap_column} + {output_gap_column}" + (f" + {' + '.join(controls or [])}" if controls else "")
    payload["audit_trail"]["manual_checklist"].append("Interpret the inflation-gap and output-gap coefficients against the standard Taylor-rule benchmark.")
    return payload


def run_rbc_dsge_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    alpha: float = 0.33,
    beta: float = 0.99,
    delta: float = 0.025,
    productivity: float = 1.0,
    labor: float = 0.33,
    shock_persistence: float = 0.9,
    shock_size: float = 0.01,
    impulse_horizon: int = 12,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    if not (0 < alpha < 1 and 0 < beta < 1 and 0 < delta < 1 and productivity > 0 and labor > 0):
        raise ValueError("RBC/DSGE calibration requires alpha, beta, delta in (0,1) and positive productivity/labor.")
    capital_return = (1 / beta) - 1 + delta
    capital_per_labor = (alpha * productivity / capital_return) ** (1 / (1 - alpha))
    capital = capital_per_labor * labor
    output = productivity * (capital**alpha) * (labor ** (1 - alpha))
    investment = delta * capital
    consumption = output - investment
    impulse = []
    for step in range(int(impulse_horizon) + 1):
        technology = productivity * (1 + shock_size * (shock_persistence**step))
        shocked_output = technology * (capital**alpha) * (labor ** (1 - alpha))
        impulse.append({"step": step, "technology": float(technology), "output": float(shocked_output), "consumption": float(shocked_output - investment)})
    return _nonregression_result_payload(
        model_type="rbc_dsge",
        model_label="Toy RBC / DSGE",
        asset=asset,
        sample=None,
        narrative_lines=[f"Toy RBC/DSGE calibration run on {asset.title}.", f"Steady-state output: {float(output):.4f}.", f"Steady-state consumption: {float(consumption):.4f}."],
        specification={
            "model_type": "rbc_dsge",
            "model_family": "macro_finance_dsge",
            "equation": "Calibrated Cobb-Douglas RBC steady state with a productivity shock impulse path",
            "parameters": {"alpha": float(alpha), "beta": float(beta), "delta": float(delta), "productivity": float(productivity), "labor": float(labor), "shock_persistence": float(shock_persistence), "shock_size": float(shock_size), "impulse_horizon": int(impulse_horizon)},
        },
        audit_trail={
            "rows_used": 0,
            "sample_columns": [],
            "manual_checklist": [
                "Recompute the Euler-implied capital return and steady-state capital-labor ratio from the listed calibration parameters.",
                "Rebuild steady-state output, investment, and consumption under the Cobb-Douglas production function.",
                "Reproduce the impulse path using the same shock persistence and shock size.",
            ],
            "derived_columns": [],
            "filters": [],
        },
        metrics={"steady_state_capital": float(capital), "steady_state_output": float(output), "steady_state_consumption": float(consumption), "steady_state_investment": float(investment)},
        tables={
            "impulse_response_table": impulse,
            "steady_state_summary": [
                {
                    "steady_state_capital": float(capital),
                    "steady_state_output": float(output),
                    "steady_state_consumption": float(consumption),
                    "steady_state_investment": float(investment),
                }
            ],
        },
    )


def run_portfolio_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    series_columns: list[str],
    risk_aversion: float = 3.0,
    long_only: bool = True,
) -> dict[str, Any]:
    series_columns = [column for column in series_columns if column]
    if len(series_columns) < 2:
        raise ValueError("Portfolio allocation requires at least two return series.")
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in series_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[series_columns].copy()
    for column in series_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    returns = sample.dropna().astype(float)
    if len(returns) < 20:
        raise ValueError("Portfolio models require at least 20 complete return observations.")
    mean_returns = returns.mean().to_numpy()
    covariance = returns.cov().to_numpy()
    inverse_covariance = np.linalg.pinv(covariance)
    ones = np.ones(len(series_columns))
    if model_type == "minimum_variance":
        weights = inverse_covariance @ ones
        label = "Minimum Variance Portfolio"
    elif model_type == "risk_parity":
        weights = _risk_parity_weights(covariance)
        label = "Risk Parity Portfolio"
    else:
        weights = inverse_covariance @ mean_returns / max(float(risk_aversion), 1e-6)
        label = "Mean-Variance Portfolio"
    if long_only:
        weights = np.clip(weights, 0.0, None)
    if np.allclose(weights.sum(), 0.0):
        weights = np.full(len(series_columns), 1.0 / len(series_columns))
    else:
        weights = weights / weights.sum()
    portfolio_return = float(mean_returns @ weights)
    portfolio_volatility = float(math.sqrt(max(weights @ covariance @ weights, 0.0)))
    weights_table = [{"asset_column": series_columns[index], "weight": float(weights[index]), "mean_return": float(mean_returns[index])} for index in range(len(series_columns))]
    covariance_rows = [
        {
            "asset_row": series_columns[row_index],
            **{
                series_columns[column_index]: float(covariance[row_index, column_index])
                for column_index in range(len(series_columns))
            },
        }
        for row_index in range(len(series_columns))
    ]
    return _nonregression_result_payload(
        model_type=model_type,
        model_label=label,
        asset=asset,
        sample=returns,
        narrative_lines=[f"{label} run on {asset.title}.", f"Assets: {', '.join(series_columns)}.", f"Expected portfolio return: {portfolio_return:.6f}.", f"Portfolio volatility: {portfolio_volatility:.6f}."],
        specification={"model_type": model_type, "model_family": "portfolio_allocation", "series_columns": series_columns, "risk_aversion": float(risk_aversion), "long_only": bool(long_only)},
        audit_trail={
            "rows_used": int(len(returns)),
            "sample_columns": series_columns,
            "manual_checklist": [
                "Recompute the sample mean vector and covariance matrix from the listed return columns.",
                "Apply the same allocation rule and long_only setting to reproduce the portfolio weights.",
                "Check the resulting portfolio return and volatility against the metrics block.",
            ],
            "derived_columns": [],
            "filters": ["Rows with missing return values across any selected asset column are dropped."],
        },
        metrics={"expected_return": portfolio_return, "volatility": portfolio_volatility},
        tables={
            "weights_table": weights_table,
            "covariance_matrix": covariance_rows,
        },
    )


def run_asset_pricing_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    model_type: str,
    asset_return_column: str,
    market_column: str,
    risk_free_column: str = "",
    smb_column: str = "",
    hml_column: str = "",
    robust_covariance: bool = True,
) -> dict[str, Any]:
    required_columns = [asset_return_column, market_column]
    if risk_free_column:
        required_columns.append(risk_free_column)
    if model_type == "fama_french_3":
        required_columns.extend([smb_column, hml_column])
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    sample["asset_excess"] = sample[asset_return_column] - sample[risk_free_column] if risk_free_column else sample[asset_return_column]
    sample["market_excess"] = sample[market_column] - sample[risk_free_column] if risk_free_column else sample[market_column]
    regressors = ["market_excess"]
    if model_type == "fama_french_3":
        regressors.extend([smb_column, hml_column])
    fitted = _fit_ols(sample[["asset_excess", *regressors]].copy(), "asset_excess", regressors, robust_covariance=robust_covariance)
    payload = _model_result_payload(
        model_type=model_type,
        model_label="Fama-French 3-Factor" if model_type == "fama_french_3" else "CAPM",
        asset=asset,
        dependent="asset_excess",
        regressors=regressors,
        sample=sample[["asset_excess", *regressors]].copy(),
        result=fitted,
        narrative_lines=[
            f"{'Fama-French 3-Factor' if model_type == 'fama_french_3' else 'CAPM'} run on {asset.title}.",
            f"Asset return column: {asset_return_column}.",
            f"Market factor column: {market_column}.",
        ],
        extra={
            "model_family": "asset_pricing",
            "asset_return_column": asset_return_column,
            "market_column": market_column,
            "risk_free_column": risk_free_column,
            "smb_column": smb_column,
            "hml_column": hml_column,
            "audit_trail": {
                "derived_columns": ["asset_excess", "market_excess"],
                "filters": ["Rows with missing factor or return inputs are dropped."],
            },
        },
    )
    payload["specification"]["equation"] = "asset_excess ~ " + " + ".join(regressors)
    return payload


def run_logit_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_binary_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted = _fit_binary_response(sample, dependent, regressors, model_kind="logit", robust_covariance=robust_covariance)
    summary_lines = [
        f"Logit run on {asset.title}.",
        f"Binary outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="logit",
        model_label="Logit",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing binary outcome or selected regressors are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Logit summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["logit", "dataset", "econometrics"],
        metadata=payload,
    )
    return payload


def run_probit_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, *regressors]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_binary_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted = _fit_binary_response(sample, dependent, regressors, model_kind="probit", robust_covariance=robust_covariance)
    summary_lines = [
        f"Probit run on {asset.title}.",
        f"Binary outcome variable: {dependent}.",
        f"Regressors: {', '.join(regressors)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="probit",
        model_label="Probit",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample,
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing binary outcome or selected regressors are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Probit summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["probit", "dataset", "econometrics"],
        metadata=payload,
    )
    return payload


def run_fixed_effects_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    entity_column: str,
    time_column: str = "",
    include_time_effects: bool = False,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    regressors = [column for column in [*(independents or []), *(controls or [])] if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, entity_column, *regressors]
    if include_time_effects and time_column:
        required_columns.append(time_column)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    sample[dependent] = _coerce_numeric_series(sample[dependent])
    for column in regressors:
        sample[column] = _coerce_numeric_series(sample[column])
    sample[entity_column] = sample[entity_column].astype(str).str.strip()
    if include_time_effects and time_column:
        sample[time_column] = sample[time_column].astype(str).str.strip()
    sample = sample.dropna().copy()

    if not regressors:
        raise ValueError("Fixed effects models require at least one explanatory variable.")

    entity_dummies = pd.get_dummies(sample[entity_column], prefix=f"fe_{entity_column}", drop_first=True, dtype=float)
    design_parts = [sample[regressors].astype(float), entity_dummies]
    fe_labels = [entity_column]
    if include_time_effects and time_column:
        time_dummies = pd.get_dummies(sample[time_column], prefix=f"fe_{time_column}", drop_first=True, dtype=float)
        design_parts.append(time_dummies)
        fe_labels.append(time_column)
    design = pd.concat(design_parts, axis=1)
    fitted = _fit_ols(pd.concat([sample[[dependent]], design], axis=1), dependent, list(design.columns), robust_covariance=robust_covariance)
    summary_lines = [
        f"Fixed effects model run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Slope regressors: {', '.join(regressors)}.",
        f"Fixed effects: {', '.join(fe_labels)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="fixed_effects",
        model_label="Fixed Effects",
        asset=asset,
        dependent=dependent,
        regressors=regressors,
        sample=sample[[dependent, *regressors, entity_column] + ([time_column] if include_time_effects and time_column else [])].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "entity_column": entity_column,
            "time_column": time_column if include_time_effects else "",
            "include_time_effects": include_time_effects,
            "entity_count": int(sample[entity_column].nunique()),
            "time_count": int(sample[time_column].nunique()) if include_time_effects and time_column else 0,
            "audit_trail": {
                "derived_columns": list(design.columns),
                "filters": ["Rows with missing outcome, slope regressors, entity ids, or time ids are dropped."],
                "fixed_effects": fe_labels,
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Fixed effects summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["fixed_effects", "panel", "econometrics"],
        metadata=payload,
    )
    return payload


def run_iv_2sls_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    dependent: str,
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    endogenous_column: str,
    instrument_columns: list[str] | None = None,
    robust_covariance: bool = True,
) -> dict[str, Any]:
    exogenous = [column for column in [*(independents or []), *(controls or [])] if column]
    instruments = [column for column in (instrument_columns or []) if column]
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    required_columns = [dependent, endogenous_column, *exogenous, *instruments]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    sample = frame[required_columns].copy()
    for column in required_columns:
        sample[column] = _coerce_numeric_series(sample[column])
    sample = sample.dropna().copy()
    fitted, covariance_type = _fit_iv_2sls(
        sample,
        dependent,
        exogenous=exogenous,
        endogenous=endogenous_column,
        instruments=instruments,
        robust_covariance=robust_covariance,
    )
    summary_lines = [
        f"IV-2SLS run on {asset.title}.",
        f"Outcome variable: {dependent}.",
        f"Endogenous regressor: {endogenous_column}.",
        f"Instruments: {', '.join(instruments)}.",
        f"Observations used: {int(fitted.nobs)}.",
    ]
    payload = _model_result_payload(
        model_type="iv_2sls",
        model_label="IV-2SLS",
        asset=asset,
        dependent=dependent,
        regressors=[*exogenous, endogenous_column],
        sample=sample[[dependent, *exogenous, endogenous_column, *instruments]].copy(),
        result=fitted,
        narrative_lines=summary_lines,
        extra={
            "endogenous_column": endogenous_column,
            "instrument_columns": instruments,
            "exogenous_columns": exogenous,
            "covariance_type": covariance_type,
            "covariance_note": "IV-2SLS uses conventional covariance when robust covariance is unavailable in the current backend."
            if robust_covariance and covariance_type != "HC1"
            else "",
            "audit_trail": {
                "derived_columns": [],
                "filters": ["Rows with missing dependent, endogenous regressor, exogenous regressors, or instruments are dropped."],
            },
        },
    )
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"IV-2SLS summary for {asset.title}",
        content="\n".join(summary_lines),
        tags=["iv_2sls", "instrumental_variables", "econometrics"],
        metadata=payload,
    )
    return payload


def _infer_model_family(model_type: str) -> str:
    mapping = {
        "ols": "econometrics_baseline",
        "ppml": "econometrics_baseline",
        "logit": "econometrics_baseline",
        "probit": "econometrics_baseline",
        "did": "econometrics_baseline",
        "event_study": "econometrics_baseline",
        "rdd": "econometrics_baseline",
        "fixed_effects": "econometrics_baseline",
        "gravity": "econometrics_baseline",
        "iv_2sls": "econometrics_baseline",
        "panel_iv": "econometrics_baseline",
        "arima": "time_series_finance",
        "arch": "time_series_finance",
        "garch": "time_series_finance",
        "var": "time_series_finance",
        "svar_irf": "time_series_finance",
        "virf": "time_series_finance",
        "dy_connectedness": "time_series_finance",
        "bk_connectedness": "time_series_finance",
        "altman_z": "corporate_finance",
        "dupont": "corporate_finance",
        "historical_var": "risk_management",
        "parametric_var": "risk_management",
        "ewma_volatility": "risk_management",
        "black_scholes": "derivatives_pricing",
        "binomial_option": "derivatives_pricing",
        "taylor_rule": "macro_finance_dsge",
        "rbc_dsge": "macro_finance_dsge",
        "mean_variance": "portfolio_allocation",
        "minimum_variance": "portfolio_allocation",
        "risk_parity": "portfolio_allocation",
        "capm": "asset_pricing",
        "fama_french_3": "asset_pricing",
    }
    if model_type in mapping:
        return mapping[model_type]
    try:
        from .data_lab_catalog import get_data_lab_catalog

        for family in get_data_lab_catalog():
            for method in family.get("methods", []):
                if str(method.get("slug") or "").strip().lower() == model_type:
                    return str(family.get("slug") or "econometrics_baseline")
    except Exception:
        pass
    return "econometrics_baseline"


def run_model_analysis(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    model_type: str,
    asset_id: str,
    dependent: str = "",
    independents: list[str] | None = None,
    controls: list[str] | None = None,
    series_columns: list[str] | None = None,
    treatment_column: str = "",
    post_column: str = "",
    event_time_column: str = "",
    lead_window: int = 4,
    lag_window: int = 4,
    omitted_period: int = -1,
    origin_mass_column: str = "",
    destination_mass_column: str = "",
    distance_column: str = "",
    running_column: str = "",
    cutoff: float = 0.0,
    bandwidth: float = 0.0,
    polynomial_order: int = 1,
    treat_above_cutoff: bool = True,
    entity_column: str = "",
    time_column: str = "",
    include_time_effects: bool = False,
    endogenous_column: str = "",
    instrument_columns: list[str] | None = None,
    market_column: str = "",
    risk_free_column: str = "",
    smb_column: str = "",
    hml_column: str = "",
    spot_column: str = "",
    strike_column: str = "",
    maturity_column: str = "",
    rate_column: str = "",
    volatility_column: str = "",
    working_capital_column: str = "",
    retained_earnings_column: str = "",
    ebit_column: str = "",
    market_equity_column: str = "",
    total_assets_column: str = "",
    total_liabilities_column: str = "",
    sales_column: str = "",
    net_income_column: str = "",
    revenue_column: str = "",
    equity_column: str = "",
    inflation_gap_column: str = "",
    output_gap_column: str = "",
    arima_p: int = 1,
    arima_d: int = 0,
    arima_q: int = 0,
    garch_p: int = 1,
    garch_q: int = 1,
    forecast_steps: int = 5,
    var_lags: int = 1,
    irf_horizon: int = 12,
    impulse_column: str = "",
    response_column: str = "",
    virf_shock_size: float = 1.0,
    bk_short_horizon: int = 5,
    bk_medium_horizon: int = 20,
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
    ewma_lambda: float = 0.94,
    option_type: str = "call",
    option_steps: int = 50,
    risk_aversion: float = 3.0,
    long_only: bool = True,
    dsge_alpha: float = 0.33,
    dsge_beta: float = 0.99,
    dsge_delta: float = 0.025,
    dsge_productivity: float = 1.0,
    dsge_labor: float = 0.33,
    dsge_shock_persistence: float = 0.9,
    dsge_shock_size: float = 0.01,
    dsge_impulse_horizon: int = 12,
    robust_covariance: bool = True,
    feature_columns: list[str] | None = None,
    factor_columns: list[str] | None = None,
    secondary_dependent: str = "",
    glm_family: str = "",
    gee_family: str = "",
    gee_group_column: str = "",
    count_family: str = "",
    inflation_regressors: list[str] | None = None,
    quantile: float = 0.5,
    varmax_order: list[int] | tuple[int, int] | None = None,
    coint_rank: int = 1,
    vecm_diff_lags: int = 1,
    markov_regimes: int = 2,
    seasonal: str | None = None,
    seasonal_periods: int = 12,
    distribution: str = "",
    garch_o: int = 0,
    forecast_simulations: int = 500,
    harx_lags: list[int] | None = None,
    unit_root_lags: int | None = None,
    trend: str = "",
    portfolio_objective: str = "",
    cvar_beta: float = 0.95,
    cdar_beta: float = 0.95,
    split_ratio: float = 0.7,
    n_estimators: int = 120,
    learning_rate: float = 0.05,
    num_leaves: int = 31,
    iterations: int = 180,
    depth: int = 6,
    treated_unit: str = "",
    control_units: list[str] | None = None,
    treatment_time: float | int | str | None = None,
    treatment_time_column: str = "",
    treatment_index: int = 0,
    intervention_at: float | int | str | None = None,
    draws: int = 150,
    tune: int = 150,
    chains: int = 2,
    template_id: str = "",
    template_name: str = "",
    variant_label: str = "",
    variant_spec: dict[str, Any] | None = None,
    effective_specification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_model = model_type.strip().lower()
    runtime_options = {
        "asset_id": asset_id,
        "dependent": dependent,
        "independents": independents or [],
        "controls": controls or [],
        "series_columns": series_columns or [],
        "treatment_column": treatment_column,
        "post_column": post_column,
        "event_time_column": event_time_column,
        "lead_window": lead_window,
        "lag_window": lag_window,
        "omitted_period": omitted_period,
        "origin_mass_column": origin_mass_column,
        "destination_mass_column": destination_mass_column,
        "distance_column": distance_column,
        "running_column": running_column,
        "cutoff": cutoff,
        "bandwidth": bandwidth,
        "polynomial_order": polynomial_order,
        "treat_above_cutoff": treat_above_cutoff,
        "entity_column": entity_column,
        "time_column": time_column,
        "include_time_effects": include_time_effects,
        "endogenous_column": endogenous_column,
        "instrument_columns": instrument_columns or [],
        "market_column": market_column,
        "risk_free_column": risk_free_column,
        "smb_column": smb_column,
        "hml_column": hml_column,
        "spot_column": spot_column,
        "strike_column": strike_column,
        "maturity_column": maturity_column,
        "rate_column": rate_column,
        "volatility_column": volatility_column,
        "working_capital_column": working_capital_column,
        "retained_earnings_column": retained_earnings_column,
        "ebit_column": ebit_column,
        "market_equity_column": market_equity_column,
        "total_assets_column": total_assets_column,
        "total_liabilities_column": total_liabilities_column,
        "sales_column": sales_column,
        "net_income_column": net_income_column,
        "revenue_column": revenue_column,
        "equity_column": equity_column,
        "inflation_gap_column": inflation_gap_column,
        "output_gap_column": output_gap_column,
        "arima_p": arima_p,
        "arima_d": arima_d,
        "arima_q": arima_q,
        "garch_p": garch_p,
        "garch_q": garch_q,
        "forecast_steps": forecast_steps,
        "var_lags": var_lags,
        "irf_horizon": irf_horizon,
        "impulse_column": impulse_column,
        "response_column": response_column,
        "virf_shock_size": virf_shock_size,
        "bk_short_horizon": bk_short_horizon,
        "bk_medium_horizon": bk_medium_horizon,
        "confidence_level": confidence_level,
        "holding_period_days": holding_period_days,
        "ewma_lambda": ewma_lambda,
        "option_type": option_type,
        "option_steps": option_steps,
        "risk_aversion": risk_aversion,
        "long_only": long_only,
        "dsge_alpha": dsge_alpha,
        "dsge_beta": dsge_beta,
        "dsge_delta": dsge_delta,
        "dsge_productivity": dsge_productivity,
        "dsge_labor": dsge_labor,
        "dsge_shock_persistence": dsge_shock_persistence,
        "dsge_shock_size": dsge_shock_size,
        "dsge_impulse_horizon": dsge_impulse_horizon,
        "robust_covariance": robust_covariance,
        "feature_columns": feature_columns or [],
        "factor_columns": factor_columns or [],
        "secondary_dependent": secondary_dependent,
        "glm_family": glm_family,
        "gee_family": gee_family,
        "gee_group_column": gee_group_column,
        "count_family": count_family,
        "inflation_regressors": inflation_regressors or [],
        "quantile": quantile,
        "varmax_order": list(varmax_order or (1, 1)),
        "coint_rank": coint_rank,
        "vecm_diff_lags": vecm_diff_lags,
        "markov_regimes": markov_regimes,
        "seasonal": seasonal or None,
        "seasonal_periods": seasonal_periods,
        "distribution": distribution,
        "garch_o": garch_o,
        "forecast_simulations": forecast_simulations,
        "harx_lags": harx_lags or [1, 5, 22],
        "unit_root_lags": unit_root_lags,
        "trend": trend,
        "portfolio_objective": portfolio_objective,
        "cvar_beta": cvar_beta,
        "cdar_beta": cdar_beta,
        "split_ratio": split_ratio,
        "n_estimators": n_estimators,
        "learning_rate": learning_rate,
        "num_leaves": num_leaves,
        "iterations": iterations,
        "depth": depth,
        "treated_unit": treated_unit,
        "control_units": control_units or [],
        "treatment_time": treatment_time,
        "treatment_time_column": treatment_time_column,
        "treatment_index": treatment_index,
        "intervention_at": intervention_at,
        "draws": draws,
        "tune": tune,
        "chains": chains,
        "template_id": template_id,
        "template_name": template_name,
        "variant_label": variant_label,
        "variant_spec": variant_spec,
        "effective_specification": effective_specification,
    }

    def attach(payload: dict[str, Any]) -> dict[str, Any]:
        family = _infer_model_family(normalized_model)
        payload["workflow_type"] = "model"
        payload.setdefault("model_family", family)
        specification = payload.get("specification")
        if not isinstance(specification, dict):
            specification = {}
        base_specification = dict(effective_specification or {}) if isinstance(effective_specification, dict) else {}
        specification = {
            **base_specification,
            **specification,
        }
        specification.setdefault("model_family", family)
        specification.setdefault("model_type", normalized_model)
        if template_id:
            specification.setdefault("template_id", template_id)
        if template_name:
            specification.setdefault("template_name", template_name)
        if variant_label:
            specification.setdefault("variant_label", variant_label)
        if isinstance(variant_spec, dict) and variant_spec:
            specification.setdefault("variant_spec", dict(variant_spec))
        payload["specification"] = specification
        payload["interpretation"] = _build_model_result_interpretation(payload)
        payload["template_id"] = template_id
        payload["template_name"] = template_name
        payload["variant_label"] = variant_label
        payload["variant_spec"] = dict(variant_spec or {}) if isinstance(variant_spec, dict) else {}
        if not payload.get("result_record_id"):
            asset_title = ((payload.get("asset") or {}).get("title") or "dataset").strip()
            record = create_knowledge_record(
                db,
                user=user,
                workspace=workspace,
                title=f"{payload.get('model_label', 'Model')} summary for {asset_title}",
                content="\n".join(payload.get("narrative") or [f"{payload.get('model_label', 'Model')} completed."]),
                tags=[normalized_model, family, "dataset"],
                metadata=payload,
            )
            payload.setdefault("result_record_id", record.id)
            payload.setdefault("result_detail_path", f"/data-lab/results/models/{record.id}")
        payload["detail_path"] = payload.get("result_detail_path") or ""
        payload["status"] = "ready"
        payload["reason"] = "Model result is ready for review."
        payload["next_action"] = "open_detail"
        payload["template_source"] = template_name or template_id
        payload["variant_source"] = variant_label or ("custom" if isinstance(variant_spec, dict) and variant_spec else "")
        return payload

    try:
        from .model_engine_runtime import has_candidate, run_candidate_model_analysis, run_extension_model_analysis, supports_model
        from .model_engine_selection import get_winning_engine
    except Exception:
        has_candidate = None
        run_candidate_model_analysis = None
        supports_model = None
        run_extension_model_analysis = None
        get_winning_engine = None

    if (
        has_candidate
        and run_candidate_model_analysis
        and get_winning_engine
        and has_candidate(normalized_model)
        and get_winning_engine(normalized_model) != "baseline"
    ):
        return attach(
            run_candidate_model_analysis(
                settings,
                db,
                model_type=normalized_model,
                user=user,
                workspace=workspace,
                **runtime_options,
            )
        )

    if supports_model and run_extension_model_analysis and supports_model(normalized_model):
        return attach(
            run_extension_model_analysis(
                settings,
                db,
                model_type=normalized_model,
                user=user,
                workspace=workspace,
                **runtime_options,
            )
        )

    if normalized_model == "ols":
        return attach(
            run_ols_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "logit":
        return attach(
            run_logit_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "probit":
        return attach(
            run_probit_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "ppml":
        return attach(
            run_ppml_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "arima":
        return attach(
            run_arima_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                time_column=time_column,
                arima_order=(int(arima_p), int(arima_d), int(arima_q)),
                forecast_steps=int(forecast_steps),
            )
        )
    if normalized_model in {"arch", "garch"}:
        return attach(
            run_arch_garch_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                dependent=dependent,
                time_column=time_column,
                p=int(garch_p),
                q=int(garch_q),
                forecast_steps=int(forecast_steps),
            )
        )
    if normalized_model == "var":
        return attach(
            run_var_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                series_columns=series_columns or [],
                time_column=time_column,
                lags=int(var_lags),
                forecast_steps=int(forecast_steps),
            )
        )
    if normalized_model == "svar_irf":
        return attach(
            run_svar_irf_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                series_columns=series_columns or [],
                time_column=time_column,
                lags=int(var_lags),
                horizon=int(irf_horizon),
                impulse_column=impulse_column,
                response_column=response_column,
            )
        )
    if normalized_model == "virf":
        return attach(
            run_virf_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                time_column=time_column,
                p=int(garch_p),
                q=int(garch_q),
                horizon=int(irf_horizon),
                shock_size=float(virf_shock_size),
            )
        )
    if normalized_model == "dy_connectedness":
        return attach(
            run_dy_connectedness_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                series_columns=series_columns or [],
                time_column=time_column,
                lags=int(var_lags),
                horizon=int(irf_horizon),
            )
        )
    if normalized_model == "bk_connectedness":
        return attach(
            run_bk_connectedness_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                series_columns=series_columns or [],
                time_column=time_column,
                lags=int(var_lags),
                short_horizon=int(bk_short_horizon),
                medium_horizon=int(bk_medium_horizon),
            )
        )
    if normalized_model == "did":
        return attach(
            run_did_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                treatment_column=treatment_column,
                post_column=post_column,
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "event_study":
        return attach(
            run_event_study_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                treatment_column=treatment_column,
                event_time_column=event_time_column,
                controls=controls or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                lead_window=lead_window,
                lag_window=lag_window,
                omitted_period=omitted_period,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "fixed_effects":
        return attach(
            run_fixed_effects_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "gravity":
        return attach(
            run_gravity_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                flow_column=dependent,
                origin_mass_column=origin_mass_column,
                destination_mass_column=destination_mass_column,
                distance_column=distance_column,
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "rdd":
        return attach(
            run_rdd_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                running_column=running_column,
                controls=controls or [],
                cutoff=cutoff,
                bandwidth=bandwidth,
                polynomial_order=polynomial_order,
                treat_above_cutoff=treat_above_cutoff,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model in {"historical_var", "parametric_var", "ewma_volatility"}:
        return attach(
            run_risk_metric_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                return_column=dependent,
                time_column=time_column,
                confidence_level=confidence_level,
                holding_period_days=holding_period_days,
                ewma_lambda=ewma_lambda,
            )
        )
    if normalized_model == "iv_2sls":
        return attach(
            run_iv_2sls_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                endogenous_column=endogenous_column,
                instrument_columns=instrument_columns or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "panel_iv":
        return attach(
            run_panel_iv_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                independents=independents or [],
                controls=controls or [],
                endogenous_column=endogenous_column,
                instrument_columns=instrument_columns or [],
                entity_column=entity_column,
                time_column=time_column,
                include_time_effects=include_time_effects,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model in {"black_scholes", "binomial_option"}:
        return attach(
            run_option_pricing_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                spot_column=spot_column,
                strike_column=strike_column,
                maturity_column=maturity_column,
                rate_column=rate_column,
                volatility_column=volatility_column,
                option_type=option_type,
                option_steps=option_steps,
            )
        )
    if normalized_model == "taylor_rule":
        return attach(
            run_taylor_rule_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                dependent=dependent,
                inflation_gap_column=inflation_gap_column,
                output_gap_column=output_gap_column,
                controls=controls or [],
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "rbc_dsge":
        return attach(
            run_rbc_dsge_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                alpha=dsge_alpha,
                beta=dsge_beta,
                delta=dsge_delta,
                productivity=dsge_productivity,
                labor=dsge_labor,
                shock_persistence=dsge_shock_persistence,
                shock_size=dsge_shock_size,
                impulse_horizon=dsge_impulse_horizon,
            )
        )
    if normalized_model in {"mean_variance", "minimum_variance", "risk_parity"}:
        return attach(
            run_portfolio_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                series_columns=series_columns or [],
                risk_aversion=risk_aversion,
                long_only=long_only,
            )
        )
    if normalized_model in {"capm", "fama_french_3"}:
        return attach(
            run_asset_pricing_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                model_type=normalized_model,
                asset_return_column=dependent,
                market_column=market_column,
                risk_free_column=risk_free_column,
                smb_column=smb_column,
                hml_column=hml_column,
                robust_covariance=robust_covariance,
            )
        )
    if normalized_model == "altman_z":
        return attach(
            run_altman_z_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                working_capital_column=working_capital_column,
                retained_earnings_column=retained_earnings_column,
                ebit_column=ebit_column,
                market_equity_column=market_equity_column,
                sales_column=sales_column,
                total_assets_column=total_assets_column,
                total_liabilities_column=total_liabilities_column,
            )
        )
    if normalized_model == "dupont":
        return attach(
            run_dupont_analysis(
                settings,
                db,
                user=user,
                workspace=workspace,
                asset_id=asset_id,
                net_income_column=net_income_column,
                revenue_column=revenue_column,
                total_assets_column=total_assets_column,
                equity_column=equity_column,
            )
        )
    raise ValueError("Unsupported model type.")


def create_plot_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_id: str,
    chart_type: str,
    x_column: str,
    y_columns: list[str] | None = None,
    group_column: str = "",
    title: str = "",
    max_points: int = 400,
) -> dict[str, Any]:
    asset = _analysis_asset_or_raise(db, user=user, workspace=workspace, asset_id=asset_id)
    frame, _ = _load_analysis_frame(settings, asset, drop_duplicates=False)
    normalized_chart_type = chart_type.strip().lower()
    y_columns = [column for column in (y_columns or []) if column]
    if x_column and x_column not in frame.columns:
        raise ValueError(f"Missing X column: {x_column}")
    for column in [*y_columns, group_column]:
        if column and column not in frame.columns:
            raise ValueError(f"Missing column: {column}")

    figure, axis = _pyplot().subplots(figsize=(10, 6), dpi=160)
    figure.patch.set_facecolor("#fffdf8")
    axis.set_facecolor("#fffdf8")
    summary = ""

    if normalized_chart_type == "histogram":
        if not x_column:
            raise ValueError("Histogram requires one numeric column.")
        numeric = pd.to_numeric(frame[x_column], errors="coerce").dropna()
        if numeric.empty:
            raise ValueError("Selected histogram variable has no numeric observations.")
        axis.hist(numeric, bins=min(24, max(8, int(np.sqrt(len(numeric))))), color="#0b5f45", alpha=0.85, edgecolor="#f4efe6")
        axis.set_xlabel(x_column)
        axis.set_ylabel("Count")
        summary = f"Histogram of {x_column} using {len(numeric)} observations."
    elif normalized_chart_type == "bar":
        if not x_column or not y_columns:
            raise ValueError("Bar chart requires both X and Y columns.")
        y_column = y_columns[0]
        plot_frame = frame[[x_column, y_column]].copy()
        plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna().copy()
        grouped = plot_frame.groupby(x_column, dropna=False)[y_column].mean().sort_values(ascending=False).head(20)
        if grouped.empty:
            raise ValueError("Selected bar chart inputs do not produce usable data.")
        axis.bar(range(len(grouped)), grouped.values, color="#0b5f45")
        axis.set_xticks(range(len(grouped)))
        axis.set_xticklabels(grouped.index.astype(str), rotation=35, ha="right")
        axis.set_xlabel(x_column)
        axis.set_ylabel(f"Mean {y_column}")
        summary = f"Bar chart of mean {y_column} by {x_column}."
    elif normalized_chart_type == "scatter":
        if not x_column or not y_columns:
            raise ValueError("Scatter chart requires both X and Y columns.")
        y_column = y_columns[0]
        plot_frame = frame[[x_column, y_column] + ([group_column] if group_column else [])].copy()
        plot_frame[x_column] = pd.to_numeric(plot_frame[x_column], errors="coerce")
        plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna(subset=[x_column, y_column]).head(max_points).copy()
        if plot_frame.empty:
            raise ValueError("Selected scatter variables have no numeric overlap.")
        if group_column:
            for label, chunk in plot_frame.groupby(group_column):
                axis.scatter(chunk[x_column], chunk[y_column], alpha=0.7, label=str(label)[:30])
            axis.legend(loc="best")
        else:
            axis.scatter(plot_frame[x_column], plot_frame[y_column], alpha=0.72, color="#0b5f45")
        axis.set_xlabel(x_column)
        axis.set_ylabel(y_column)
        summary = f"Scatter plot of {y_column} against {x_column}."
    else:
        if not x_column or not y_columns:
            raise ValueError("Line chart requires an X column and at least one Y column.")
        plot_columns = [x_column, *y_columns]
        plot_frame = frame[plot_columns].copy()
        x_role = infer_column_role(plot_frame[x_column])
        if x_role == "date":
            plot_frame[x_column] = _coerce_date_series(plot_frame[x_column])
        else:
            numeric_x = pd.to_numeric(plot_frame[x_column], errors="coerce")
            if numeric_x.notna().sum():
                plot_frame[x_column] = numeric_x
        for y_column in y_columns:
            plot_frame[y_column] = pd.to_numeric(plot_frame[y_column], errors="coerce")
        plot_frame = plot_frame.dropna().head(max_points).copy()
        if plot_frame.empty:
            raise ValueError("Selected line chart variables do not produce usable observations.")
        plot_frame = plot_frame.sort_values(by=x_column)
        for y_column in y_columns:
            axis.plot(plot_frame[x_column], plot_frame[y_column], marker="o", linewidth=1.8, label=y_column)
        if len(y_columns) > 1:
            axis.legend(loc="best")
        axis.set_xlabel(x_column)
        axis.set_ylabel("Value")
        summary = f"Line chart for {', '.join(y_columns)} over {x_column}."

    axis.set_title(title.strip() or summary)
    axis.grid(alpha=0.18, linestyle="--")
    figure.tight_layout()

    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    _pyplot().close(figure)
    payload = buffer.getvalue()
    plot_asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{Path(asset.title).stem}-{normalized_chart_type or 'chart'}.png",
        content=payload,
        content_type="image/png",
        description=f"{normalized_chart_type.title()} chart generated from {asset.title}",
    )
    plot_asset.kind = "chart_png"
    plot_asset.metadata_json = {
        **plot_asset.metadata_json,
        "analysis_kind": "plot",
        "workflow_type": "data_processing",
        "processing_family": "visualization",
        "source_asset_id": asset.id,
        "chart_type": normalized_chart_type or "line",
        "x_column": x_column,
        "y_columns": y_columns,
        "group_column": group_column,
        "summary": summary,
        "result_detail_path": f"/data-lab/results/processing/{plot_asset.id}",
    }
    db.flush()
    return {
        "workflow_type": "data_processing",
        "processing_family": "visualization",
        "asset": serialize_asset(plot_asset),
        "chart_type": normalized_chart_type or "line",
        "title": title.strip() or summary,
        "summary": summary,
        "download_url": f"/api/assets/{plot_asset.id}/download",
        "result_detail_path": f"/data-lab/results/processing/{plot_asset.id}",
        "detail_path": f"/data-lab/results/processing/{plot_asset.id}",
        "status": "ready",
        "reason": "Visualization result is ready for review.",
        "next_action": "open_detail",
        "plot_specification": {
            "chart_type": normalized_chart_type or "line",
            "x_column": x_column,
            "y_columns": y_columns,
            "group_column": group_column,
            "title": title.strip() or summary,
            "max_points": int(max_points),
        },
        "audit_trail": {
            "source_asset_id": asset.id,
            "source_asset_title": asset.title,
            "plot_asset_id": plot_asset.id,
            "download_url": f"/api/assets/{plot_asset.id}/download",
            "manual_checklist": [
                "Download the plotted image and the source sample asset.",
                "Recreate the chart using the listed chart_type, x_column, y_columns, and group_column.",
                "Compare the visible point counts or grouped bars against the summary and source sample.",
            ],
        },
    }
