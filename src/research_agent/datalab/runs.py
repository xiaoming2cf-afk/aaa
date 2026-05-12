from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from research_agent.entities import DataAsset, DataLabRun, KnowledgeRecord, User, Workspace
from research_agent.utils import truncate_text

from .registry import normalize_workflow_type


JsonSafe = Callable[[Any], Any]
EnsureUtc = Callable[[datetime | None], datetime | None]
AssetSerializer = Callable[[DataAsset], dict[str, Any]]
RecordSerializer = Callable[[KnowledgeRecord], dict[str, Any]]


def create_run(
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
    json_safe: JsonSafe,
) -> DataLabRun:
    normalized_workflow = normalize_workflow_type(workflow_type)
    run = DataLabRun(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        workflow_type=normalized_workflow,
        family=str(family or "").strip(),
        method=str(method or "").strip(),
        title=truncate_text(str(title or "").strip(), 240),
        source_asset_id=str(source_asset_id or "").strip() or None,
        request_json=json_safe(dict(request_payload or {}) if isinstance(request_payload, dict) else {}),
    )
    db.add(run)
    db.flush()
    return run


def get_owned_run(db: Session, *, user: User, run_id: str) -> DataLabRun:
    run = db.get(DataLabRun, run_id)
    if not run or run.owner_user_id != user.id:
        raise FileNotFoundError("Data Lab run not found.")
    return run


def finalize_run_success(
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
    json_safe: JsonSafe,
) -> DataLabRun:
    run = get_owned_run(db, user=user, run_id=run_id)
    run.status = "ready"
    if title.strip():
        run.title = truncate_text(title.strip(), 240)
    run.summary = truncate_text(str(summary or "").strip(), 600)
    run.detail_path = str(detail_path or "").strip()
    run.result_asset_id = str(result_asset_id or "").strip() or None
    run.result_record_id = str(result_record_id or "").strip() or None
    run.error_summary = ""
    run.output_json = json_safe(dict(output_payload or {}) if isinstance(output_payload, dict) else {})
    run.finished_at = datetime.now(timezone.utc)
    run.updated_at = run.finished_at
    db.flush()
    return run


def finalize_run_failure(
    db: Session,
    *,
    user: User,
    run_id: str,
    error: Exception | str,
    title: str = "",
    output_payload: dict[str, Any] | None = None,
    json_safe: JsonSafe,
) -> DataLabRun:
    run = get_owned_run(db, user=user, run_id=run_id)
    run.status = "failed"
    if title.strip():
        run.title = truncate_text(title.strip(), 240)
    run.error_summary = truncate_text(str(error or "Data Lab run failed.").strip(), 600) or "Data Lab run failed."
    run.output_json = json_safe(dict(output_payload or {}) if isinstance(output_payload, dict) else {})
    run.finished_at = datetime.now(timezone.utc)
    run.updated_at = run.finished_at
    db.flush()
    return run


def list_runs(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    workflow_type: str = "",
    limit: int = 24,
) -> list[DataLabRun]:
    normalized_workflow = normalize_workflow_type(workflow_type) if workflow_type else ""
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
    if normalized_workflow:
        rows = [row for row in rows if row.workflow_type == normalized_workflow]
    return rows


def serialize_run(
    db: Session,
    *,
    user: User,
    run: DataLabRun,
    ensure_utc: EnsureUtc,
    serialize_asset: AssetSerializer,
    serialize_record: RecordSerializer,
) -> dict[str, Any]:
    output = dict(run.output_json or {}) if isinstance(run.output_json, dict) else {}
    updated_at = ensure_utc(run.finished_at) or ensure_utc(run.updated_at) or ensure_utc(run.started_at)
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
        "request_json": dict(run.request_json or {}) if isinstance(run.request_json, dict) else {},
        "ref_id": "",
        "download_path": "",
        "created_at": (ensure_utc(run.started_at) or datetime.now(timezone.utc)).isoformat(),
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
        return {**base, "reason": reason, "next_action": "review_failure"}

    if run.workflow_type == "agent_session":
        session = output.get("agent_session") if isinstance(output.get("agent_session"), dict) else {}
        return {
            **base,
            "summary": str(session.get("summary") or run.summary or "").strip(),
            "reason": str(session.get("summary") or run.summary or "Data Lab Agent session is ready.").strip(),
            "next_action": "open_detail",
            "message_count": len(session.get("messages") or []),
            "cell_count": len(session.get("cells") or []),
            "artifact_count": len(session.get("artifacts") or []),
            "metadata": {
                "workflow_type": "agent_session",
                "agent_family": run.family,
                "agent_method": run.method,
            },
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
            payload = serialize_record(record)
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
