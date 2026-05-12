from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fitz
from markdown import markdown
from rich.console import Console
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .agent_diagnostics import build_agent_eval_candidate, get_owned_agent_run, serialize_agent_run_detail
from .agent_run_store import AgentRunContext, AgentRunStore
from .asset_storage import load_asset_bytes
from .config import Settings
from .entities import AgentRun, DataAsset, User, Workspace
from .orchestrator import ResearchOrchestrator
from .platform_core import add_item_to_knowledge_case, create_knowledge_record
from .quality_center import (
    build_delivery_scorecard,
    build_run_quality_snapshot,
    load_engineering_gate_report,
    review_agent_run_delivery,
)
from .research_tools import ResearchSession
from .runtime_models import (
    AttachmentPageRef,
    EvidencePack,
    FeatureDisabledError,
    ResearchPlan,
    ResearchRunRequest,
    ResearchRunRetryRequest,
    RunAttachment,
    WorkspaceContextPack,
)
from .utils import slugify, utc_timestamp_slug, write_json
from .workspace_context import build_workspace_context_pack


SESSION_METADATA_FILENAME = ".session.json"
_DEFAULT_AGENT_LEASE_SECONDS = 15 * 60
_RESEARCH_RUNTIME_DISABLED_MESSAGE = (
    "Research generation is not available in this deployment because no inference runtime is configured."
)


def _research_runtime_available(settings: Settings) -> bool:
    return bool(getattr(settings, "research_runtime_enabled", False))


def _research_runtime_disabled_trace(*, queue_created: bool) -> dict[str, Any]:
    return {
        "runtime_available": False,
        "queue_created": queue_created,
        "reason": "inference_runtime_missing",
    }


def research_runtime_capability(settings: Settings) -> dict[str, Any]:
    enabled = _research_runtime_available(settings)
    return {
        "enabled": enabled,
        "code": "available" if enabled else "feature_disabled",
        "message": "" if enabled else _RESEARCH_RUNTIME_DISABLED_MESSAGE,
        "trace": {"runtime_available": True, "queue_created": False}
        if enabled
        else _research_runtime_disabled_trace(queue_created=False),
    }


def _require_research_runtime_available(settings: Settings, *, queue_created: bool = False) -> None:
    if _research_runtime_available(settings):
        return
    raise FeatureDisabledError(
        feature="research_runtime",
        message=_RESEARCH_RUNTIME_DISABLED_MESSAGE,
        trace=_research_runtime_disabled_trace(queue_created=queue_created),
    )


@dataclass
class ResearchRunPayload:
    session_id: str
    session_dir: str
    topic: str
    question: str | None
    language: str
    created_at: str
    access_token: str
    final_text: str
    report_html: str
    report_path: str
    bibtex_path: str
    sources_path: str
    bibtex_content: str
    sources_content: dict[str, Any]
    used_source_ids: list[str]
    tool_trace: list[dict[str, Any]]
    agent_run_id: str = ""
    status: str = "saved"
    current_stage: str = "saved"
    plan_json: dict[str, Any] | None = None
    evidence_json: dict[str, Any] | None = None
    review_json: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    previous_response_ids: dict[str, str] | None = None
    input_json: dict[str, Any] | None = None
    attachment_json: list[dict[str, Any]] | None = None
    candidate_drafts_json: list[dict[str, Any]] | None = None
    selected_draft_id: str | None = None
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_session_id(topic: str) -> str:
    return f"{slugify(topic)}-{utc_timestamp_slug()}-{secrets.token_hex(4)}"


def build_session_dir(reports_dir: Path, topic: str) -> Path:
    session_dir = reports_dir / build_session_id(topic)
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def render_report_html(markdown_content: str) -> str:
    return markdown(
        markdown_content,
        extensions=["extra", "fenced_code", "tables", "toc"],
        output_format="html5",
    )


def session_dir_for_id(reports_dir: Path, session_id: str) -> Path:
    session_dir = (reports_dir / session_id).resolve()
    reports_root = reports_dir.resolve()
    if reports_root not in session_dir.parents or not session_dir.exists():
        raise FileNotFoundError(f"Unknown session: {session_id}")
    return session_dir


def _model_supports_multimodal_inputs(model: str) -> bool:
    lowered = (model or "").strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in ("whisper", "tts", "embedding")):
        return False
    if any(
        token in lowered
        for token in (
            "vision",
            "-vl",
            "vl-",
            "llava",
            "pixtral",
            "gemma3",
            "qwen2.5-vl",
            "qwen-vl",
            "internvl",
            "minicpm-v",
        )
    ):
        return True
    return lowered.startswith(("gpt", "o"))


def _pdf_page_refs(raw_bytes: bytes) -> list[AttachmentPageRef]:
    refs: list[AttachmentPageRef] = []
    try:
        with fitz.open(stream=raw_bytes, filetype="pdf") as document:
            for page_index in range(min(document.page_count, 4)):
                page_text = document.load_page(page_index).get_text("text").strip()
                refs.append(
                    AttachmentPageRef(
                        page_number=page_index + 1,
                        label=f"Page {page_index + 1}",
                        excerpt=page_text[:1600],
                    )
                )
    except Exception:
        return refs
    return refs


def build_run_attachments(
    *,
    settings: Settings,
    assets: list[DataAsset],
    model: str,
) -> list[RunAttachment]:
    supports_multimodal = _model_supports_multimodal_inputs(model)
    attachments: list[RunAttachment] = []
    for index, asset in enumerate(assets, start=1):
        metadata = dict(asset.metadata_json or {})
        caption = str(asset.description or metadata.get("summary") or asset.title or "").strip()
        raw_bytes: bytes | None = None
        input_content: dict[str, Any] | None = None
        page_refs: list[AttachmentPageRef] = []
        if asset.file_path:
            try:
                raw_bytes = load_asset_bytes(settings, asset.file_path)
            except Exception:
                raw_bytes = None
        if asset.kind == "document_pdf" and raw_bytes:
            page_refs = _pdf_page_refs(raw_bytes)
            if supports_multimodal:
                input_content = {
                    "type": "input_file",
                    "filename": metadata.get("original_filename") or asset.title,
                    "file_data": base64.b64encode(raw_bytes).decode("ascii"),
                }
        elif asset.kind in {"chart_png", "image_jpeg"} and raw_bytes and asset.content_type:
            if supports_multimodal:
                input_content = {
                    "type": "input_image",
                    "image_url": f"data:{asset.content_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}",
                    "detail": "high",
                }
        attachments.append(
            RunAttachment(
                source_id=f"A{index}",
                asset_id=asset.id,
                title=asset.title,
                kind=asset.kind,
                mime_type=asset.content_type or "",
                file_name=str(metadata.get("original_filename") or asset.title),
                description=asset.description or "",
                page_refs=page_refs,
                extracted_text=asset.extracted_text or "",
                caption=caption,
                usable_by_vision_model=bool(input_content),
                metadata={
                    "download_path": f"/api/assets/{asset.id}/download",
                    "source_url": asset.source_url or "",
                },
                input_content=input_content,
            )
        )
    return attachments


def normalize_draft_variants(*, requested: int | None, mode: str, attachments: list[RunAttachment]) -> int:
    if requested is not None:
        return max(1, min(int(requested), 3))
    if mode == "deep_research" or attachments:
        return 2
    return 1


def build_agent_report_metadata(
    *,
    run: AgentRun,
    topic: str,
    question: str | None,
    report_path: str,
    selected_draft_id: str | None,
) -> dict[str, Any]:
    plan_json = dict(run.plan_json or {}) if isinstance(run.plan_json, dict) else {}
    evidence_json = dict(run.evidence_json or {}) if isinstance(run.evidence_json, dict) else {}
    review_json = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
    return {
        "source_type": "agent_report",
        "workflow_type": "research_agent",
        "agent_run_id": run.id,
        "report_path": report_path,
        "selected_draft_id": selected_draft_id or "",
        "result_detail_path": f"/research-agent?run={run.id}",
        "research_topic": topic,
        "research_question": question or "",
        "plan_summary": {
            "query_count": len(plan_json.get("queries", []) or []),
            "required_sections": list(plan_json.get("required_sections", []) or []),
        },
        "evidence_summary": {
            "source_count": len(evidence_json.get("included_source_ids", []) or []),
            "attachment_count": len(run.attachment_json or []),
        },
        "review_summary": {
            "status": review_json.get("status", ""),
            "unsupported_claim_count": review_json.get("unsupported_claim_count", 0),
        },
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _queue_context_pack(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    topic: str,
    question: str | None,
) -> WorkspaceContextPack:
    return build_workspace_context_pack(
        db,
        user=user,
        workspace=workspace,
        topic=topic,
        research_question=question,
    )


def _enqueue_agent_run(
    *,
    settings: Settings,
    db: Session,
    user: User,
    workspace: Workspace,
    session_dir: Path,
    topic: str,
    question: str | None,
    language: str,
    input_payload: dict[str, Any],
    attachment_payload: list[dict[str, Any]],
    context_pack: WorkspaceContextPack,
    existing_run: AgentRun | None = None,
    current_stage: str = "planned",
) -> AgentRun:
    now = _utc_now()
    store = AgentRunStore(
        db=db,
        context=AgentRunContext(
            session_id=session_dir.name,
            topic=topic,
            question=question,
            language=language,
            session_dir=session_dir,
            workspace=workspace,
            user=user,
        ),
        existing_record=existing_run,
    )
    store.start(
        status="queued",
        current_stage=current_stage,
        context_json=context_pack.model_dump(mode="json"),
        input_json=input_payload,
        attachment_json=attachment_payload,
        queue_status="queued",
        queued_at=now,
        claimed_at=None,
        lease_expires_at=None,
        worker_id="",
        worker_heartbeat_at=None,
        runtime_profile_json={},
        stage_provider_json={},
        runtime_bundle_id=None,
        runtime_bundle_version="",
        quality_json={},
    )
    run = store.record
    if run is None:
        raise RuntimeError("Failed to enqueue agent run.")
    return run


def _run_payload(
    run: AgentRun,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    engineering_gate = load_engineering_gate_report(settings) if settings is not None else None
    delivery_review, _ = review_agent_run_delivery(
        run,
        settings=settings,
        engineering_gate=engineering_gate,
        auto_refresh_if_missing=False,
    )
    return {
        "run": serialize_agent_run_detail(run, delivery_review=delivery_review),
        "eval_candidate": build_agent_eval_candidate(run) if run.status in {"saved", "blocked", "failed"} else None,
        "poll": {
            "run_id": run.id,
            "queue_status": run.queue_status,
            "status": run.status,
        },
    }


def _prepare_run_attachments(
    *,
    settings: Settings,
    assets: list[DataAsset],
) -> list[RunAttachment]:
    return build_run_attachments(settings=settings, assets=assets, model=settings.model)


def run_research(
    *,
    settings: Settings,
    topic: str,
    question: str | None = None,
    language: str = "Chinese",
    instructions: str = "",
    attachments: list[RunAttachment] | None = None,
    draft_variants: int = 1,
    mode: str = "standard",
    session_dir: Path | None = None,
    input_payload: dict[str, Any] | None = None,
    existing_run: AgentRun | None = None,
    plan_override: dict[str, Any] | None = None,
    evidence_override: dict[str, Any] | None = None,
    context_override: dict[str, Any] | None = None,
    previous_response_ids: dict[str, str] | None = None,
    api_key: str | None = None,
    console: Console | None = None,
    db: Session | None = None,
    user: User | None = None,
    workspace: Workspace | None = None,
    orchestrator: ResearchOrchestrator | None = None,
) -> ResearchRunPayload:
    runtime_settings = settings.with_api_key(api_key)
    runtime_session_dir = session_dir or build_session_dir(settings.reports_dir, topic)
    if (runtime_session_dir / SESSION_METADATA_FILENAME).exists():
        metadata = load_session_metadata(runtime_session_dir)
        created_at = str(metadata.get("created_at") or datetime.now(timezone.utc).isoformat())
        access_token = ""
    else:
        access_token, created_at = create_session_access(session_dir=runtime_session_dir, topic=topic)
    session = ResearchSession(session_dir=runtime_session_dir)
    update_session_metadata(
        runtime_session_dir,
        question=question,
        language=language,
    )
    runtime = orchestrator or ResearchOrchestrator(
        settings=runtime_settings,
        session=session,
        db=db,
        user=user,
        workspace=workspace,
    )
    result = runtime.run(
        topic=topic,
        research_question=question,
        preferred_language=language,
        attachments=list(attachments or []),
        draft_variants=max(1, draft_variants),
        mode=mode,
        additional_instructions=instructions,
        input_payload=input_payload,
        existing_run=existing_run,
        plan_override=plan_override and ResearchPlan.model_validate(plan_override),
        evidence_override=evidence_override and EvidencePack.model_validate(evidence_override),
        context_pack_override=context_override and WorkspaceContextPack.model_validate(context_override),
        previous_response_ids=previous_response_ids,
    )
    report_path = Path(result.report_path)
    bibtex_path = Path(result.bibtex_path)
    sources_path = Path(result.sources_path)
    final_text = report_path.read_text(encoding="utf-8") if report_path.exists() else result.final_text
    bibtex_content = bibtex_path.read_text(encoding="utf-8") if bibtex_path.exists() else ""
    sources_content = (
        json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    )
    return ResearchRunPayload(
        session_id=runtime_session_dir.name,
        session_dir=str(runtime_session_dir),
        topic=topic,
        question=question,
        language=language,
        created_at=created_at,
        access_token=access_token,
        final_text=final_text,
        report_html=render_report_html(final_text),
        report_path=str(report_path),
        bibtex_path=str(bibtex_path),
        sources_path=str(sources_path),
        bibtex_content=bibtex_content,
        sources_content=sources_content,
        used_source_ids=result.used_source_ids,
        tool_trace=result.tool_trace,
        agent_run_id=result.agent_run_id,
        status=result.status,
        current_stage=result.current_stage,
        plan_json=result.plan_json,
        evidence_json=result.evidence_json,
        review_json=result.review_json,
        metrics_json=result.metrics_json,
        previous_response_ids=result.previous_response_ids,
        input_json=result.input_json,
        attachment_json=result.attachment_json,
        candidate_drafts_json=result.candidate_drafts_json,
        selected_draft_id=result.selected_draft_id,
        error_message=result.error_message,
    )


def _owned_assets_for_run(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset_ids: list[str],
) -> list[DataAsset]:
    assets: list[DataAsset] = []
    seen: set[str] = set()
    for asset_id in asset_ids:
        normalized_id = str(asset_id or "").strip()
        if not normalized_id or normalized_id in seen:
            continue
        seen.add(normalized_id)
        asset = db.get(DataAsset, normalized_id)
        if asset is None or asset.owner_user_id != user.id or asset.workspace_id != workspace.id:
            raise FileNotFoundError(f"Asset not found: {normalized_id}")
        assets.append(asset)
    return assets


def _auto_save_agent_report(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    run: AgentRun,
    topic: str,
    question: str | None,
    report_markdown: str,
    report_path: str,
    case_id: str | None,
) -> None:
    metadata = build_agent_report_metadata(
        run=run,
        topic=topic,
        question=question,
        report_path=report_path,
        selected_draft_id=run.selected_draft_id or "",
    )
    record = create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Research Report: {topic}",
        content=report_markdown,
        tags=["research", "agent-report", workspace.research_domain or "workspace"],
        metadata=metadata,
    )
    run.workspace_knowledge_record_id = record.id
    if case_id:
        add_item_to_knowledge_case(
            db,
            user=user,
            workspace=workspace,
            case_id=case_id,
            item_type="knowledge_record",
            ref_id=record.id,
            metadata={"source_kind": "agent_report", "agent_run_id": run.id},
        )
        run.workspace_case_id = case_id
    db.flush()


def start_workspace_research_run(
    *,
    settings: Settings,
    db: Session,
    user: User,
    workspace: Workspace,
    request: ResearchRunRequest,
) -> dict[str, Any]:
    _require_research_runtime_available(settings)
    assets = _owned_assets_for_run(db, user=user, workspace=workspace, asset_ids=request.asset_ids)
    attachments = _prepare_run_attachments(
        settings=settings,
        assets=assets,
    )
    draft_variants = normalize_draft_variants(
        requested=request.draft_variants,
        mode=request.mode,
        attachments=attachments,
    )
    normalized_input = request.model_dump(mode="json")
    normalized_input["draft_variants"] = draft_variants
    session_dir = build_session_dir(settings.reports_dir, request.topic)
    create_session_access(session_dir=session_dir, topic=request.topic)
    update_session_metadata(session_dir, question=request.question, language="Chinese")
    run = _enqueue_agent_run(
        settings=settings,
        db=db,
        user=user,
        workspace=workspace,
        session_dir=session_dir,
        topic=request.topic,
        question=request.question,
        language="Chinese",
        input_payload=normalized_input,
        attachment_payload=[attachment.model_dump(mode="json", exclude={"input_content"}) for attachment in attachments],
        context_pack=_queue_context_pack(
            db,
            user=user,
            workspace=workspace,
            topic=request.topic,
            question=request.question,
        ),
    )
    return _run_payload(run, settings=settings)


def retry_workspace_research_run(
    *,
    settings: Settings,
    db: Session,
    user: User,
    workspace: Workspace,
    run: AgentRun,
    request: ResearchRunRetryRequest,
) -> dict[str, Any]:
    current_stage = (run.current_stage or "").strip().lower()
    if current_stage not in {"drafting", "reviewing", "blocked"} and (run.status or "").strip().lower() != "blocked":
        raise ValueError("Retry is only available for blocked or in-progress drafting runs.")
    _require_research_runtime_available(settings)
    existing_input = dict(run.input_json or {}) if isinstance(run.input_json, dict) else {}
    combined_asset_ids = list(existing_input.get("asset_ids") or []) + list(request.asset_ids or [])
    assets = _owned_assets_for_run(db, user=user, workspace=workspace, asset_ids=combined_asset_ids)
    merged_instructions = "\n".join(
        item.strip()
        for item in [str(existing_input.get("instructions") or ""), request.instructions]
        if str(item or "").strip()
    )
    attachments = _prepare_run_attachments(
        settings=settings,
        assets=assets,
    )
    normalized_input = {
        **existing_input,
        "asset_ids": [asset.id for asset in assets],
        "instructions": merged_instructions,
        "retry_instructions": request.instructions,
        "draft_variants": normalize_draft_variants(
            requested=request.draft_variants or existing_input.get("draft_variants"),
            mode=str(existing_input.get("mode") or "standard"),
            attachments=attachments,
        ),
    }
    session_dir = session_dir_for_id(settings.reports_dir, run.session_id)
    update_session_metadata(session_dir, question=run.question or None, language=run.language or "Chinese")
    queued_run = _enqueue_agent_run(
        settings=settings,
        db=db,
        user=user,
        workspace=workspace,
        session_dir=session_dir,
        topic=run.topic,
        question=run.question or None,
        language=run.language or "Chinese",
        input_payload=normalized_input,
        attachment_payload=[attachment.model_dump(mode="json", exclude={"input_content"}) for attachment in attachments],
        context_pack=WorkspaceContextPack.model_validate(run.context_json or {})
        if isinstance(run.context_json, dict) and run.context_json
        else _queue_context_pack(
            db,
            user=user,
            workspace=workspace,
            topic=run.topic,
            question=run.question or None,
        ),
        existing_run=run,
        current_stage="drafting",
    )
    return _run_payload(queued_run, settings=settings)


def _refresh_run_quality_snapshot(
    db: Session,
    *,
    settings: Settings | None,
    user: User,
    workspace: Workspace,
    run: AgentRun,
) -> dict[str, Any]:
    engineering_gate = load_engineering_gate_report(settings) if settings is not None else None
    review_agent_run_delivery(run, settings=settings, engineering_gate=engineering_gate)
    snapshot = build_run_quality_snapshot(run, engineering_gate=engineering_gate)
    scorecard = build_delivery_scorecard(
        db,
        user=user,
        workspace=workspace,
        settings=settings,
        engineering_gate=engineering_gate,
    )
    run.quality_json = dict(run.quality_json or {}) if isinstance(run.quality_json, dict) else snapshot
    metrics_json = dict(run.metrics_json or {}) if isinstance(run.metrics_json, dict) else {}
    metrics_json["workspace_score_snapshot"] = {
        "total_score": scorecard.get("total_score", 0),
        "business_deliverable": scorecard.get("business_deliverable", False),
        "deliverable": scorecard.get("deliverable", False),
        "blocked_actions": list(scorecard.get("blocked_actions") or []),
        "reviewed_at": scorecard.get("generated_at", _utc_now().isoformat()),
    }
    run.metrics_json = metrics_json
    db.flush()
    return snapshot


def claim_queued_agent_run(
    *,
    db: Session,
    worker_id: str,
    lease_seconds: int = _DEFAULT_AGENT_LEASE_SECONDS,
) -> AgentRun | None:
    now = _utc_now()
    run = (
        db.query(AgentRun)
        .filter(
            or_(
                AgentRun.queue_status == "queued",
                and_(AgentRun.queue_status == "claimed", AgentRun.lease_expires_at.is_not(None), AgentRun.lease_expires_at < now),
            )
        )
        .order_by(AgentRun.queued_at.asc(), AgentRun.created_at.asc())
        .first()
    )
    if run is None:
        return None
    run.queue_status = "claimed"
    run.claimed_at = now
    run.lease_expires_at = now + timedelta(seconds=max(60, lease_seconds))
    run.worker_id = worker_id.strip() or "research-worker"
    run.worker_heartbeat_at = now
    if run.status == "queued":
        run.status = "running"
    db.flush()
    return run


def process_claimed_agent_run(
    *,
    settings: Settings,
    db: Session,
    run: AgentRun,
) -> dict[str, Any]:
    if not run.workspace_id or not run.owner_user_id:
        raise RuntimeError("Queued run is missing workspace ownership.")
    workspace = db.get(Workspace, run.workspace_id)
    user = db.get(User, run.owner_user_id)
    if workspace is None or user is None:
        raise FileNotFoundError("Queued run owner or workspace no longer exists.")

    run.worker_heartbeat_at = _utc_now()
    run.runtime_profile_json = {}
    run.stage_provider_json = {}
    run.runtime_bundle_id = None
    run.runtime_bundle_version = ""
    db.flush()
    _require_research_runtime_available(settings, queue_created=True)
    raise RuntimeError("Research runtime was reported available but no worker implementation is registered.")


def fail_claimed_agent_run(
    *,
    db: Session,
    run: AgentRun,
    message: str,
) -> AgentRun:
    run.status = "failed"
    run.current_stage = "failed"
    run.queue_status = "failed"
    run.lease_expires_at = None
    run.worker_heartbeat_at = _utc_now()
    run.finished_at = _utc_now()
    metrics_json = dict(run.metrics_json or {}) if isinstance(run.metrics_json, dict) else {}
    metrics_json["worker_error"] = message
    run.metrics_json = metrics_json
    run.review_json = {
        "status": "failed",
        "summary": message,
        "findings": [],
        "missing_sections": [],
        "invalid_source_ids": [],
        "unsupported_claim_count": 0,
    }
    run.quality_json = build_run_quality_snapshot(run)
    db.flush()
    return run


def run_agent_worker_iteration(
    *,
    settings: Settings,
    db: Session,
    worker_id: str = "research-worker",
) -> dict[str, Any] | None:
    run = claim_queued_agent_run(db=db, worker_id=worker_id)
    if run is None:
        return None
    try:
        return process_claimed_agent_run(settings=settings, db=db, run=run)
    except Exception as exc:
        failed_run = fail_claimed_agent_run(db=db, run=run, message=str(exc))
        if failed_run.owner_user_id and failed_run.workspace_id:
            workspace = db.get(Workspace, failed_run.workspace_id)
            user = db.get(User, failed_run.owner_user_id)
            if workspace is not None and user is not None:
                _refresh_run_quality_snapshot(db, settings=settings, user=user, workspace=workspace, run=failed_run)
        return _run_payload(failed_run, settings=settings)


def load_report_session(
    reports_dir: Path,
    session_id: str,
    access_token: str,
) -> ResearchRunPayload:
    session_dir = resolve_session_dir(reports_dir, session_id)
    metadata = require_session_access(session_dir=session_dir, access_token=access_token)

    sources_path = session_dir / "sources.json"
    report_path = session_dir / "report.md"
    bibtex_path = session_dir / "references.bib"
    sources_content = (
        json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    )
    final_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    topic = sources_content.get("topic") or metadata.get("topic") or session_id
    return ResearchRunPayload(
        session_id=session_id,
        session_dir=str(session_dir),
        topic=topic,
        question=metadata.get("question"),
        language=metadata.get("language", "Chinese"),
        created_at=metadata["created_at"],
        access_token=access_token,
        final_text=final_text,
        report_html=render_report_html(final_text),
        report_path=str(report_path),
        bibtex_path=str(bibtex_path),
        sources_path=str(sources_path),
        bibtex_content=bibtex_path.read_text(encoding="utf-8") if bibtex_path.exists() else "",
        sources_content=sources_content,
        used_source_ids=sources_content.get("source_ids", []),
        tool_trace=[],
        agent_run_id="",
        status="saved",
        current_stage="saved",
        plan_json=None,
        evidence_json=None,
        review_json=None,
        metrics_json=None,
        previous_response_ids=None,
    )


def create_session_access(session_dir: Path, topic: str) -> tuple[str, str]:
    access_token = secrets.token_urlsafe(24)
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "topic": topic,
        "created_at": created_at,
        "access_token_hash": hash_session_token(access_token),
    }
    write_json(session_dir / SESSION_METADATA_FILENAME, metadata)
    return access_token, created_at


def update_session_metadata(
    session_dir: Path,
    *,
    question: str | None,
    language: str,
) -> None:
    metadata = load_session_metadata(session_dir)
    metadata["question"] = question
    metadata["language"] = language
    write_json(session_dir / SESSION_METADATA_FILENAME, metadata)


def resolve_session_dir(reports_dir: Path, session_id: str) -> Path:
    session_dir = (reports_dir / session_id).resolve()
    reports_root = reports_dir.resolve()
    if reports_root not in session_dir.parents:
        raise FileNotFoundError(f"Unknown session: {session_id}")
    if not session_dir.exists():
        raise FileNotFoundError(f"Unknown session: {session_id}")
    return session_dir


def require_session_access(session_dir: Path, access_token: str) -> dict[str, Any]:
    metadata = load_session_metadata(session_dir)
    expected_hash = metadata.get("access_token_hash", "")
    actual_hash = hash_session_token(access_token)
    if not expected_hash or not hmac.compare_digest(expected_hash, actual_hash):
        raise PermissionError("Invalid session token.")
    return metadata


def load_session_metadata(session_dir: Path) -> dict[str, Any]:
    metadata_path = session_dir / SESSION_METADATA_FILENAME
    if not metadata_path.exists():
        raise FileNotFoundError("Session metadata is missing.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def hash_session_token(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()
