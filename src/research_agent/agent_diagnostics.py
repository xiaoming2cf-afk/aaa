from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .entities import AgentRun, User, Workspace


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, list) else []


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    end = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
    return round(max((end - start).total_seconds(), 0.0), 3)


def list_agent_runs(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    limit: int = 20,
    status: str = "",
    current_stage: str = "",
) -> list[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(
            and_(
                AgentRun.owner_user_id == user.id,
                AgentRun.workspace_id == workspace.id,
            )
        )
        .order_by(AgentRun.started_at.desc(), AgentRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    normalized_status = status.strip().lower()
    if normalized_status:
        stmt = stmt.where(AgentRun.status == normalized_status)
    normalized_stage = current_stage.strip().lower()
    if normalized_stage:
        stmt = stmt.where(AgentRun.current_stage == normalized_stage)
    return list(db.scalars(stmt))


def get_owned_agent_run(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    run_id: str,
) -> AgentRun:
    run = db.scalar(
        select(AgentRun).where(
            and_(
                AgentRun.id == run_id,
                AgentRun.owner_user_id == user.id,
                AgentRun.workspace_id == workspace.id,
            )
        )
    )
    if run is None:
        raise FileNotFoundError("Agent run not found.")
    return run


def serialize_agent_run(
    run: AgentRun,
    *,
    delivery_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context_json = _json_dict(run.context_json)
    input_json = _json_dict(run.input_json)
    attachment_json = _json_list(run.attachment_json)
    plan_json = _json_dict(run.plan_json)
    evidence_json = _json_dict(run.evidence_json)
    review_json = _json_dict(run.review_json)
    metrics_json = _json_dict(run.metrics_json)
    trace_json = _json_list(run.trace_json)
    candidate_drafts = _json_list(run.candidate_drafts_json)

    source_ids = [str(item) for item in evidence_json.get("included_source_ids", []) if str(item).strip()]
    findings = _json_list(review_json.get("findings"))
    delivery_payload = delivery_review
    if delivery_payload is None:
        quality_json = _json_dict(run.quality_json)
        candidate_payload = quality_json.get("delivery_review") if isinstance(quality_json.get("delivery_review"), dict) else quality_json
        delivery_payload = candidate_payload if isinstance(candidate_payload, dict) and candidate_payload.get("resource_id") else None
    if delivery_payload is None:
        from .quality_center import build_agent_run_delivery_review

        delivery_payload = build_agent_run_delivery_review(run)
    return {
        "id": run.id,
        "session_id": run.session_id,
        "topic": run.topic,
        "question": run.question,
        "language": run.language,
        "status": run.status,
        "current_stage": run.current_stage,
        "queue_status": run.queue_status,
        "context_summary": str(context_json.get("summary") or "").strip(),
        "review_status": str(review_json.get("status") or "").strip(),
        "review_summary": str(review_json.get("summary") or "").strip(),
        "source_count": len(source_ids),
        "attachment_count": len(attachment_json),
        "finding_count": len(findings),
        "trace_event_count": len(trace_json),
        "draft_attempts": int(metrics_json.get("draft_attempts") or 0),
        "candidate_draft_count": len(candidate_drafts),
        "citation_coverage": metrics_json.get("citation_coverage"),
        "tool_choice_correctness": metrics_json.get("tool_choice_correctness"),
        "unsupported_claim_count": int(
            metrics_json.get("unsupported_claim_count") or review_json.get("unsupported_claim_count") or 0
        ),
        "selected_draft_id": run.selected_draft_id or "",
        "workspace_knowledge_record_id": run.workspace_knowledge_record_id,
        "workspace_case_id": run.workspace_case_id,
        "publish_status": run.publish_status,
        "mode": str(input_json.get("mode") or "").strip(),
        "report_path": run.report_path,
        "bibtex_path": run.bibtex_path,
        "sources_path": run.sources_path,
        "worker_id": run.worker_id,
        "worker_heartbeat_at": _iso(run.worker_heartbeat_at),
        "runtime_bundle_id": run.runtime_bundle_id,
        "runtime_bundle_version": run.runtime_bundle_version or "",
        "quality_summary": _json_dict(run.quality_json),
        "delivery_review": delivery_payload,
        "publish_allowed": bool(delivery_payload.get("publish_allowed")),
        "blocking_reasons": list(delivery_payload.get("blocking_reasons") or []),
        "started_at": _iso(run.started_at),
        "queued_at": _iso(run.queued_at),
        "claimed_at": _iso(run.claimed_at),
        "lease_expires_at": _iso(run.lease_expires_at),
        "finished_at": _iso(run.finished_at),
        "published_at": _iso(run.published_at),
        "duration_seconds": _duration_seconds(run.started_at, run.finished_at),
        "created_at": _iso(run.created_at),
        "updated_at": _iso(run.updated_at),
    }


def serialize_agent_run_detail(
    run: AgentRun,
    *,
    delivery_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = serialize_agent_run(run, delivery_review=delivery_review)
    payload.update(
        {
            "context": _json_dict(run.context_json),
            "input": _json_dict(run.input_json),
            "attachments": _json_list(run.attachment_json),
            "plan": _json_dict(run.plan_json),
            "evidence": _json_dict(run.evidence_json),
            "review": _json_dict(run.review_json),
            "metrics": _json_dict(run.metrics_json),
            "candidate_drafts": _json_list(run.candidate_drafts_json),
            "trace": _json_list(run.trace_json),
            "runtime_profile": _json_dict(run.runtime_profile_json),
            "stage_providers": _json_dict(run.stage_provider_json),
            "quality": _json_dict(run.quality_json),
            "final_text": run.final_text or "",
            "previous_response_ids": _json_dict(run.metrics_json).get("previous_response_ids", {}),
        }
    )
    return payload


def build_agent_eval_candidate(run: AgentRun) -> dict[str, Any]:
    input_json = _json_dict(run.input_json)
    attachment_json = _json_list(run.attachment_json)
    plan_json = _json_dict(run.plan_json)
    evidence_json = _json_dict(run.evidence_json)
    review_json = _json_dict(run.review_json)
    metrics_json = _json_dict(run.metrics_json)
    context_json = _json_dict(run.context_json)
    candidate_drafts = _json_list(run.candidate_drafts_json)
    trace_json = _json_list(run.trace_json)

    required_sections = [str(item) for item in plan_json.get("required_sections", []) if str(item).strip()]
    source_ids = [str(item) for item in evidence_json.get("included_source_ids", []) if str(item).strip()]
    missing_sections = [str(item) for item in review_json.get("missing_sections", []) if str(item).strip()]
    invalid_source_ids = [str(item) for item in review_json.get("invalid_source_ids", []) if str(item).strip()]
    unsupported_claim_count = int(
        metrics_json.get("unsupported_claim_count") or review_json.get("unsupported_claim_count") or 0
    )
    citation_coverage = float(metrics_json.get("citation_coverage") or 0.0)
    reviewer_approved = str(review_json.get("status") or "").strip().lower() == "approved"
    tool_choice_correctness = metrics_json.get("tool_choice_correctness")
    if tool_choice_correctness is None:
        attachment_only = bool(attachment_json) and not any(str(source_id).startswith("S") for source_id in source_ids)
        completed_tool_calls = [
            item
            for item in trace_json
            if str(item.get("event") or "").strip() == "tool_completed"
        ]
        tool_choice_correctness = 1.0 if completed_tool_calls or attachment_only else 0.0
    needs_human_annotation = bool(
        run.status != "saved"
        or not reviewer_approved
        or unsupported_claim_count > 0
        or invalid_source_ids
        or missing_sections
        or citation_coverage < 0.75
    )
    ready_for_prompt_optimizer = bool(
        reviewer_approved
        and run.status == "saved"
        and unsupported_claim_count == 0
        and not invalid_source_ids
        and not missing_sections
    )

    return {
        "run_id": run.id,
        "session_id": run.session_id,
        "item": {
            "topic": run.topic,
            "question": run.question,
            "language": run.language,
            "workspace_context_summary": str(context_json.get("summary") or "").strip(),
            "required_sections": required_sections,
            "allowed_source_ids": source_ids,
            "mode": str(input_json.get("mode") or "").strip(),
            "attachment_ids": [str(item.get("asset_id") or "").strip() for item in attachment_json if str(item.get("asset_id") or "").strip()],
            "report_markdown": run.final_text or "",
            "review_summary": str(review_json.get("summary") or "").strip(),
        },
        "grader_scores": {
            "citation_coverage": citation_coverage,
            "unsupported_claim_count": unsupported_claim_count,
            "missing_section_count": len(missing_sections),
            "invalid_source_id_count": len(invalid_source_ids),
            "reviewer_approved": reviewer_approved,
            "draft_attempts": int(metrics_json.get("draft_attempts") or 0),
            "candidate_draft_count": len(candidate_drafts),
            "tool_choice_correctness": tool_choice_correctness,
            "reviewer_human_agreement": metrics_json.get("reviewer_human_agreement"),
        },
        "grader_labels": {
            "needs_human_annotation": needs_human_annotation,
            "ready_for_prompt_optimizer": ready_for_prompt_optimizer,
            "run_status": run.status,
            "review_status": str(review_json.get("status") or "").strip(),
        },
        "metadata": {
            "report_path": run.report_path,
            "selected_draft_id": run.selected_draft_id or "",
            "workspace_knowledge_record_id": run.workspace_knowledge_record_id,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
        },
    }


def build_agent_eval_dataset_preview(runs: list[AgentRun]) -> dict[str, Any]:
    items = [
        build_agent_eval_candidate(run)
        for run in runs
        if (run.status or "").strip().lower() in {"saved", "blocked", "failed"}
    ]
    ready_count = sum(1 for item in items if item["grader_labels"]["ready_for_prompt_optimizer"])
    needs_annotation_count = sum(1 for item in items if item["grader_labels"]["needs_human_annotation"])
    approved_count = sum(1 for item in items if item["grader_labels"]["review_status"] == "approved")
    blocked_count = sum(1 for item in items if item["grader_labels"]["review_status"] == "blocked")
    return {
        "dataset_version": "research-agent-v2",
        "items": items,
        "summary": {
            "count": len(items),
            "ready_for_prompt_optimizer_count": ready_count,
            "needs_human_annotation_count": needs_annotation_count,
            "approved_count": approved_count,
            "blocked_count": blocked_count,
        },
    }
