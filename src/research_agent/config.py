from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field

if os.getenv("PYTHON_DOTENV_DISABLED", "").strip().lower() not in {"1", "true", "yes"}:
    load_dotenv(override=False)


_DEV_APP_ENVS = {"development", "dev", "test", "testing"}
_WEAK_APP_SECRETS = {"", "development-secret-change-me", "changeme", "secret", "development-secret"}
_VALID_AGENT_MATH_MODES = {"off", "shadow", "active"}


def _default_app_secret() -> str:
    configured = os.getenv("APP_SECRET", "").strip()
    if configured:
        return configured
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env in _DEV_APP_ENVS:
        return secrets.token_urlsafe(32)
    return ""


class Settings(BaseModel):
    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "Economic Research Platform"))
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    app_secret: str = Field(default_factory=_default_app_secret)
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = Field(default_factory=lambda: os.getenv("RESEARCH_AGENT_MODEL", "qwen2.5:7b-instruct"))
    reasoning_effort: str = Field(
        default_factory=lambda: os.getenv("RESEARCH_AGENT_REASONING_EFFORT", "medium")
    )
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./storage/platform.db")
    )
    storage_dir: Path = Field(default_factory=lambda: Path(os.getenv("STORAGE_DIR", "storage")))
    asset_storage_backend: str = Field(
        default_factory=lambda: os.getenv("ASSET_STORAGE_BACKEND", "local")
    )
    supabase_url: str = Field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_service_role_key: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    supabase_storage_bucket: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_STORAGE_BUCKET", "research-assets")
    )
    reports_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("RESEARCH_AGENT_REPORTS_DIR", "storage/reports"))
    )
    max_tool_calls: int = Field(
        default_factory=lambda: int(os.getenv("RESEARCH_AGENT_MAX_TOOL_CALLS", "12"))
    )
    public_base_url: str = Field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", ""))
    encryption_key: str = Field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", ""))
    cron_secret: str = Field(default_factory=lambda: os.getenv("CRON_SECRET", ""))
    session_ttl_hours: int = Field(default_factory=lambda: int(os.getenv("SESSION_TTL_HOURS", "72")))
    allowed_origins: str = Field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "").strip())
    trusted_proxy_ips: str = Field(default_factory=lambda: os.getenv("TRUSTED_PROXY_IPS", "").strip())
    smtp_host: str = Field(default_factory=lambda: os.getenv("SMTP_HOST", "").strip())
    smtp_port: int = Field(default_factory=lambda: int(os.getenv("SMTP_PORT", "465")))
    smtp_username: str = Field(default_factory=lambda: os.getenv("SMTP_USERNAME", "").strip())
    smtp_password: str = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD", "").strip())
    smtp_from_email: str = Field(default_factory=lambda: os.getenv("SMTP_FROM_EMAIL", "").strip())
    smtp_security: str = Field(
        default_factory=lambda: (os.getenv("SMTP_SECURITY", "ssl").strip().lower() or "ssl")
    )
    password_reset_ttl_minutes: int = Field(
        default_factory=lambda: int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
    )
    db_pool_size: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "8")))
    db_max_overflow: int = Field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "16")))
    db_pool_timeout: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30")))
    db_pool_recycle: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_RECYCLE", "1800")))
    gdelt_query: str = Field(
        default_factory=lambda: os.getenv(
            "GDELT_QUERY",
            '"inflation" OR "interest rate" OR "central bank" OR "bond yield" OR "oil price" '
            'OR "tariff" OR "unemployment" OR "recession" OR "GDP" OR "trade"',
        )
    )
    gdelt_max_records: int = Field(
        default_factory=lambda: int(os.getenv("GDELT_MAX_RECORDS", "15"))
    )
    default_fred_series: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_FRED_SERIES", "FEDFUNDS,CPIAUCSL,UNRATE,DGS10")
    )
    fred_api_key: str = Field(default_factory=lambda: os.getenv("FRED_API_KEY", ""))
    public_digest_enabled: bool = Field(
        default_factory=lambda: os.getenv("PUBLIC_DIGEST_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    )
    public_digest_timezone: str = Field(
        default_factory=lambda: os.getenv("PUBLIC_DIGEST_TIMEZONE", "Asia/Shanghai")
    )
    public_digest_local_time: str = Field(
        default_factory=lambda: os.getenv("PUBLIC_DIGEST_LOCAL_TIME", "08:30")
    )
    public_digest_title: str = Field(
        default_factory=lambda: os.getenv("PUBLIC_DIGEST_TITLE", "Global Economic Daily")
    )
    public_digest_query: str = Field(default_factory=lambda: os.getenv("PUBLIC_DIGEST_QUERY", "").strip())
    public_digest_max_records: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DIGEST_MAX_RECORDS", "30"))
    )
    data_lab_agent_enabled: bool = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    data_lab_agent_max_attempts: int = Field(
        default_factory=lambda: int(os.getenv("DATA_LAB_AGENT_MAX_ATTEMPTS", "3"))
    )
    data_lab_agent_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("DATA_LAB_AGENT_TIMEOUT_SECONDS", "20"))
    )
    data_lab_agent_output_limit: int = Field(
        default_factory=lambda: int(os.getenv("DATA_LAB_AGENT_OUTPUT_LIMIT", "12000"))
    )
    data_lab_agent_execution_mode: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_EXECUTION_MODE", "subprocess_replay").strip().lower()
    )
    data_lab_agent_ipython_enabled: bool = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_IPYTHON_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    data_lab_agent_llm_enabled: bool = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_LLM_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    data_lab_agent_llm_base_url: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_LLM_BASE_URL", "").strip()
    )
    data_lab_agent_llm_api_key: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_LLM_API_KEY", "").strip()
    )
    data_lab_agent_coder_model: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_CODER_MODEL", "").strip()
    )
    data_lab_agent_reviewer_model: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_REVIEWER_MODEL", "").strip()
    )
    data_lab_agent_report_model: str = Field(
        default_factory=lambda: os.getenv("DATA_LAB_AGENT_REPORT_MODEL", "").strip()
    )
    data_lab_agent_llm_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("DATA_LAB_AGENT_LLM_TIMEOUT_SECONDS", "45"))
    )
    agent_math_mode: str = Field(
        default_factory=lambda: os.getenv("AGENT_MATH_MODE", "off").strip().lower()
    )
    agent_math_delivery_threshold: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_MATH_DELIVERY_THRESHOLD", "0.85"))
    )
    agent_math_human_threshold: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_MATH_HUMAN_THRESHOLD", "0.55"))
    )
    agent_math_override_margin: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_MATH_OVERRIDE_MARGIN", "0.05"))
    )

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///./"):
            relative_path = self.database_url.removeprefix("sqlite:///./")
            Path(relative_path).parent.mkdir(parents=True, exist_ok=True)
        elif self.database_url.startswith("sqlite:///"):
            absolute_path = self.database_url.removeprefix("sqlite:///")
            Path(absolute_path).parent.mkdir(parents=True, exist_ok=True)

    def with_api_key(self, api_key: str | None = None) -> "Settings":
        runtime_key = (api_key or "").strip()
        return self.model_copy(
            update={
                "openai_api_key": runtime_key or self.openai_api_key,
            }
        )

    @property
    def has_server_api_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def uses_supabase_asset_storage(self) -> bool:
        return self.asset_storage_backend.strip().lower() == "supabase"

    @property
    def has_supabase_storage_config(self) -> bool:
        return bool(
            self.supabase_url.strip()
            and self.supabase_service_role_key.strip()
            and self.supabase_storage_bucket.strip()
        )

    def get_encryption_key(self) -> bytes:
        source = self.encryption_key.strip() or self.app_secret
        digest = hashlib.sha256(source.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def get_cron_secret(self) -> str:
        if self.cron_secret.strip():
            return self.cron_secret
        return hashlib.sha256(f"{self.app_secret}:cron".encode("utf-8")).hexdigest()

    @property
    def is_development_env(self) -> bool:
        return self.app_env.strip().lower() in _DEV_APP_ENVS

    @property
    def has_strong_app_secret(self) -> bool:
        return self.app_secret.strip() not in _WEAK_APP_SECRETS

    @property
    def allowed_origin_list(self) -> list[str]:
        values: list[str] = []
        for raw in self.allowed_origins.split(","):
            value = raw.strip()
            if value:
                values.append(value)
        if self.public_base_url.strip():
            parsed = urlsplit(self.public_base_url.strip())
            if parsed.scheme and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if origin not in values:
                    values.append(origin)
        return values

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        values: list[str] = []
        for raw in self.trusted_proxy_ips.split(","):
            value = raw.strip()
            if value:
                values.append(value)
        return values

    @property
    def smtp_is_configured(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_port > 0
            and self.smtp_from_email
            and self.smtp_username
            and self.smtp_password
        )

    @property
    def smtp_uses_ssl(self) -> bool:
        return self.smtp_security == "ssl"

    def validate_runtime_configuration(self) -> None:
        if not self.is_development_env and not self.has_strong_app_secret:
            raise RuntimeError("APP_SECRET must be changed before running outside development/test.")
        if self.smtp_security not in {"ssl", "starttls"}:
            raise RuntimeError("SMTP_SECURITY must be one of: ssl, starttls.")
        if self.password_reset_ttl_minutes <= 0:
            raise RuntimeError("PASSWORD_RESET_TTL_MINUTES must be greater than zero.")
        if self.agent_math_mode not in _VALID_AGENT_MATH_MODES:
            raise RuntimeError("AGENT_MATH_MODE must be one of: off, shadow, active.")
        if not 0.0 <= self.agent_math_delivery_threshold <= 1.0:
            raise RuntimeError("AGENT_MATH_DELIVERY_THRESHOLD must be between 0.0 and 1.0.")
        if not 0.0 <= self.agent_math_human_threshold <= 1.0:
            raise RuntimeError("AGENT_MATH_HUMAN_THRESHOLD must be between 0.0 and 1.0.")
        if not 0.0 <= self.agent_math_override_margin <= 1.0:
            raise RuntimeError("AGENT_MATH_OVERRIDE_MARGIN must be between 0.0 and 1.0.")


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    settings.validate_runtime_configuration()
    return settings
