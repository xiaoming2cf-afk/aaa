from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .audit import audit_event
from .entities import AgentRun, User, Workspace
from .utils import write_json


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentRunContext:
    session_id: str
    topic: str
    question: str | None
    language: str
    session_dir: Path
    workspace: Workspace | None = None
    user: User | None = None


class AgentRunStore:
    def __init__(
        self,
        *,
        db: Session | None,
        context: AgentRunContext,
        existing_record: AgentRun | None = None,
    ) -> None:
        self.db = db
        self.context = context
        self.local_path = context.session_dir / "agent_run.json"
        self.record: AgentRun | None = existing_record

    @property
    def run_id(self) -> str:
        return self.record.id if self.record is not None else self.context.session_id

    def start(
        self,
        *,
        status: str,
        current_stage: str,
        context_json: dict[str, Any],
        input_json: dict[str, Any] | None = None,
        attachment_json: list[dict[str, Any]] | None = None,
        queue_status: str | None = None,
        queued_at: datetime | None = None,
        claimed_at: datetime | None = None,
        lease_expires_at: datetime | None = None,
        worker_id: str | None = None,
        worker_heartbeat_at: datetime | None = None,
        runtime_profile_json: dict[str, Any] | None = None,
        stage_provider_json: dict[str, Any] | None = None,
        runtime_bundle_id: str | None = None,
        runtime_bundle_version: str | None = None,
        quality_json: dict[str, Any] | None = None,
        publish_status: str | None = None,
        published_at: datetime | None = None,
    ) -> None:
        now = _utc_now()
        if self.record is not None:
            self.record.session_id = self.context.session_id
            self.record.topic = self.context.topic
            self.record.question = self.context.question or ""
            self.record.language = self.context.language
            self.record.status = status
            self.record.current_stage = current_stage
            self.record.context_json = context_json
            if input_json is not None:
                self.record.input_json = input_json
            if attachment_json is not None:
                self.record.attachment_json = attachment_json
            if queue_status is not None:
                self.record.queue_status = queue_status
            if queued_at is not None or queue_status == "queued":
                self.record.queued_at = queued_at or now
            if claimed_at is not None or queue_status != "queued":
                self.record.claimed_at = claimed_at
            if lease_expires_at is not None or queue_status != "claimed":
                self.record.lease_expires_at = lease_expires_at
            if worker_id is not None:
                self.record.worker_id = worker_id
            if worker_heartbeat_at is not None:
                self.record.worker_heartbeat_at = worker_heartbeat_at
            if runtime_profile_json is not None:
                self.record.runtime_profile_json = runtime_profile_json
            if stage_provider_json is not None:
                self.record.stage_provider_json = stage_provider_json
            if runtime_bundle_id is not None:
                self.record.runtime_bundle_id = runtime_bundle_id
            if runtime_bundle_version is not None:
                self.record.runtime_bundle_version = runtime_bundle_version
            if quality_json is not None:
                self.record.quality_json = quality_json
            if publish_status is not None:
                self.record.publish_status = publish_status
            if published_at is not None or publish_status != "published":
                self.record.published_at = published_at
            self.record.finished_at = None
            if self.db is not None:
                self.db.flush()
        elif self.db is not None:
            self.record = AgentRun(
                owner_user_id=self.context.user.id if self.context.user else None,
                workspace_id=self.context.workspace.id if self.context.workspace else None,
                session_id=self.context.session_id,
                topic=self.context.topic,
                question=self.context.question or "",
                language=self.context.language,
                status=status,
                current_stage=current_stage,
                context_json=context_json,
                input_json=input_json or {},
                attachment_json=attachment_json or [],
                queue_status=queue_status or "idle",
                queued_at=queued_at,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
                worker_id=worker_id or "",
                worker_heartbeat_at=worker_heartbeat_at,
                runtime_profile_json=runtime_profile_json or {},
                stage_provider_json=stage_provider_json or {},
                runtime_bundle_id=runtime_bundle_id,
                runtime_bundle_version=runtime_bundle_version or "",
                quality_json=quality_json or {},
                publish_status=publish_status or "unpublished",
                published_at=published_at,
                started_at=now,
            )
            self.db.add(self.record)
            self.db.flush()
            if self.context.user and self.context.workspace:
                audit_event(
                    self.db,
                    request=None,
                    action="agent.run.start",
                    status="ok",
                    summary=f"Started agent run for {self.context.topic}",
                    user=self.context.user,
                    workspace=self.context.workspace,
                    resource_type="agent_run",
                    resource_id=self.record.id,
                    metadata={"current_stage": current_stage},
                )
        self._write_local(
            {
                "run_id": self.run_id,
                "workspace_id": self.context.workspace.id if self.context.workspace else None,
                "status": status,
                "current_stage": current_stage,
                "started_at": now.isoformat(),
                "topic": self.context.topic,
                "question": self.context.question,
                "language": self.context.language,
                "context": context_json,
                "input": input_json or {},
                "attachments": attachment_json or [],
                "queue_status": queue_status or "idle",
                "queued_at": (queued_at or now).isoformat() if queue_status == "queued" or queued_at else None,
                "runtime_profile": runtime_profile_json or {},
                "stage_provider": stage_provider_json or {},
                "runtime_bundle_id": runtime_bundle_id or "",
                "runtime_bundle_version": runtime_bundle_version or "",
                "quality": quality_json or {},
            }
        )

    def update(
        self,
        *,
        status: str,
        current_stage: str,
        plan_json: dict[str, Any] | None = None,
        evidence_json: dict[str, Any] | None = None,
        review_json: dict[str, Any] | None = None,
        trace_json: list[dict[str, Any]] | None = None,
        metrics_json: dict[str, Any] | None = None,
        input_json: dict[str, Any] | None = None,
        attachment_json: list[dict[str, Any]] | None = None,
        candidate_drafts_json: list[dict[str, Any]] | None = None,
        selected_draft_id: str | None = None,
        workspace_knowledge_record_id: str | None = None,
        workspace_case_id: str | None = None,
        report_path: str | None = None,
        bibtex_path: str | None = None,
        sources_path: str | None = None,
        final_text: str | None = None,
        queue_status: str | None = None,
        queued_at: datetime | None = None,
        claimed_at: datetime | None = None,
        lease_expires_at: datetime | None = None,
        worker_id: str | None = None,
        worker_heartbeat_at: datetime | None = None,
        runtime_profile_json: dict[str, Any] | None = None,
        stage_provider_json: dict[str, Any] | None = None,
        runtime_bundle_id: str | None = None,
        runtime_bundle_version: str | None = None,
        quality_json: dict[str, Any] | None = None,
        publish_status: str | None = None,
        published_at: datetime | None = None,
        finished: bool = False,
    ) -> None:
        payload = {
            "run_id": self.run_id,
            "workspace_id": self.context.workspace.id if self.context.workspace else None,
            "status": status,
            "current_stage": current_stage,
            "topic": self.context.topic,
            "question": self.context.question,
            "language": self.context.language,
        }
        if plan_json is not None:
            payload["plan"] = plan_json
        if evidence_json is not None:
            payload["evidence"] = evidence_json
        if review_json is not None:
            payload["review"] = review_json
        if trace_json is not None:
            payload["trace"] = trace_json
        if metrics_json is not None:
            payload["metrics"] = metrics_json
        if input_json is not None:
            payload["input"] = input_json
        if attachment_json is not None:
            payload["attachments"] = attachment_json
        if candidate_drafts_json is not None:
            payload["candidate_drafts"] = candidate_drafts_json
        if selected_draft_id is not None:
            payload["selected_draft_id"] = selected_draft_id
        if workspace_knowledge_record_id is not None:
            payload["workspace_knowledge_record_id"] = workspace_knowledge_record_id
        if workspace_case_id is not None:
            payload["workspace_case_id"] = workspace_case_id
        if report_path is not None:
            payload["report_path"] = report_path
        if bibtex_path is not None:
            payload["bibtex_path"] = bibtex_path
        if sources_path is not None:
            payload["sources_path"] = sources_path
        if final_text is not None:
            payload["final_text"] = final_text
        if queue_status is not None:
            payload["queue_status"] = queue_status
        if queued_at is not None:
            payload["queued_at"] = queued_at.isoformat()
        if claimed_at is not None:
            payload["claimed_at"] = claimed_at.isoformat()
        if lease_expires_at is not None:
            payload["lease_expires_at"] = lease_expires_at.isoformat()
        if worker_id is not None:
            payload["worker_id"] = worker_id
        if worker_heartbeat_at is not None:
            payload["worker_heartbeat_at"] = worker_heartbeat_at.isoformat()
        if runtime_profile_json is not None:
            payload["runtime_profile"] = runtime_profile_json
        if stage_provider_json is not None:
            payload["stage_provider"] = stage_provider_json
        if runtime_bundle_id is not None:
            payload["runtime_bundle_id"] = runtime_bundle_id
        if runtime_bundle_version is not None:
            payload["runtime_bundle_version"] = runtime_bundle_version
        if quality_json is not None:
            payload["quality"] = quality_json
        if publish_status is not None:
            payload["publish_status"] = publish_status
        if published_at is not None:
            payload["published_at"] = published_at.isoformat()
        if finished:
            payload["finished_at"] = _utc_now().isoformat()

        if self.record is not None:
            self.record.status = status
            self.record.current_stage = current_stage
            if plan_json is not None:
                self.record.plan_json = plan_json
            if evidence_json is not None:
                self.record.evidence_json = evidence_json
            if review_json is not None:
                self.record.review_json = review_json
            if trace_json is not None:
                self.record.trace_json = trace_json
            if metrics_json is not None:
                self.record.metrics_json = metrics_json
            if input_json is not None:
                self.record.input_json = input_json
            if attachment_json is not None:
                self.record.attachment_json = attachment_json
            if candidate_drafts_json is not None:
                self.record.candidate_drafts_json = candidate_drafts_json
            if selected_draft_id is not None:
                self.record.selected_draft_id = selected_draft_id
            if workspace_knowledge_record_id is not None:
                self.record.workspace_knowledge_record_id = workspace_knowledge_record_id
            if workspace_case_id is not None:
                self.record.workspace_case_id = workspace_case_id
            if report_path is not None:
                self.record.report_path = report_path
            if bibtex_path is not None:
                self.record.bibtex_path = bibtex_path
            if sources_path is not None:
                self.record.sources_path = sources_path
            if final_text is not None:
                self.record.final_text = final_text
            if queue_status is not None:
                self.record.queue_status = queue_status
            if queued_at is not None:
                self.record.queued_at = queued_at
            if claimed_at is not None:
                self.record.claimed_at = claimed_at
            if lease_expires_at is not None:
                self.record.lease_expires_at = lease_expires_at
            if worker_id is not None:
                self.record.worker_id = worker_id
            if worker_heartbeat_at is not None:
                self.record.worker_heartbeat_at = worker_heartbeat_at
            if runtime_profile_json is not None:
                self.record.runtime_profile_json = runtime_profile_json
            if stage_provider_json is not None:
                self.record.stage_provider_json = stage_provider_json
            if runtime_bundle_id is not None:
                self.record.runtime_bundle_id = runtime_bundle_id
            if runtime_bundle_version is not None:
                self.record.runtime_bundle_version = runtime_bundle_version
            if quality_json is not None:
                self.record.quality_json = quality_json
            if publish_status is not None:
                self.record.publish_status = publish_status
            if published_at is not None:
                self.record.published_at = published_at
            if finished:
                self.record.finished_at = _utc_now()
            self.db.flush()
        self._write_local(payload)

    def complete(self, *, status: str, current_stage: str, summary: str, metadata: dict[str, Any]) -> None:
        if self.record is not None and self.db is not None and self.context.user and self.context.workspace:
            audit_event(
                self.db,
                request=None,
                action="agent.run.complete",
                status=status,
                summary=summary,
                user=self.context.user,
                workspace=self.context.workspace,
                resource_type="agent_run",
                resource_id=self.record.id,
                metadata=metadata,
            )
        self._write_local(
            {
                "run_id": self.run_id,
                "status": status,
                "current_stage": current_stage,
                "summary": summary,
                "metadata": metadata,
                "finished_at": _utc_now().isoformat(),
            }
        )

    def _write_local(self, payload: dict[str, Any]) -> None:
        existing: dict[str, Any] = {}
        if self.local_path.exists():
            try:
                import json

                existing = json.loads(self.local_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        existing.update(payload)
        write_json(self.local_path, existing)
