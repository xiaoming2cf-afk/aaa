from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy.orm import Session

from .agent_math import score_candidate_review, settings_math_mode
from .agent_run_store import AgentRunContext, AgentRunStore
from .config import Settings
from .entities import AgentRun, User, Workspace
from .models import WorkRecord
from .orchestration_prompts import (
    PLANNER_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    WRITER_INSTRUCTIONS,
)
from .research_tools import ResearchSession, tool_result_json
from .runtime_models import (
    AgentRunTraceEvent,
    CandidateDraftSummary,
    EvidenceItem,
    EvidencePack,
    ResearchPlan,
    ResearchQuery,
    RunAttachment,
    ReviewFinding,
    ReviewModelFeedback,
    ReviewReport,
    WorkspaceContextPack,
)
from .utils import extract_source_ids, truncate_text, unique_preserve_order
from .workspace_context import build_workspace_context_pack


T = TypeVar("T")

DEFAULT_REQUIRED_SECTIONS = [
    "Topic",
    "Research Question",
    "Executive Summary",
    "Key Papers",
    "Methodological Patterns",
    "Research Gaps",
    "Suggested Next Reads",
    "References",
]

_NON_RESEARCH_PATTERNS = (
    "logo",
    "slogan",
    "advertisement",
    "ad copy",
    "tweet thread",
    "wedding speech",
    "travel itinerary",
    "recipe",
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response_output_text(response: Any) -> str:
    if getattr(response, "output_text", ""):
        return response.output_text

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) == "output_text":
                chunks.append(content.text)
    return "\n".join(chunks)


def _section_present(text: str, heading: str) -> bool:
    escaped = re.escape(heading.strip())
    return bool(
        re.search(rf"(?im)^\s*#+\s*{escaped}\s*$", text)
        or re.search(rf"(?im)^\s*{escaped}\s*$", text)
    )


def _missing_sections(text: str, required_sections: list[str]) -> list[str]:
    return [section for section in required_sections if not _section_present(text, section)]


def _unsupported_claim_count(text: str) -> int:
    count = 0
    current_section = ""
    for block in re.split(r"\n\s*\n", text):
        snippet = block.strip()
        if not snippet:
            continue

        heading_match = re.match(r"^\s*#+\s*(.+?)\s*$", snippet.splitlines()[0])
        if heading_match:
            current_section = heading_match.group(1).strip().lower()
            continue

        if current_section in {"topic", "research question", "references"}:
            continue

        normalized = re.sub(r"\s+", " ", snippet)
        if normalized.startswith(("- ", "* ", "|", "```")):
            continue
        if len(normalized) < 100:
            continue
        if not re.search(r"\[S\d+\]", normalized):
            count += 1
    return count


def _research_scope_issue(topic: str, question: str | None) -> str | None:
    combined = " ".join([topic or "", question or ""]).strip()
    if len(combined) < 8:
        return "Research topic is too short to plan reliably."
    lowered = combined.lower()
    for pattern in _NON_RESEARCH_PATTERNS:
        if pattern in lowered:
            return "Request appears outside the supported research workflow scope."
    return None


def _format_review_feedback(review: ReviewReport) -> str:
    lines = [review.summary or "The reviewer blocked the previous draft."]
    for finding in review.findings[:6]:
        lines.append(f"- [{finding.severity}] {finding.code}: {finding.message}")
    return "\n".join(lines)


def _dedupe_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ReviewFinding] = []
    for finding in findings:
        key = (finding.severity, finding.code, finding.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _safe_attachment_payload(attachments: list[RunAttachment]) -> list[dict[str, Any]]:
    return [attachment.model_dump(mode="json", exclude={"input_content"}) for attachment in attachments]


def _attachment_prompt_lines(attachments: list[RunAttachment]) -> list[str]:
    if not attachments:
        return ["No user attachments were supplied."]
    lines: list[str] = []
    for attachment in attachments:
        lines.append(f"[{attachment.source_id}] {attachment.title} ({attachment.kind})")
        if attachment.caption:
            lines.append(f"Caption: {attachment.caption}")
        if attachment.extracted_text:
            lines.append(f"Extracted text: {truncate_text(attachment.extracted_text, 800)}")
        if attachment.page_refs:
            page_summaries = ", ".join(
                f"p.{max(page.page_number, 1)} {page.label or ''}".strip()
                for page in attachment.page_refs[:4]
            )
            if page_summaries:
                lines.append(f"Pages: {page_summaries}")
        lines.append("")
    return lines


def _message_input_from_text_and_attachments(
    *,
    text: str,
    attachments: list[RunAttachment],
    include_media: bool,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    if include_media:
        for attachment in attachments:
            if attachment.input_content:
                content.append(dict(attachment.input_content))
    return [{"role": "user", "content": content}]


def _should_retry_without_vision_inputs(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        pattern in message
        for pattern in (
            "input_image",
            "input_file",
            "vision",
            "image",
            "file inputs",
            "unsupported input",
        )
    )


def _attachment_evidence_items(attachments: list[RunAttachment]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for attachment in attachments:
        excerpts = [page.excerpt.strip() for page in attachment.page_refs if page.excerpt.strip()]
        evidence_excerpt = "\n\n".join(excerpts).strip() or attachment.extracted_text.strip() or attachment.caption.strip()
        modality = "pdf" if attachment.kind == "document_pdf" else "image"
        evidence_level = "attachment_excerpt" if attachment.kind == "document_pdf" else "image_caption"
        items.append(
            EvidenceItem(
                source_id=attachment.source_id,
                title=attachment.title,
                modality=modality,
                query_used="workspace_asset",
                abstract_excerpt=truncate_text(attachment.caption or attachment.description or attachment.title, 300),
                evidence_excerpt=truncate_text(evidence_excerpt or attachment.title, 1200),
                evidence_level=evidence_level,
                selection_reason="User-supplied workspace attachment used as direct evidence.",
                asset_id=attachment.asset_id,
                page_ref=", ".join(str(page.page_number) for page in attachment.page_refs[:6]),
                risk_flags=[] if (attachment.caption or attachment.extracted_text or attachment.page_refs) else ["weak_attachment_context"],
            )
        )
    return items


def _candidate_score(review: ReviewReport, *, cited_source_count: int, mode: str = "off") -> tuple[float, dict[str, Any]]:
    return score_candidate_review(
        review_status=review.status,
        unsupported_claim_count=review.unsupported_claim_count,
        missing_section_count=len(review.missing_sections),
        invalid_source_id_count=len(review.invalid_source_ids),
        finding_count=len(review.findings),
        cited_source_count=cited_source_count,
        mode=mode,
    )


def _candidate_summary_from_review(
    *,
    draft_id: str,
    variant_index: int,
    draft_markdown: str,
    cited_source_ids: list[str],
    review: ReviewReport,
    mode: str = "off",
) -> CandidateDraftSummary:
    score, metadata = _candidate_score(review, cited_source_count=len(cited_source_ids), mode=mode)
    return CandidateDraftSummary(
        draft_id=draft_id,
        variant_index=variant_index,
        status=review.status,
        score=score,
        summary=review.summary,
        cited_source_ids=cited_source_ids,
        missing_sections=review.missing_sections,
        invalid_source_ids=review.invalid_source_ids,
        unsupported_claim_count=review.unsupported_claim_count,
        finding_count=len(review.findings),
        draft_preview=truncate_text(draft_markdown, 500),
        metadata={"arbiter": metadata},
    )


def _synthetic_review_report_from_candidate(candidate: CandidateDraftSummary) -> ReviewReport:
    return ReviewReport(
        status=candidate.status,
        allow_save=candidate.status == "approved",
        summary=candidate.summary,
        findings=[
            ReviewFinding(
                severity="high" if candidate.status != "approved" else "low",
                code="candidate_selection",
                message=candidate.summary,
                source_ids=candidate.invalid_source_ids,
            )
        ]
        if candidate.summary
        else [],
        missing_sections=candidate.missing_sections,
        invalid_source_ids=candidate.invalid_source_ids,
        unsupported_claim_count=candidate.unsupported_claim_count,
        selected_draft_id=candidate.draft_id,
        candidate_drafts=[candidate],
    )


@dataclass
class AgentStepResult(Generic[T]):
    value: T
    response_id: str | None = None
    output_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WriterDraft:
    draft_markdown: str
    cited_source_ids: list[str]


@dataclass
class ResearchOrchestratorResult:
    final_text: str
    report_path: str
    bibtex_path: str
    sources_path: str
    used_source_ids: list[str]
    tool_trace: list[dict[str, Any]]
    status: str
    current_stage: str
    agent_run_id: str
    plan_json: dict[str, Any]
    evidence_json: dict[str, Any]
    review_json: dict[str, Any]
    metrics_json: dict[str, Any]
    previous_response_ids: dict[str, str]
    input_json: dict[str, Any]
    attachment_json: list[dict[str, Any]]
    candidate_drafts_json: list[dict[str, Any]]
    selected_draft_id: str | None = None
    error_message: str = ""


class DraftValidationError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        response_id: str | None = None,
        invalid_source_ids: list[str] | None = None,
        missing_sections: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.response_id = response_id
        self.invalid_source_ids = invalid_source_ids or []
        self.missing_sections = missing_sections or []

    def feedback_text(self) -> str:
        lines = [str(self)]
        if self.invalid_source_ids:
            lines.append(f"Invalid source IDs: {', '.join(self.invalid_source_ids)}")
        if self.missing_sections:
            lines.append(f"Missing sections: {', '.join(self.missing_sections)}")
        return "\n".join(lines)


class ReviewBlockedError(RuntimeError):
    def __init__(
        self,
        *,
        review_report: ReviewReport,
        last_draft: str,
        agent_run_id: str,
    ) -> None:
        super().__init__(review_report.summary or "Reviewer blocked the draft.")
        self.review_report = review_report
        self.last_draft = last_draft
        self.agent_run_id = agent_run_id


class PlannerAgentProtocol(Protocol):
    def run(
        self,
        *,
        topic: str,
        research_question: str | None,
        preferred_language: str,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment] | None = None,
        additional_instructions: str = "",
        previous_response_id: str | None = None,
    ) -> AgentStepResult[ResearchPlan]: ...


class ResearchAgentProtocol(Protocol):
    def run(
        self,
        *,
        plan: ResearchPlan,
        attachments: list[RunAttachment] | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[EvidencePack]: ...


class WriterAgentProtocol(Protocol):
    def run(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment] | None = None,
        additional_instructions: str = "",
        variant_index: int = 1,
        variant_count: int = 1,
        revision_feedback: str | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[WriterDraft]: ...


class ReviewerAgentProtocol(Protocol):
    def run(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        draft_markdown: str,
        attachments: list[RunAttachment] | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[ReviewReport]: ...


class PlannerAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        client: Any | None = None,
        instructions: str | None = None,
    ) -> None:
        if client is None:
            raise ValueError("A runtime client is required to run the planner agent.")
        self.settings = settings
        self.client = client
        self.instructions = instructions or PLANNER_INSTRUCTIONS

    def run(
        self,
        *,
        topic: str,
        research_question: str | None,
        preferred_language: str,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment] | None = None,
        additional_instructions: str = "",
        previous_response_id: str | None = None,
    ) -> AgentStepResult[ResearchPlan]:
        attachment_list = list(attachments or [])
        request: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": self.instructions,
            "input": self._build_input(
                topic=topic,
                research_question=research_question,
                preferred_language=preferred_language,
                context_pack=context_pack,
                attachments=attachment_list,
                additional_instructions=additional_instructions,
                include_media=True,
            ),
            "text_format": ResearchPlan,
            "reasoning": {"effort": self.settings.reasoning_effort},
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        used_attachment_fallback = False
        try:
            response = self.client.responses.parse(**request)
        except Exception as exc:
            if not attachment_list or not _should_retry_without_vision_inputs(exc):
                raise
            used_attachment_fallback = True
            request["input"] = self._build_input(
                topic=topic,
                research_question=research_question,
                preferred_language=preferred_language,
                context_pack=context_pack,
                attachments=attachment_list,
                additional_instructions=additional_instructions,
                include_media=False,
            )
            response = self.client.responses.parse(**request)
        raw_plan = response.output_parsed
        if raw_plan is None:
            raise RuntimeError("Planner agent returned no structured plan.")
        plan = self._normalize_plan(
            ResearchPlan.model_validate(raw_plan),
            topic=topic,
            research_question=research_question,
            preferred_language=preferred_language,
        )
        return AgentStepResult(
            value=plan,
            response_id=response.id,
            output_text=_response_output_text(response),
            metadata={
                "attachment_count": len(attachment_list),
                "used_attachment_fallback": used_attachment_fallback,
            },
        )

    def _build_input(
        self,
        *,
        topic: str,
        research_question: str | None,
        preferred_language: str,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment],
        additional_instructions: str,
        include_media: bool,
    ) -> list[dict[str, Any]]:
        lines = [
            f"Topic: {topic}",
            f"Preferred language: {preferred_language}",
            f"Research question: {research_question or 'Not specified'}",
            "Workspace context:",
            context_pack.to_prompt_block(),
            "User attachments:",
            "\n".join(_attachment_prompt_lines(attachments)),
        ]
        if additional_instructions.strip():
            lines.extend(["Additional instructions:", additional_instructions.strip()])
        return _message_input_from_text_and_attachments(
            text="\n".join(lines),
            attachments=attachments,
            include_media=include_media,
        )

    def _normalize_plan(
        self,
        plan: ResearchPlan,
        *,
        topic: str,
        research_question: str | None,
        preferred_language: str,
    ) -> ResearchPlan:
        queries = plan.queries or [
            ResearchQuery(
                query=research_question or topic,
                rationale="Primary topic search derived from the user request.",
                priority="high",
            )
        ]
        required_sections = unique_preserve_order(plan.required_sections or DEFAULT_REQUIRED_SECTIONS)
        if "References" not in required_sections:
            required_sections.append("References")
        return plan.model_copy(
            update={
                "topic": plan.topic or topic,
                "research_question": plan.research_question or research_question,
                "preferred_language": plan.preferred_language or preferred_language,
                "queries": queries,
                "required_sections": required_sections,
                "target_source_count": max(3, min(plan.target_source_count or 5, 8)),
                "must_answer_questions": plan.must_answer_questions or ([research_question] if research_question else []),
            }
        )


class ResearchAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        session: ResearchSession,
        client: Any | None = None,
        tool_event_handler: Any | None = None,
        instructions: str | None = None,
    ) -> None:
        if client is None:
            raise ValueError("A runtime client is required to run the research agent.")
        self.settings = settings
        self.session = session
        self.client = client
        self._tool_event_handler = tool_event_handler
        self.instructions = instructions or RESEARCHER_INSTRUCTIONS
        self._tool_specs = self._build_tool_specs()
        self._handlers = self._build_handlers()
        self._query_by_source_id: dict[str, str] = {}
        self._excerpt_by_source_id: dict[str, str] = {}

    def run(
        self,
        *,
        plan: ResearchPlan,
        attachments: list[RunAttachment] | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[EvidencePack]:
        attachment_list = list(attachments or [])
        request: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": self.instructions,
            "input": self._build_input(plan, attachment_list),
            "text_format": EvidencePack,
            "tools": self._tool_specs,
            "reasoning": {"effort": self.settings.reasoning_effort},
            "max_tool_calls": self.settings.max_tool_calls,
            "parallel_tool_calls": False,
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        response = self.client.responses.parse(**request)
        loop_guard = 0
        while True:
            loop_guard += 1
            if loop_guard > self.settings.max_tool_calls + 3:
                raise RuntimeError("Research agent exceeded the safe tool-call loop limit.")
            tool_outputs = self._execute_function_calls(response)
            if not tool_outputs:
                break
            response = self.client.responses.parse(
                model=self.settings.model,
                instructions=self.instructions,
                previous_response_id=response.id,
                input=tool_outputs,
                text_format=EvidencePack,
                tools=self._tool_specs,
                reasoning={"effort": self.settings.reasoning_effort},
                max_tool_calls=self.settings.max_tool_calls,
                parallel_tool_calls=False,
            )

        raw_pack = response.output_parsed
        if raw_pack is None:
            raise RuntimeError("Research agent returned no structured evidence pack.")
        pack = self._normalize_pack(EvidencePack.model_validate(raw_pack), plan=plan, attachments=attachment_list)
        return AgentStepResult(value=pack, response_id=response.id, output_text=_response_output_text(response))

    def _build_input(self, plan: ResearchPlan, attachments: list[RunAttachment]) -> str:
        query_lines = "\n".join(
            f"- {query.query} ({query.priority}): {query.rationale or 'No rationale provided.'}"
            for query in plan.queries
        )
        screening_lines = "\n".join(f"- {item}" for item in plan.screening_criteria) or "- Prefer relevant, citable work."
        question_lines = "\n".join(f"- {item}" for item in plan.must_answer_questions) or "- Cover the main topic."
        return "\n".join(
            [
                f"Topic: {plan.topic}",
                f"Research question: {plan.research_question or 'Not specified'}",
                f"Preferred language: {plan.preferred_language}",
                f"Target source count: {plan.target_source_count}",
                f"Open access only: {plan.open_access_only}",
                f"Require PDF for methods: {plan.require_pdf_for_methods}",
                "Queries:",
                query_lines,
                "Must answer:",
                question_lines,
                "Screening criteria:",
                screening_lines,
                "User attachments:",
                "\n".join(_attachment_prompt_lines(attachments)),
            ]
        )

    def _build_handlers(self) -> dict[str, Any]:
        return {
            "search_openalex": self.session.search_openalex,
            "get_source_details": self.session.get_source_details,
            "fetch_pdf_excerpt": self.session.fetch_pdf_excerpt,
        }

    def _build_tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_openalex",
                "description": "Search scholarly literature in OpenAlex and return candidate papers with source IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 15},
                        "from_year": {"type": "integer"},
                        "to_year": {"type": "integer"},
                        "open_access_only": {"type": "boolean"},
                        "require_pdf": {"type": "boolean"},
                        "sort_by": {"type": "string", "enum": ["relevance", "most_cited"]},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_source_details",
                "description": "Inspect a previously discovered paper in more detail using its source ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"source_id": {"type": "string"}},
                    "required": ["source_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "fetch_pdf_excerpt",
                "description": "Download an open-access PDF for a source and extract text from the first pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "max_pages": {"type": "integer", "minimum": 1, "maximum": 12},
                        "max_characters": {"type": "integer", "minimum": 1000, "maximum": 30000},
                    },
                    "required": ["source_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def _execute_function_calls(self, response: Any) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            arguments = json.loads(getattr(item, "arguments", "") or "{}")
            self._record_tool_event(
                {
                    "stage": "researching",
                    "event": "tool_requested",
                    "tool": getattr(item, "name", ""),
                    "arguments": arguments,
                }
            )
            result = self._invoke_tool(getattr(item, "name", ""), arguments)
            self._record_tool_event(
                {
                    "stage": "researching",
                    "event": "tool_completed",
                    "tool": getattr(item, "name", ""),
                    "arguments": arguments,
                    "result_preview": self._preview_tool_result(result),
                }
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": getattr(item, "call_id", ""),
                    "output": tool_result_json(result),
                }
            )
        return outputs

    def _invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers[tool_name]
        try:
            result = handler(**arguments)
        except Exception as exc:
            return {
                "status": "error",
                "tool": tool_name,
                "message": str(exc),
            }
        if tool_name == "search_openalex":
            query = str(arguments.get("query") or "").strip()
            for source_id in result.get("source_ids", []):
                self._query_by_source_id[source_id] = query
        elif tool_name == "fetch_pdf_excerpt" and result.get("status") == "ok":
            source_id = str(result.get("source_id") or "")
            excerpt = str(result.get("text_excerpt") or "")
            if source_id and excerpt:
                self._excerpt_by_source_id[source_id] = excerpt
        return result

    def _record_tool_event(self, payload: dict[str, Any]) -> None:
        if callable(self._tool_event_handler):
            self._tool_event_handler(payload)

    def _preview_tool_result(self, result: dict[str, Any]) -> dict[str, Any]:
        preview = dict(result)
        if "text_excerpt" in preview:
            preview["text_excerpt"] = truncate_text(str(preview["text_excerpt"]), 500)
        if "results" in preview and isinstance(preview["results"], list):
            preview["results"] = preview["results"][:3]
        return preview

    def _normalize_pack(self, pack: EvidencePack, *, plan: ResearchPlan, attachments: list[RunAttachment]) -> EvidencePack:
        normalized_items: list[EvidenceItem] = []
        seen: set[str] = set()
        for raw_item in pack.items:
            item = EvidenceItem.model_validate(raw_item)
            if item.source_id not in self.session.sources or item.source_id in seen:
                continue
            seen.add(item.source_id)
            record = self.session.sources[item.source_id]
            normalized_items.append(self._merge_item_with_record(item=item, record=record))

        if not normalized_items:
            fallback_ids = self.session.consulted_source_ids[: max(1, plan.target_source_count)]
            for source_id in fallback_ids:
                record = self.session.sources.get(source_id)
                if record is None:
                    continue
                normalized_items.append(self._evidence_item_from_record(record))

        attachment_items = _attachment_evidence_items(attachments)
        normalized_items = attachment_items + normalized_items[: max(1, plan.target_source_count)]
        included_source_ids = unique_preserve_order([item.source_id for item in normalized_items])
        return pack.model_copy(
            update={
                "topic": pack.topic or plan.topic,
                "research_question": pack.research_question or plan.research_question,
                "items": normalized_items,
                "included_source_ids": included_source_ids,
                "queries_used": unique_preserve_order(
                    [item.query_used for item in normalized_items if item.query_used] + pack.queries_used
                ),
                "research_summary": pack.research_summary.strip()
                or f"Collected {len(normalized_items)} evidence items for {plan.topic}.",
            }
        )

    def _merge_item_with_record(self, *, item: EvidenceItem, record: WorkRecord) -> EvidenceItem:
        abstract_excerpt = item.abstract_excerpt or truncate_text(record.abstract or "", 400)
        evidence_excerpt = item.evidence_excerpt or self._excerpt_by_source_id.get(item.source_id) or abstract_excerpt
        evidence_level = "pdf_excerpt" if item.source_id in self._excerpt_by_source_id else item.evidence_level
        return item.model_copy(
            update={
                "title": item.title or record.title,
                "query_used": item.query_used or self._query_by_source_id.get(item.source_id, ""),
                "publication_year": item.publication_year or record.publication_year,
                "cited_by_count": item.cited_by_count or record.cited_by_count,
                "venue": item.venue or record.venue or "",
                "abstract_excerpt": abstract_excerpt,
                "evidence_excerpt": evidence_excerpt,
                "evidence_level": evidence_level,
                "selection_reason": item.selection_reason or "Selected for relevance to the research plan.",
            }
        )

    def _evidence_item_from_record(self, record: WorkRecord) -> EvidenceItem:
        excerpt = self._excerpt_by_source_id.get(record.source_id) or truncate_text(record.abstract or "", 400)
        return EvidenceItem(
            source_id=record.source_id,
            title=record.title,
            query_used=self._query_by_source_id.get(record.source_id, ""),
            publication_year=record.publication_year,
            cited_by_count=record.cited_by_count,
            venue=record.venue or "",
            abstract_excerpt=truncate_text(record.abstract or "", 400),
            evidence_excerpt=excerpt,
            evidence_level="pdf_excerpt" if record.source_id in self._excerpt_by_source_id else "abstract",
            selection_reason="Selected from the search results as fallback evidence.",
        )


class WriterAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        client: Any | None = None,
        instructions: str | None = None,
    ) -> None:
        if client is None:
            raise ValueError("A runtime client is required to run the writer agent.")
        self.settings = settings
        self.client = client
        self.instructions = instructions or WRITER_INSTRUCTIONS

    def run(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment] | None = None,
        additional_instructions: str = "",
        variant_index: int = 1,
        variant_count: int = 1,
        revision_feedback: str | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[WriterDraft]:
        attachment_list = list(attachments or [])
        request: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": self.instructions,
            "input": self._build_input(
                plan=plan,
                evidence_pack=evidence_pack,
                context_pack=context_pack,
                attachments=attachment_list,
                additional_instructions=additional_instructions,
                variant_index=variant_index,
                variant_count=variant_count,
                revision_feedback=revision_feedback,
                include_media=True,
            ),
            "reasoning": {"effort": self.settings.reasoning_effort},
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        used_attachment_fallback = False
        try:
            response = self.client.responses.create(**request)
        except Exception as exc:
            if not attachment_list or not _should_retry_without_vision_inputs(exc):
                raise
            used_attachment_fallback = True
            request["input"] = self._build_input(
                plan=plan,
                evidence_pack=evidence_pack,
                context_pack=context_pack,
                attachments=attachment_list,
                additional_instructions=additional_instructions,
                variant_index=variant_index,
                variant_count=variant_count,
                revision_feedback=revision_feedback,
                include_media=False,
            )
            response = self.client.responses.create(**request)
        draft_markdown = _response_output_text(response).strip()
        cited_source_ids = extract_source_ids(draft_markdown)
        invalid_source_ids = [
            source_id for source_id in cited_source_ids if source_id not in set(evidence_pack.included_source_ids)
        ]
        missing_sections = _missing_sections(draft_markdown, plan.required_sections)
        if invalid_source_ids or missing_sections:
            message = "Writer draft failed output guardrails."
            if invalid_source_ids:
                message = f"{message} Invalid source IDs: {', '.join(invalid_source_ids)}."
            if missing_sections:
                message = f"{message} Missing sections: {', '.join(missing_sections)}."
            raise DraftValidationError(
                message=message,
                response_id=response.id,
                invalid_source_ids=invalid_source_ids,
                missing_sections=missing_sections,
            )

        return AgentStepResult(
            value=WriterDraft(
                draft_markdown=draft_markdown,
                cited_source_ids=unique_preserve_order(cited_source_ids),
            ),
            response_id=response.id,
            output_text=draft_markdown,
            metadata={"used_attachment_fallback": used_attachment_fallback, "variant_index": variant_index},
        )

    def _build_input(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        context_pack: WorkspaceContextPack,
        attachments: list[RunAttachment],
        additional_instructions: str,
        variant_index: int,
        variant_count: int,
        revision_feedback: str | None,
        include_media: bool,
    ) -> list[dict[str, Any]]:
        source_lines = []
        for item in evidence_pack.items:
            source_lines.extend(
                [
                    f"[{item.source_id}] {item.title}",
                    f"Year: {item.publication_year or 'Unknown'}; Venue: {item.venue or 'Unknown'}; Citations: {item.cited_by_count}",
                    f"Selection reason: {item.selection_reason or 'Not specified.'}",
                    f"Abstract excerpt: {item.abstract_excerpt or 'None.'}",
                    f"Evidence excerpt: {item.evidence_excerpt or 'None.'}",
                    "",
                ]
            )

        revision_block = revision_feedback.strip() if revision_feedback else "No prior reviewer feedback."
        section_lines = "\n".join(f"- {section}" for section in plan.required_sections)
        lines = [
            f"Topic: {plan.topic}",
            f"Research question: {plan.research_question or 'Not specified'}",
            f"Preferred language: {plan.preferred_language}",
            (
                f"Draft variant {variant_index} of {variant_count}. Produce a distinct but citation-safe alternative."
                if variant_count > 1
                else "Produce one citation-safe draft."
            ),
            "Use these exact markdown section headings:",
            section_lines,
            "Relevant workspace context:",
            context_pack.to_prompt_block(),
            "Evidence pack:",
            "\n".join(source_lines).strip(),
            "Attachment evidence:",
            "\n".join(_attachment_prompt_lines(attachments)),
            "Revision feedback:",
            revision_block,
        ]
        if additional_instructions.strip():
            lines.extend(["Additional instructions:", additional_instructions.strip()])
        return _message_input_from_text_and_attachments(
            text="\n".join(lines),
            attachments=attachments,
            include_media=include_media,
        )


class ReviewerAgent:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: Any | None = None,
        use_model_feedback: bool = True,
        instructions: str | None = None,
        thresholds: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.use_model_feedback = bool(self.client is not None and use_model_feedback and settings is not None)
        self.instructions = instructions or REVIEWER_INSTRUCTIONS
        self.thresholds = dict(thresholds or {})

    def run(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        draft_markdown: str,
        attachments: list[RunAttachment] | None = None,
        previous_response_id: str | None = None,
    ) -> AgentStepResult[ReviewReport]:
        attachment_list = list(attachments or [])
        allowed_source_ids = set(evidence_pack.included_source_ids)
        invalid_source_ids = [
            source_id for source_id in extract_source_ids(draft_markdown) if source_id not in allowed_source_ids
        ]
        missing_sections = _missing_sections(draft_markdown, plan.required_sections)
        unsupported_claim_count = _unsupported_claim_count(draft_markdown)
        max_unsupported_claim_count = int(self.thresholds.get("max_unsupported_claim_count", 0) or 0)
        max_missing_sections = int(self.thresholds.get("max_missing_sections", 0) or 0)
        require_valid_source_ids = bool(self.thresholds.get("require_valid_source_ids", True))

        findings: list[ReviewFinding] = []
        if invalid_source_ids and require_valid_source_ids:
            findings.append(
                ReviewFinding(
                    severity="high",
                    code="invalid_source_id",
                    message=f"Draft cites source IDs outside the evidence pack: {', '.join(invalid_source_ids)}.",
                    source_ids=invalid_source_ids,
                )
            )
        if len(missing_sections) > max_missing_sections:
            findings.append(
                ReviewFinding(
                    severity="high",
                    code="missing_sections",
                    message=f"Draft is missing required sections: {', '.join(missing_sections)}.",
                )
            )
        if unsupported_claim_count > max_unsupported_claim_count:
            findings.append(
                ReviewFinding(
                    severity="high" if unsupported_claim_count >= 2 else "medium",
                    code="unsupported_claims",
                    message=f"Draft contains {unsupported_claim_count} substantive paragraph(s) without citations.",
                )
            )

        model_feedback = ReviewModelFeedback(summary="", approve=True, findings=[])
        response_id: str | None = None
        used_attachment_fallback = False
        if self.use_model_feedback and self.client is not None and self.settings is not None:
            request: dict[str, Any] = {
                "model": self.settings.model,
                "instructions": self.instructions,
                "input": self._build_input(
                    plan=plan,
                    evidence_pack=evidence_pack,
                    draft_markdown=draft_markdown,
                    attachments=attachment_list,
                    include_media=True,
                ),
                "text_format": ReviewModelFeedback,
                "reasoning": {"effort": self.settings.reasoning_effort},
            }
            if previous_response_id:
                request["previous_response_id"] = previous_response_id
            try:
                response = self.client.responses.parse(**request)
            except Exception as exc:
                if not attachment_list or not _should_retry_without_vision_inputs(exc):
                    raise
                used_attachment_fallback = True
                request["input"] = self._build_input(
                    plan=plan,
                    evidence_pack=evidence_pack,
                    draft_markdown=draft_markdown,
                    attachments=attachment_list,
                    include_media=False,
                )
                response = self.client.responses.parse(**request)
            response_id = response.id
            raw_feedback = response.output_parsed
            if raw_feedback is not None:
                model_feedback = ReviewModelFeedback.model_validate(raw_feedback)
                findings.extend(model_feedback.findings)

        findings = _dedupe_findings(findings)
        blocked = bool(
            (invalid_source_ids and require_valid_source_ids)
            or len(missing_sections) > max_missing_sections
            or unsupported_claim_count > max_unsupported_claim_count
            or not model_feedback.approve
            or any(finding.severity == "high" for finding in findings)
        )
        summary = model_feedback.summary.strip()
        if not summary:
            summary = (
                "Draft approved by reviewer."
                if not blocked
                else "Reviewer blocked the draft because it failed evidence or structure checks."
            )
        report = ReviewReport(
            status="blocked" if blocked else "approved",
            allow_save=not blocked,
            summary=summary,
            findings=findings,
            missing_sections=missing_sections,
            invalid_source_ids=invalid_source_ids,
            unsupported_claim_count=unsupported_claim_count,
        )
        return AgentStepResult(
            value=report,
            response_id=response_id,
            output_text=summary,
            metadata={"used_attachment_fallback": used_attachment_fallback},
        )

    def _build_input(
        self,
        *,
        plan: ResearchPlan,
        evidence_pack: EvidencePack,
        draft_markdown: str,
        attachments: list[RunAttachment],
        include_media: bool,
    ) -> list[dict[str, Any]]:
        source_lines = []
        for item in evidence_pack.items:
            source_lines.append(
                f"[{item.source_id}] {item.title} | {item.publication_year or 'Unknown'} | {item.selection_reason or 'No reason provided.'}"
            )
        return _message_input_from_text_and_attachments(
            text="\n".join(
                [
                    f"Topic: {plan.topic}",
                    f"Research question: {plan.research_question or 'Not specified'}",
                    f"Required sections: {', '.join(plan.required_sections)}",
                    f"Allowed source IDs: {', '.join(evidence_pack.included_source_ids)}",
                    "Evidence summary:",
                    "\n".join(source_lines) or "No evidence items.",
                    "Attachment evidence:",
                    "\n".join(_attachment_prompt_lines(attachments)),
                    "Draft to review:",
                    draft_markdown,
                ]
            ),
            attachments=attachments,
            include_media=include_media,
        )


class ResearchOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        session: ResearchSession,
        db: Session | None = None,
        user: User | None = None,
        workspace: Workspace | None = None,
        planner: PlannerAgentProtocol | None = None,
        researcher: ResearchAgentProtocol | None = None,
        writer: WriterAgentProtocol | None = None,
        reviewer: ReviewerAgentProtocol | None = None,
        stage_clients: dict[str, Any] | None = None,
        instruction_overrides: dict[str, str] | None = None,
        review_thresholds: dict[str, Any] | None = None,
        runtime_bundle: dict[str, Any] | None = None,
        max_draft_attempts: int = 3,
    ) -> None:
        self.settings = settings
        self.math_mode = settings_math_mode(settings)
        self.session = session
        self.db = db
        self.user = user
        self.workspace = workspace
        self.trace_events: list[AgentRunTraceEvent] = []
        self.previous_response_ids: dict[str, str] = {}
        self.max_draft_attempts = max(1, max_draft_attempts)
        self.runtime_bundle = dict(runtime_bundle or {})
        resolved_stage_clients = dict(stage_clients or {})
        overrides = dict(instruction_overrides or {})
        self.planner = planner or PlannerAgent(
            settings=settings,
            client=resolved_stage_clients.get("planner"),
            instructions=overrides.get("planner"),
        )
        self.researcher = researcher or ResearchAgent(
            settings=settings,
            session=session,
            client=resolved_stage_clients.get("researcher"),
            tool_event_handler=self._record_external_event,
            instructions=overrides.get("researcher"),
        )
        self.writer = writer or WriterAgent(
            settings=settings,
            client=resolved_stage_clients.get("writer"),
            instructions=overrides.get("writer"),
        )
        self.reviewer = reviewer or ReviewerAgent(
            settings=settings,
            client=resolved_stage_clients.get("reviewer"),
            instructions=overrides.get("reviewer"),
            thresholds=review_thresholds,
        )

    def run(
        self,
        *,
        topic: str,
        research_question: str | None = None,
        preferred_language: str = "Chinese",
        attachments: list[RunAttachment] | None = None,
        draft_variants: int = 1,
        mode: str = "standard",
        additional_instructions: str = "",
        input_payload: dict[str, Any] | None = None,
        existing_run: AgentRun | None = None,
        plan_override: ResearchPlan | None = None,
        evidence_override: EvidencePack | None = None,
        context_pack_override: WorkspaceContextPack | None = None,
        previous_response_ids: dict[str, str] | None = None,
    ) -> ResearchOrchestratorResult:
        attachment_list = list(attachments or [])
        attachment_payload = _safe_attachment_payload(attachment_list)
        normalized_input = dict(input_payload or {})
        normalized_input.setdefault("topic", topic)
        normalized_input.setdefault("question", research_question)
        normalized_input.setdefault("mode", mode)
        normalized_input.setdefault("instructions", additional_instructions)
        normalized_input.setdefault("draft_variants", draft_variants)
        normalized_input.setdefault("asset_ids", [attachment.asset_id for attachment in attachment_list])
        self.trace_events = [
            AgentRunTraceEvent.model_validate(item)
            for item in ((existing_run.trace_json or []) if existing_run is not None else [])
            if isinstance(item, dict)
        ]
        existing_previous_ids = {}
        if existing_run is not None and isinstance(existing_run.metrics_json, dict):
            existing_previous_ids = dict(existing_run.metrics_json.get("previous_response_ids") or {})
        self.previous_response_ids = dict(previous_response_ids or existing_previous_ids)
        context_pack = context_pack_override or self._build_context_pack(topic=topic, research_question=research_question)
        store = AgentRunStore(
            db=self.db,
            context=AgentRunContext(
                session_id=self.session.session_dir.name,
                topic=topic,
                question=research_question,
                language=preferred_language,
                session_dir=self.session.session_dir,
                workspace=self.workspace,
                user=self.user,
            ),
            existing_record=existing_run,
        )
        starting_stage = "drafting" if plan_override is not None and evidence_override is not None else "planned"
        store.start(
            status="running",
            current_stage=starting_stage,
            context_json=context_pack.model_dump(mode="json"),
            input_json=normalized_input,
            attachment_json=attachment_payload,
        )
        self._trace(
            starting_stage,
            "retry_requested" if existing_run is not None else "stage_started",
            topic=topic,
            attachment_count=len(attachment_list),
            draft_variants=max(1, draft_variants),
            mode=mode,
        )

        scope_issue = _research_scope_issue(topic, research_question)
        if scope_issue:
            review = ReviewReport(
                status="blocked",
                allow_save=False,
                summary=scope_issue,
                findings=[
                    ReviewFinding(
                        severity="high",
                        code="scope_guard",
                        message=scope_issue,
                    )
                ],
            )
            self._trace("blocked", "scope_blocked", reason=scope_issue)
            metrics = self._build_metrics(
                None,
                None,
                review,
                draft_markdown=None,
                draft_attempts=0,
                candidate_drafts=[],
                attachment_count=len(attachment_list),
            )
            store.update(
                status="blocked",
                current_stage="blocked",
                input_json=normalized_input,
                attachment_json=attachment_payload,
                review_json=review.model_dump(mode="json"),
                trace_json=self._trace_payload(),
                metrics_json=metrics,
                finished=True,
            )
            store.complete(
                status="blocked",
                current_stage="blocked",
                summary=scope_issue,
                metadata={"previous_response_ids": self.previous_response_ids},
            )
            return ResearchOrchestratorResult(
                final_text="",
                report_path="",
                bibtex_path="",
                sources_path="",
                used_source_ids=[],
                tool_trace=self._trace_payload(),
                status="blocked",
                current_stage="blocked",
                agent_run_id=store.run_id,
                plan_json={},
                evidence_json={},
                review_json=review.model_dump(mode="json"),
                metrics_json=metrics,
                previous_response_ids=dict(self.previous_response_ids),
                input_json=normalized_input,
                attachment_json=attachment_payload,
                candidate_drafts_json=[],
                selected_draft_id=None,
                error_message=scope_issue,
            )

        plan: ResearchPlan | None = plan_override
        evidence_pack: EvidencePack | None = evidence_override
        review_report: ReviewReport | None = None
        last_draft = ""
        draft_attempts = 0
        selected_draft_id: str | None = None
        candidate_drafts_json: list[dict[str, Any]] = []
        try:
            if plan is None or evidence_pack is None:
                plan_result = self.planner.run(
                    topic=topic,
                    research_question=research_question,
                    preferred_language=preferred_language,
                    context_pack=context_pack,
                    attachments=attachment_list,
                    additional_instructions=additional_instructions,
                    previous_response_id=self.previous_response_ids.get("planner"),
                )
                self._save_previous_response_id("planner", plan_result.response_id)
                plan = plan_result.value
                self._trace("planned", "stage_completed", query_count=len(plan.queries))
                store.update(
                    status="running",
                    current_stage="planned",
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    plan_json=plan.model_dump(mode="json"),
                    trace_json=self._trace_payload(),
                    metrics_json={"previous_response_ids": dict(self.previous_response_ids)},
                )

                self._trace("researching", "stage_started", target_source_count=plan.target_source_count)
                research_result = self.researcher.run(
                    plan=plan,
                    attachments=attachment_list,
                    previous_response_id=self.previous_response_ids.get("researcher"),
                )
                self._save_previous_response_id("researcher", research_result.response_id)
                evidence_pack = research_result.value
                self._trace(
                    "researching",
                    "evidence_snapshot_saved",
                    included_source_ids=evidence_pack.included_source_ids,
                    rejected_source_ids=[
                        source_id
                        for source_id in self.session.consulted_source_ids
                        if source_id not in set(evidence_pack.included_source_ids)
                    ],
                )
                self._trace("researching", "stage_completed", source_count=len(evidence_pack.items))
                store.update(
                    status="running",
                    current_stage="researching",
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    plan_json=plan.model_dump(mode="json"),
                    evidence_json=evidence_pack.model_dump(mode="json"),
                    trace_json=self._trace_payload(),
                    metrics_json={"previous_response_ids": dict(self.previous_response_ids)},
                )
            else:
                self._trace("drafting", "resume_loaded", source_count=len(evidence_pack.items))
                store.update(
                    status="running",
                    current_stage="drafting",
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    plan_json=plan.model_dump(mode="json"),
                    evidence_json=evidence_pack.model_dump(mode="json"),
                    trace_json=self._trace_payload(),
                    metrics_json={"previous_response_ids": dict(self.previous_response_ids)},
                )

            revision_feedback: str | None = additional_instructions.strip() or None
            candidate_variant_count = max(1, draft_variants)
            for attempt in range(1, self.max_draft_attempts + 1):
                draft_attempts = attempt
                current_candidate_summaries: list[CandidateDraftSummary] = []
                candidate_reviews: dict[str, ReviewReport] = {}
                candidate_texts: dict[str, str] = {}
                self._trace("drafting", "stage_started", attempt=attempt, variant_count=candidate_variant_count)
                for variant_index in range(1, candidate_variant_count + 1):
                    candidate_id = f"D{attempt}-{variant_index}"
                    try:
                        writer_result = self.writer.run(
                            plan=plan,
                            evidence_pack=evidence_pack,
                            context_pack=context_pack,
                            attachments=attachment_list,
                            additional_instructions=additional_instructions,
                            variant_index=variant_index,
                            variant_count=candidate_variant_count,
                            revision_feedback=revision_feedback,
                            previous_response_id=self.previous_response_ids.get("writer") if variant_index == 1 else None,
                        )
                    except DraftValidationError as exc:
                        self._save_previous_response_id("writer", exc.response_id)
                        summary = CandidateDraftSummary(
                            draft_id=candidate_id,
                            variant_index=variant_index,
                            status="blocked",
                            score=0.0,
                            summary=exc.feedback_text(),
                            cited_source_ids=[],
                            missing_sections=exc.missing_sections,
                            invalid_source_ids=exc.invalid_source_ids,
                            unsupported_claim_count=0,
                            finding_count=1,
                            draft_preview="",
                        )
                        current_candidate_summaries.append(summary)
                        candidate_reviews[candidate_id] = _synthetic_review_report_from_candidate(summary)
                        self._trace(
                            "drafting",
                            "candidate_blocked",
                            attempt=attempt,
                            variant_index=variant_index,
                            invalid_source_ids=exc.invalid_source_ids,
                            missing_sections=exc.missing_sections,
                        )
                        continue

                    self._save_previous_response_id("writer", writer_result.response_id)
                    candidate_texts[candidate_id] = writer_result.value.draft_markdown
                    self._trace(
                        "drafting",
                        "candidate_completed",
                        attempt=attempt,
                        variant_index=variant_index,
                        cited_source_count=len(writer_result.value.cited_source_ids),
                    )
                    reviewer_result = self.reviewer.run(
                        plan=plan,
                        evidence_pack=evidence_pack,
                        draft_markdown=writer_result.value.draft_markdown,
                        attachments=attachment_list,
                        previous_response_id=self.previous_response_ids.get("reviewer") if variant_index == 1 else None,
                    )
                    self._save_previous_response_id("reviewer", reviewer_result.response_id)
                    candidate_review = reviewer_result.value
                    candidate_reviews[candidate_id] = candidate_review
                    current_candidate_summaries.append(
                        _candidate_summary_from_review(
                            draft_id=candidate_id,
                            variant_index=variant_index,
                            draft_markdown=writer_result.value.draft_markdown,
                            cited_source_ids=writer_result.value.cited_source_ids,
                            review=candidate_review,
                            mode=self.math_mode,
                        )
                    )
                    self._trace(
                        "reviewing",
                        "candidate_reviewed",
                        attempt=attempt,
                        variant_index=variant_index,
                        status=candidate_review.status,
                        unsupported_claim_count=candidate_review.unsupported_claim_count,
                    )

                if not current_candidate_summaries:
                    synthetic_candidate = CandidateDraftSummary(
                        draft_id=f"D{attempt}-1",
                        variant_index=1,
                        status="blocked",
                        score=0.0,
                        summary="No candidate draft was generated.",
                        finding_count=1,
                    )
                    current_candidate_summaries = [synthetic_candidate]
                    candidate_reviews[synthetic_candidate.draft_id] = _synthetic_review_report_from_candidate(synthetic_candidate)

                selected_candidate = max(
                    current_candidate_summaries,
                    key=lambda item: (item.status == "approved", item.score, -item.variant_index),
                )
                selected_draft_id = selected_candidate.draft_id
                last_draft = candidate_texts.get(selected_draft_id, last_draft)
                selected_review = candidate_reviews.get(selected_draft_id) or _synthetic_review_report_from_candidate(selected_candidate)
                review_report = selected_review.model_copy(
                    update={
                        "selected_draft_id": selected_draft_id,
                        "candidate_drafts": current_candidate_summaries,
                    }
                )
                candidate_drafts_json = [item.model_dump(mode="json") for item in current_candidate_summaries]
                self._trace(
                    "reviewing",
                    "candidate_selected",
                    attempt=attempt,
                    selected_draft_id=selected_draft_id,
                    status=review_report.status,
                    score=selected_candidate.score,
                    math_mode=self.math_mode,
                    arbiter=(selected_candidate.metadata or {}).get("arbiter", {}),
                )
                store.update(
                    status="running" if review_report.status == "approved" else "blocked",
                    current_stage="approved" if review_report.status == "approved" else "reviewing",
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    plan_json=plan.model_dump(mode="json"),
                    evidence_json=evidence_pack.model_dump(mode="json"),
                    review_json=review_report.model_dump(mode="json"),
                    candidate_drafts_json=candidate_drafts_json,
                    selected_draft_id=selected_draft_id,
                    trace_json=self._trace_payload(),
                    metrics_json=self._build_metrics(
                        plan,
                        evidence_pack,
                        review_report,
                        draft_markdown=last_draft,
                        draft_attempts=draft_attempts,
                        candidate_drafts=current_candidate_summaries,
                        attachment_count=len(attachment_list),
                    ),
                    final_text=last_draft,
                )
                if review_report.status == "approved":
                    break
                revision_feedback = _format_review_feedback(review_report)

            if review_report is None or review_report.status != "approved":
                final_review = review_report or ReviewReport(
                    status="blocked",
                    allow_save=False,
                    summary="Reviewer blocked the draft.",
                    candidate_drafts=[CandidateDraftSummary(draft_id="D-final", summary="No approved draft.", status="blocked")],
                )
                metrics = self._build_metrics(
                    plan,
                    evidence_pack,
                    final_review,
                    draft_markdown=last_draft,
                    draft_attempts=draft_attempts,
                    candidate_drafts=[CandidateDraftSummary.model_validate(item) for item in candidate_drafts_json],
                    attachment_count=len(attachment_list),
                )
                self._trace("blocked", "stage_completed", summary=final_review.summary)
                store.update(
                    status="blocked",
                    current_stage="blocked",
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    plan_json=plan.model_dump(mode="json"),
                    evidence_json=evidence_pack.model_dump(mode="json"),
                    review_json=final_review.model_dump(mode="json"),
                    candidate_drafts_json=candidate_drafts_json,
                    selected_draft_id=selected_draft_id,
                    trace_json=self._trace_payload(),
                    metrics_json=metrics,
                    final_text=last_draft,
                    finished=True,
                )
                store.complete(
                    status="blocked",
                    current_stage="blocked",
                    summary=final_review.summary,
                    metadata={"previous_response_ids": dict(self.previous_response_ids)},
                )
                return ResearchOrchestratorResult(
                    final_text=last_draft,
                    report_path="",
                    bibtex_path="",
                    sources_path="",
                    used_source_ids=[],
                    tool_trace=self._trace_payload(),
                    status="blocked",
                    current_stage="blocked",
                    agent_run_id=store.run_id,
                    plan_json=plan.model_dump(mode="json"),
                    evidence_json=evidence_pack.model_dump(mode="json"),
                    review_json=final_review.model_dump(mode="json"),
                    metrics_json=metrics,
                    previous_response_ids=dict(self.previous_response_ids),
                    input_json=normalized_input,
                    attachment_json=attachment_payload,
                    candidate_drafts_json=candidate_drafts_json,
                    selected_draft_id=selected_draft_id,
                    error_message=final_review.summary,
                )

            used_source_ids = unique_preserve_order(
                [
                    source_id
                    for source_id in extract_source_ids(last_draft)
                    if source_id in set(evidence_pack.included_source_ids)
                ]
                or evidence_pack.included_source_ids
            )
            attachment_source_entries = [
                {
                    "source_id": attachment.source_id,
                    "asset_id": attachment.asset_id,
                    "title": attachment.title,
                    "kind": attachment.kind,
                    "caption": attachment.caption,
                    "page_refs": [page.model_dump(mode="json") for page in attachment.page_refs],
                }
                for attachment in attachment_list
            ]
            artifact = self.session.persist_outputs(
                topic=topic,
                report_markdown=last_draft,
                source_ids=used_source_ids,
                extra_sources=attachment_source_entries,
            )
            self._trace("saved", "stage_completed", source_count=len(used_source_ids))
            metrics = self._build_metrics(
                plan,
                evidence_pack,
                review_report,
                draft_markdown=last_draft,
                draft_attempts=draft_attempts,
                candidate_drafts=[CandidateDraftSummary.model_validate(item) for item in candidate_drafts_json],
                attachment_count=len(attachment_list),
            )
            store.update(
                status="saved",
                current_stage="saved",
                input_json=normalized_input,
                attachment_json=attachment_payload,
                plan_json=plan.model_dump(mode="json"),
                evidence_json=evidence_pack.model_dump(mode="json"),
                review_json=review_report.model_dump(mode="json"),
                candidate_drafts_json=candidate_drafts_json,
                selected_draft_id=selected_draft_id,
                trace_json=self._trace_payload(),
                metrics_json=metrics,
                report_path=str(artifact.report_path),
                bibtex_path=str(artifact.bibtex_path),
                sources_path=str(artifact.sources_path),
                final_text=last_draft,
                finished=True,
            )
            store.complete(
                status="saved",
                current_stage="saved",
                summary=f"Saved research report for {topic}",
                metadata={
                    "draft_attempts": draft_attempts,
                    "source_count": len(used_source_ids),
                    "previous_response_ids": dict(self.previous_response_ids),
                },
            )
            return ResearchOrchestratorResult(
                final_text=last_draft,
                report_path=str(artifact.report_path),
                bibtex_path=str(artifact.bibtex_path),
                sources_path=str(artifact.sources_path),
                used_source_ids=used_source_ids,
                tool_trace=self._trace_payload(),
                status="saved",
                current_stage="saved",
                agent_run_id=store.run_id,
                plan_json=plan.model_dump(mode="json"),
                evidence_json=evidence_pack.model_dump(mode="json"),
                review_json=review_report.model_dump(mode="json"),
                metrics_json=metrics,
                previous_response_ids=dict(self.previous_response_ids),
                input_json=normalized_input,
                attachment_json=attachment_payload,
                candidate_drafts_json=candidate_drafts_json,
                selected_draft_id=selected_draft_id,
            )
        except Exception as exc:
            self._trace("failed", "stage_completed", error=str(exc))
            metrics = self._build_metrics(
                plan,
                evidence_pack,
                review_report,
                draft_markdown=last_draft,
                draft_attempts=draft_attempts,
                candidate_drafts=[CandidateDraftSummary.model_validate(item) for item in candidate_drafts_json],
                attachment_count=len(attachment_list),
            )
            store.update(
                status="failed",
                current_stage="failed",
                input_json=normalized_input,
                attachment_json=attachment_payload,
                plan_json=plan.model_dump(mode="json") if plan is not None else {},
                evidence_json=evidence_pack.model_dump(mode="json") if evidence_pack is not None else {},
                review_json=review_report.model_dump(mode="json") if review_report is not None else {},
                candidate_drafts_json=candidate_drafts_json,
                selected_draft_id=selected_draft_id,
                trace_json=self._trace_payload(),
                metrics_json=metrics,
                final_text=last_draft,
                finished=True,
            )
            store.complete(
                status="failed",
                current_stage="failed",
                summary=str(exc),
                metadata={"previous_response_ids": dict(self.previous_response_ids)},
            )
            return ResearchOrchestratorResult(
                final_text=last_draft,
                report_path="",
                bibtex_path="",
                sources_path="",
                used_source_ids=[],
                tool_trace=self._trace_payload(),
                status="failed",
                current_stage="failed",
                agent_run_id=store.run_id,
                plan_json=plan.model_dump(mode="json") if plan is not None else {},
                evidence_json=evidence_pack.model_dump(mode="json") if evidence_pack is not None else {},
                review_json=review_report.model_dump(mode="json") if review_report is not None else {},
                metrics_json=metrics,
                previous_response_ids=dict(self.previous_response_ids),
                input_json=normalized_input,
                attachment_json=attachment_payload,
                candidate_drafts_json=candidate_drafts_json,
                selected_draft_id=selected_draft_id,
                error_message=str(exc),
            )

    def _build_context_pack(
        self,
        *,
        topic: str,
        research_question: str | None,
    ) -> WorkspaceContextPack:
        if self.db is not None and self.user is not None and self.workspace is not None:
            return build_workspace_context_pack(
                self.db,
                user=self.user,
                workspace=self.workspace,
                topic=topic,
                research_question=research_question,
            )
        return WorkspaceContextPack(
            workspace_id=self.workspace.id if self.workspace else None,
            topic=topic,
            research_question=research_question,
            summary="No workspace context available for this run.",
            snippets=[],
        )

    def _trace(self, stage: str, event: str, **details: Any) -> None:
        self.trace_events.append(
            AgentRunTraceEvent(
                timestamp=_utc_iso(),
                stage=stage,
                event=event,
                details=details,
            )
        )

    def _record_external_event(self, payload: dict[str, Any]) -> None:
        self.trace_events.append(
            AgentRunTraceEvent(
                timestamp=_utc_iso(),
                stage=str(payload.get("stage") or "researching"),
                event=str(payload.get("event") or "tool"),
                details={key: value for key, value in payload.items() if key not in {"stage", "event"}},
            )
        )

    def _trace_payload(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self.trace_events]

    def _save_previous_response_id(self, agent_name: str, response_id: str | None) -> None:
        if response_id:
            self.previous_response_ids[agent_name] = response_id

    def _build_metrics(
        self,
        plan: ResearchPlan | None,
        evidence_pack: EvidencePack | None,
        review_report: ReviewReport | None,
        *,
        draft_markdown: str | None,
        draft_attempts: int,
        candidate_drafts: list[CandidateDraftSummary],
        attachment_count: int,
    ) -> dict[str, Any]:
        evidence_ids = evidence_pack.included_source_ids if evidence_pack else []
        cited_ids = []
        if draft_markdown and evidence_pack is not None:
            cited_ids = [
                source_id
                for source_id in extract_source_ids(draft_markdown)
                if source_id in set(evidence_ids)
            ]
        citation_coverage = round(len(cited_ids) / max(len(evidence_ids), 1), 3) if evidence_ids else 0.0
        return {
            "draft_attempts": draft_attempts,
            "plan_query_count": len(plan.queries) if plan else 0,
            "evidence_count": len(evidence_pack.items) if evidence_pack else 0,
            "citation_coverage": citation_coverage,
            "unsupported_claim_count": review_report.unsupported_claim_count if review_report else 0,
            "missing_section_count": len(review_report.missing_sections) if review_report else 0,
            "invalid_source_id_count": len(review_report.invalid_source_ids) if review_report else 0,
            "review_finding_count": len(review_report.findings) if review_report else 0,
            "review_blocked": bool(review_report and review_report.status != "approved"),
            "review_status": review_report.status if review_report else "pending",
            "candidate_draft_count": len(candidate_drafts),
            "selected_draft_id": review_report.selected_draft_id if review_report else "",
            "attachment_count": attachment_count,
            "tool_choice_correctness": 1.0
            if (self.session.consulted_source_ids or any(item.modality in {"pdf", "image", "attachment"} for item in (evidence_pack.items if evidence_pack else [])))
            else 0.0,
            "reviewer_human_agreement": None,
            "arbiter_math_mode": self.math_mode,
            "arbiter_candidate_selection": [
                {
                    "draft_id": candidate.draft_id,
                    "status": candidate.status,
                    "score": candidate.score,
                    "arbiter": dict(candidate.metadata or {}).get("arbiter", {}),
                }
                for candidate in candidate_drafts
            ],
            "previous_response_ids": dict(self.previous_response_ids),
            "runtime_bundle_id": str(self.runtime_bundle.get("id") or ""),
            "runtime_bundle_version": str(self.runtime_bundle.get("version") or ""),
        }
