from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .entities import (
    AgentRun,
    KnowledgeCase,
    KnowledgeCaseItem,
    KnowledgeRecord,
    PublicationRecord,
    Team,
    TeamLibraryRecord,
    TeamMember,
    User,
    Workspace,
)
from .utils import slugify, truncate_text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin_role(role: str) -> bool:
    return role.strip().lower() in {"owner", "admin"}


def serialize_team(team: Team, *, role: str = "") -> dict[str, Any]:
    return {
        "id": team.id,
        "owner_user_id": team.owner_user_id,
        "name": team.name,
        "slug": team.slug,
        "description": team.description,
        "role": role,
        "created_at": team.created_at.isoformat(),
        "updated_at": team.updated_at.isoformat(),
    }


def create_team(db: Session, *, user: User, name: str, description: str = "") -> Team:
    team = Team(
        owner_user_id=user.id,
        name=name.strip(),
        slug=slugify(name),
        description=description.strip(),
    )
    db.add(team)
    db.flush()
    db.add(
        TeamMember(
            team_id=team.id,
            user_id=user.id,
            role="owner",
        )
    )
    db.flush()
    return team


def _membership_for_user(db: Session, *, user: User, team_id: str) -> TeamMember:
    membership = db.scalar(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user.id,
            )
        )
    )
    if membership is None:
        raise FileNotFoundError("Team not found.")
    return membership


def get_team_for_user(db: Session, *, user: User, team_id: str) -> Team:
    membership = _membership_for_user(db, user=user, team_id=team_id)
    team = db.get(Team, membership.team_id)
    if team is None:
        raise FileNotFoundError("Team not found.")
    return team


def get_team_admin_for_user(db: Session, *, user: User, team_id: str) -> Team:
    membership = _membership_for_user(db, user=user, team_id=team_id)
    if not _is_admin_role(membership.role):
        raise PermissionError("Team admin access required.")
    team = db.get(Team, membership.team_id)
    if team is None:
        raise FileNotFoundError("Team not found.")
    return team


def list_teams_for_user(db: Session, *, user: User) -> list[dict[str, Any]]:
    memberships = list(
        db.scalars(
            select(TeamMember)
            .where(TeamMember.user_id == user.id)
            .order_by(TeamMember.created_at.asc())
        )
    )
    items: list[dict[str, Any]] = []
    for membership in memberships:
        team = db.get(Team, membership.team_id)
        if team is None:
            continue
        items.append(serialize_team(team, role=membership.role))
    return items


def attach_workspace_to_team(db: Session, *, user: User, workspace: Workspace, team_id: str) -> Workspace:
    get_team_admin_for_user(db, user=user, team_id=team_id)
    if workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    workspace.team_id = team_id
    db.flush()
    return workspace


def serialize_team_library_record(record: TeamLibraryRecord) -> dict[str, Any]:
    metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    return {
        "id": record.id,
        "team_id": record.team_id,
        "source_type": record.source_type,
        "source_ref_id": record.source_ref_id,
        "source_workspace_id": record.source_workspace_id,
        "source_owner_user_id": record.source_owner_user_id,
        "title": record.title,
        "summary": record.summary,
        "content_excerpt": truncate_text(record.content or "", 280),
        "metadata": metadata,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def list_team_library_records(db: Session, *, user: User, team_id: str) -> list[TeamLibraryRecord]:
    get_team_for_user(db, user=user, team_id=team_id)
    return list(
        db.scalars(
            select(TeamLibraryRecord)
            .where(TeamLibraryRecord.team_id == team_id)
            .order_by(TeamLibraryRecord.updated_at.desc())
        )
    )


def get_team_library_record_for_user(db: Session, *, user: User, team_id: str, record_id: str) -> TeamLibraryRecord:
    get_team_for_user(db, user=user, team_id=team_id)
    record = db.scalar(
        select(TeamLibraryRecord).where(
            and_(
                TeamLibraryRecord.id == record_id,
                TeamLibraryRecord.team_id == team_id,
            )
        )
    )
    if record is None:
        raise FileNotFoundError("Team library record not found.")
    return record


def _knowledge_case_to_markdown(db: Session, case: KnowledgeCase) -> str:
    items = list(
        db.scalars(
            select(KnowledgeCaseItem)
            .where(KnowledgeCaseItem.case_id == case.id)
            .order_by(KnowledgeCaseItem.created_at.asc())
        )
    )
    lines = [
        f"# {case.title}",
        "",
        case.description or "No description provided.",
        "",
        "## Case Items",
    ]
    if not items:
        lines.append("- No linked items.")
    for item in items:
        label = item.title_snapshot or item.ref_id
        summary = item.summary_snapshot or "No summary."
        lines.append(f"- **{item.item_type}**: {label}")
        lines.append(f"  - {summary}")
    return "\n".join(lines).strip()


def _resolve_publish_source(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    source_type: str,
    source_ref_id: str,
) -> tuple[str, str, str, dict[str, Any]]:
    normalized_type = source_type.strip().lower()
    if normalized_type == "agent_run":
        run = db.scalar(
            select(AgentRun).where(
                and_(
                    AgentRun.id == source_ref_id,
                    AgentRun.owner_user_id == user.id,
                    AgentRun.workspace_id == workspace.id,
                )
            )
        )
        if run is None:
            raise FileNotFoundError("Agent run not found.")
        if run.status != "saved":
            raise ValueError("Only saved research runs can be published.")
        title = f"Research Report: {run.topic}"
        summary = str((run.review_json or {}).get("summary") or "").strip() or truncate_text(run.final_text or "", 180)
        content = run.final_text or ""
        metadata = {
            "source_type": "agent_run",
            "agent_run_id": run.id,
            "selected_draft_id": run.selected_draft_id or "",
            "report_path": run.report_path,
            "runtime_bundle_id": run.runtime_bundle_id,
            "runtime_bundle_version": run.runtime_bundle_version or "",
            "quality_summary": dict(run.quality_json or {}) if isinstance(run.quality_json, dict) else {},
            "stage_providers": dict(run.stage_provider_json or {}) if isinstance(run.stage_provider_json, dict) else {},
            "publish_status": run.publish_status,
            "review_summary": str((run.review_json or {}).get("summary") or "").strip(),
            "evidence_summary": {
                "source_count": len((run.evidence_json or {}).get("included_source_ids", []) if isinstance(run.evidence_json, dict) else []),
                "attachment_count": len(run.attachment_json or []),
            },
            "detail_path": f"/research-agent?run={run.id}",
        }
        return title, summary, content, metadata
    if normalized_type == "knowledge_record":
        record = db.scalar(
            select(KnowledgeRecord).where(
                and_(
                    KnowledgeRecord.id == source_ref_id,
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                )
            )
        )
        if record is None:
            raise FileNotFoundError("Knowledge record not found.")
        metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
        metadata.update(
            {
                "source_type": "knowledge_record",
                "knowledge_record_id": record.id,
                "detail_path": "/knowledge-base",
            }
        )
        return record.title, truncate_text(record.content or "", 180), record.content or "", metadata
    if normalized_type == "knowledge_case":
        case = db.scalar(
            select(KnowledgeCase).where(
                and_(
                    KnowledgeCase.id == source_ref_id,
                    KnowledgeCase.owner_user_id == user.id,
                    KnowledgeCase.workspace_id == workspace.id,
                )
            )
        )
        if case is None:
            raise FileNotFoundError("Knowledge case not found.")
        content = _knowledge_case_to_markdown(db, case)
        metadata = {
            "source_type": "knowledge_case",
            "knowledge_case_id": case.id,
            "detail_path": "/knowledge-base",
        }
        return case.title, truncate_text(case.description or content, 180), content, metadata
    raise ValueError("Unsupported publish source type.")


def publish_workspace_source_to_team_library(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    team_id: str,
    source_type: str,
    source_ref_id: str,
    title_override: str = "",
    summary_override: str = "",
) -> TeamLibraryRecord:
    team = get_team_admin_for_user(db, user=user, team_id=team_id)
    title, summary, content, metadata = _resolve_publish_source(
        db,
        user=user,
        workspace=workspace,
        source_type=source_type,
        source_ref_id=source_ref_id,
    )
    record = db.scalar(
        select(TeamLibraryRecord).where(
            and_(
                TeamLibraryRecord.team_id == team.id,
                TeamLibraryRecord.source_type == source_type,
                TeamLibraryRecord.source_ref_id == source_ref_id,
            )
        )
    )
    if record is None:
        record = TeamLibraryRecord(
            team_id=team.id,
            source_type=source_type,
            source_ref_id=source_ref_id,
            source_workspace_id=workspace.id,
            source_owner_user_id=user.id,
            title=title_override.strip() or title,
            summary=summary_override.strip() or summary,
            content=content,
            metadata_json=metadata,
        )
        db.add(record)
        db.flush()
    else:
        record.title = title_override.strip() or title
        record.summary = summary_override.strip() or summary
        record.content = content
        record.metadata_json = metadata
        record.updated_at = _utc_now()
        db.flush()
    db.add(
        PublicationRecord(
            team_library_record_id=record.id,
            team_id=team.id,
            source_type=source_type,
            source_ref_id=source_ref_id,
            source_workspace_id=workspace.id,
            source_owner_user_id=user.id,
            published_by_user_id=user.id,
            metadata_json=metadata,
        )
    )
    if source_type == "agent_run":
        run = db.get(AgentRun, source_ref_id)
        if run is not None:
            run.publish_status = "published"
            run.published_at = _utc_now()
    db.flush()
    return record


def clone_team_library_record_to_workspace(
    db: Session,
    *,
    user: User,
    target_workspace: Workspace,
    record: TeamLibraryRecord,
    title_override: str = "",
    include_source_metadata: bool = True,
) -> KnowledgeRecord:
    if target_workspace.owner_user_id != user.id:
        raise FileNotFoundError("Workspace not found.")
    metadata = {
        "source_type": "team_library_clone",
        "team_library_record_id": record.id,
        "team_id": record.team_id,
        "published_source_type": record.source_type,
        "published_source_ref_id": record.source_ref_id,
    }
    if include_source_metadata:
        metadata["publication"] = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    cloned = KnowledgeRecord(
        workspace_id=target_workspace.id,
        owner_user_id=user.id,
        title=title_override.strip() or record.title,
        content=record.content,
        tags_json=["team-library", record.source_type],
        metadata_json=metadata,
    )
    db.add(cloned)
    db.flush()
    return cloned
