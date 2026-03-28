from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class Settings(BaseModel):
    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "Economic Research Platform"))
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    app_secret: str = Field(
        default_factory=lambda: os.getenv("APP_SECRET", "development-secret-change-me")
    )
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = Field(default_factory=lambda: os.getenv("RESEARCH_AGENT_MODEL", "gpt-5-mini"))
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
    session_ttl_hours: int = Field(default_factory=lambda: int(os.getenv("SESSION_TTL_HOURS", "720")))
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


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
