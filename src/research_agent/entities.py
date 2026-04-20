from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    research_domain: Mapped[str] = mapped_column(String(100), default="economics")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (UniqueConstraint("owner_user_id", "label", name="uq_integration_owner_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    label: Mapped[str] = mapped_column(String(120))
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeRecord(Base):
    __tablename__ = "knowledge_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class WorkspaceMemory(Base):
    __tablename__ = "workspace_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeCase(Base):
    __tablename__ = "knowledge_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeCaseItem(Base):
    __tablename__ = "knowledge_case_items"
    __table_args__ = (UniqueConstraint("case_id", "item_type", "ref_id", name="uq_case_item_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("knowledge_cases.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(60), index=True)
    ref_id: Mapped[str] = mapped_column(String(120), index=True)
    title_snapshot: Mapped[str] = mapped_column(String(240), default="")
    summary_snapshot: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class LabTemplate(Base):
    __tablename__ = "lab_templates"
    __table_args__ = (UniqueConstraint("workspace_id", "template_scope", "name", name="uq_lab_template_scope_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_scope: Mapped[str] = mapped_column(String(40), index=True)
    workflow_type: Mapped[str] = mapped_column(String(40), index=True)
    family: Mapped[str] = mapped_column(String(80), default="", index=True)
    method: Mapped[str] = mapped_column(String(80), default="", index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    specification_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class DataAsset(Base):
    __tablename__ = "data_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(800), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(800), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RuntimeProfile(Base):
    __tablename__ = "runtime_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_runtime_profile_workspace_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active_bundle_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_bundles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bindings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    health_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RuntimeBundle(Base):
    __tablename__ = "runtime_bundles"
    __table_args__ = (UniqueConstraint("workspace_id", "version", name="uq_runtime_bundle_workspace_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    prompts_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rubric_json: Mapped[dict] = mapped_column(JSON, default=dict)
    routing_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_thresholds_json: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery_thresholds_json: Mapped[dict] = mapped_column(JSON, default=dict)
    eval_baseline_json: Mapped[dict] = mapped_column(JSON, default=dict)
    score_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TeamLibraryRecord(Base):
    __tablename__ = "team_library_records"
    __table_args__ = (
        UniqueConstraint("team_id", "source_type", "source_ref_id", name="uq_team_library_source_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(60), index=True)
    source_ref_id: Mapped[str] = mapped_column(String(120), index=True)
    source_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PublicationRecord(Base):
    __tablename__ = "publication_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_library_record_id: Mapped[str] = mapped_column(
        ForeignKey("team_library_records.id", ondelete="CASCADE"),
        index=True,
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(60), index=True)
    source_ref_id: Mapped[str] = mapped_column(String(120), index=True)
    source_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DataLabRun(Base):
    __tablename__ = "data_lab_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workflow_type: Mapped[str] = mapped_column(String(40), default="processing", index=True)
    family: Mapped[str] = mapped_column(String(80), default="", index=True)
    method: Mapped[str] = mapped_column(String(80), default="", index=True)
    title: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    source_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    result_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    result_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    detail_path: Mapped[str] = mapped_column(String(400), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class LiteratureEntry(Base):
    __tablename__ = "literature_entries"
    __table_args__ = (UniqueConstraint("workspace_id", "openalex_id", name="uq_workspace_openalex"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    openalex_id: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(Text)
    authors_json: Mapped[list] = mapped_column(JSON, default=list)
    abstract: Mapped[str] = mapped_column(Text, default="")
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi: Mapped[str] = mapped_column(String(255), default="")
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    venue: Mapped[str] = mapped_column(String(255), default="")
    landing_page_url: Mapped[str] = mapped_column(String(800), default="")
    pdf_url: Mapped[str] = mapped_column(String(800), default="")
    keywords_json: Mapped[list] = mapped_column(JSON, default=list)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class EconomicBriefing(Base):
    __tablename__ = "economic_briefings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    summary_markdown: Mapped[str] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text, default="")
    headline_count: Mapped[int] = mapped_column(Integer, default=0)
    items_json: Mapped[list] = mapped_column(JSON, default=list)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PublicEconomicBriefing(Base):
    __tablename__ = "public_economic_briefings"
    __table_args__ = (UniqueConstraint("briefing_date", name="uq_public_briefing_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    briefing_date: Mapped[str] = mapped_column(String(10), index=True)
    timezone_name: Mapped[str] = mapped_column(String(80), default="Asia/Shanghai")
    summary_markdown: Mapped[str] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text, default="")
    template_version: Mapped[str] = mapped_column(String(40), default="daily-macro-v1")
    headline_count: Mapped[int] = mapped_column(Integer, default=0)
    items_json: Mapped[list] = mapped_column(JSON, default=list)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ScheduleJob(Base):
    __tablename__ = "schedule_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    timezone_name: Mapped[str] = mapped_column(String(80), default="UTC")
    local_time: Mapped[str] = mapped_column(String(8), default="08:00")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("schedule_jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    topic: Mapped[str] = mapped_column(String(240), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(40), default="Chinese")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    current_stage: Mapped[str] = mapped_column(String(40), default="planned", index=True)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_json: Mapped[list] = mapped_column(JSON, default=list)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_json: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_json: Mapped[list] = mapped_column(JSON, default=list)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_drafts_json: Mapped[list] = mapped_column(JSON, default=list)
    selected_draft_id: Mapped[str] = mapped_column(String(120), default="")
    queue_status: Mapped[str] = mapped_column(String(40), default="idle", index=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    worker_id: Mapped[str] = mapped_column(String(120), default="")
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    runtime_profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    stage_provider_json: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime_bundle_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_bundles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    runtime_bundle_version: Mapped[str] = mapped_column(String(80), default="", index=True)
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    publish_status: Mapped[str] = mapped_column(String(40), default="unpublished", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    workspace_knowledge_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    final_text: Mapped[str] = mapped_column(Text, default="")
    report_path: Mapped[str] = mapped_column(String(800), default="")
    bibtex_path: Mapped[str] = mapped_column(String(800), default="")
    sources_path: Mapped[str] = mapped_column(String(800), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLogEvent(Base):
    __tablename__ = "audit_log_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    route: Mapped[str] = mapped_column(String(240), default="", index=True)
    method: Mapped[str] = mapped_column(String(12), default="", index=True)
    action: Mapped[str] = mapped_column(String(120), default="", index=True)
    resource_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    resource_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    status: Mapped[str] = mapped_column(String(40), default="ok", index=True)
    ip_address: Mapped[str] = mapped_column(String(120), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (UniqueConstraint("email", "ip_address", name="uq_login_attempt_email_ip"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    ip_address: Mapped[str] = mapped_column(String(120), index=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (UniqueConstraint("bucket_type", "bucket_key", name="uq_rate_limit_bucket"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_type: Mapped[str] = mapped_column(String(80), index=True)
    bucket_key: Mapped[str] = mapped_column(String(500), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
