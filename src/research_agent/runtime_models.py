from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStage = Literal[
    "queued",
    "planned",
    "researching",
    "drafting",
    "reviewing",
    "approved",
    "blocked",
    "failed",
    "saved",
]

FindingSeverity = Literal["high", "medium", "low"]
ResearchMode = Literal["standard", "deep_research"]
QueueStatus = Literal["idle", "queued", "claimed", "completed", "failed"]
PublishStatus = Literal["unpublished", "published"]
StageName = Literal["planner", "researcher", "writer", "reviewer"]
RuntimeBundleStatus = Literal["draft", "published", "archived"]


class AttachmentPageRef(BaseModel):
    page_number: int = 1
    label: str = ""
    excerpt: str = ""


class RunAttachment(BaseModel):
    source_id: str
    asset_id: str
    title: str
    kind: str
    mime_type: str = ""
    file_name: str = ""
    description: str = ""
    page_refs: list[AttachmentPageRef] = Field(default_factory=list)
    extracted_text: str = ""
    caption: str = ""
    usable_by_vision_model: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_content: dict[str, Any] | None = Field(default=None, exclude=True)


class ResearchRunRequest(BaseModel):
    topic: str
    question: str | None = None
    instructions: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    case_id: str | None = None
    runtime_profile_id: str | None = None
    draft_variants: int | None = None
    mode: ResearchMode = "standard"


class ResearchRunRetryRequest(BaseModel):
    instructions: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    draft_variants: int | None = None


class TeamCreateRequest(BaseModel):
    name: str
    description: str = ""


class WorkspaceTeamAttachRequest(BaseModel):
    team_id: str


class ProviderCapabilityMatrix(BaseModel):
    provider_kind: str
    supports_structured_output: bool = False
    supports_tool_calls: bool = False
    supports_multimodal_input: bool = False
    supports_long_form_writing: bool = True


class StageProviderBinding(BaseModel):
    stage: StageName
    integration_id: str
    model_override: str = ""
    fallback_integration_ids: list[str] = Field(default_factory=list)


class RuntimeProfileRequest(BaseModel):
    name: str
    description: str = ""
    is_default: bool = False
    bindings: list[StageProviderBinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeProfileSummary(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str = ""
    is_default: bool = False
    bindings: list[StageProviderBinding] = Field(default_factory=list)
    active_bundle_id: str | None = None
    active_bundle_version: str = ""
    health: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchRunPublishRequest(BaseModel):
    team_id: str
    title: str = ""
    summary: str = ""


class KnowledgePublishRequest(BaseModel):
    team_id: str
    title: str = ""
    summary: str = ""


class TeamLibraryCloneRequest(BaseModel):
    workspace_id: str
    title: str = ""
    include_source_metadata: bool = True


class RuntimeBundleApplyRequest(BaseModel):
    runtime_profile_id: str | None = None


class ScoreCheck(BaseModel):
    key: str
    label: str
    passed: bool = False
    detail: str = ""


class ScoreDimension(BaseModel):
    key: str
    label: str
    score: int = 0
    checks: list[ScoreCheck] = Field(default_factory=list)


class EngineeringGateCheck(BaseModel):
    key: str
    label: str
    passed: bool = False
    detail: str = ""


class EngineeringGateReport(BaseModel):
    passed: bool = False
    checks: list[EngineeringGateCheck] = Field(default_factory=list)
    checked_at: str = ""
    source: str = "missing"


class DeliveryReviewReport(BaseModel):
    resource_type: Literal["agent_run", "knowledge_record"]
    resource_id: str
    business_score: int = 0
    business_deliverable: bool = False
    engineering_gate_passed: bool = False
    deliverable: bool = False
    publish_allowed: bool = False
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    checks: list[ScoreCheck] = Field(default_factory=list)
    checked_at: str


class RunQualitySnapshot(BaseModel):
    run_id: str
    status: str
    current_stage: str
    queue_status: str = ""
    quality_score: int = 0
    business_deliverable: bool = False
    citation_coverage: float = 0.0
    unsupported_claim_rate: float = 1.0
    review_block_precision: float = 0.0
    provider_kinds: list[str] = Field(default_factory=list)
    runtime_bundle_id: str = ""
    runtime_bundle_version: str = ""
    review_status: str = ""
    blocked_reason: str = ""
    deliverable: bool = False
    publish_allowed: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    delivery_review: DeliveryReviewReport | None = None


class BundleQualitySnapshot(BaseModel):
    bundle_id: str
    version: str
    status: RuntimeBundleStatus = "draft"
    total_score: int = 0
    deliverable: bool = False
    citation_coverage: float = 0.0
    unsupported_claim_rate: float = 1.0
    review_block_precision: float = 0.0
    golden_eval_pass_rate: float = 0.0


class DeliveryScorecard(BaseModel):
    workspace_id: str
    active_bundle_id: str = ""
    active_bundle_version: str = ""
    dimensions: list[ScoreDimension] = Field(default_factory=list)
    total_score: int = 0
    business_deliverable: bool = False
    engineering_gate: EngineeringGateReport | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    deliverable: bool = False
    generated_at: str


class RuntimeBundleVersion(BaseModel):
    id: str
    workspace_id: str
    name: str
    version: str
    status: RuntimeBundleStatus = "draft"
    published_at: str | None = None
    created_at: str


class RuntimeBundleSummary(BaseModel):
    id: str
    workspace_id: str
    name: str
    version: str
    status: RuntimeBundleStatus = "draft"
    prompts: dict[str, Any] = Field(default_factory=dict)
    rubric: dict[str, Any] = Field(default_factory=dict)
    routing_policy: dict[str, Any] = Field(default_factory=dict)
    review_thresholds: dict[str, Any] = Field(default_factory=dict)
    delivery_thresholds: dict[str, Any] = Field(default_factory=dict)
    eval_baseline: dict[str, Any] = Field(default_factory=dict)
    score: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    published_at: str | None = None
    created_at: str
    updated_at: str


class ResearchQuery(BaseModel):
    query: str
    rationale: str = ""
    priority: Literal["high", "medium", "low"] = "medium"


class ResearchPlan(BaseModel):
    topic: str
    research_question: str | None = None
    preferred_language: str = "Chinese"
    queries: list[ResearchQuery] = Field(default_factory=list)
    must_answer_questions: list[str] = Field(default_factory=list)
    screening_criteria: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(
        default_factory=lambda: [
            "Topic",
            "Research Question",
            "Executive Summary",
            "Key Papers",
            "Methodological Patterns",
            "Research Gaps",
            "Suggested Next Reads",
            "References",
        ]
    )
    target_source_count: int = 5
    open_access_only: bool = False
    require_pdf_for_methods: bool = True
    planning_notes: str = ""


class EvidenceItem(BaseModel):
    source_id: str
    title: str
    modality: Literal["text", "pdf", "image", "attachment"] = "text"
    query_used: str = ""
    publication_year: int | None = None
    cited_by_count: int = 0
    venue: str = ""
    abstract_excerpt: str = ""
    evidence_excerpt: str = ""
    evidence_level: Literal["abstract", "pdf_excerpt", "attachment_excerpt", "image_caption"] = "abstract"
    selection_reason: str = ""
    asset_id: str | None = None
    page_ref: str = ""
    region_ref: str = ""
    risk_flags: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    topic: str
    research_question: str | None = None
    items: list[EvidenceItem] = Field(default_factory=list)
    included_source_ids: list[str] = Field(default_factory=list)
    queries_used: list[str] = Field(default_factory=list)
    research_summary: str = ""


class ContextSnippet(BaseModel):
    source_type: Literal["memory", "note", "briefing", "literature"]
    record_id: str
    title: str
    excerpt: str
    relevance_score: int = 0


class WorkspaceContextPack(BaseModel):
    workspace_id: str | None = None
    topic: str = ""
    research_question: str | None = None
    summary: str = ""
    snippets: list[ContextSnippet] = Field(default_factory=list)

    def to_prompt_block(self) -> str:
        lines = [self.summary.strip() or "No relevant workspace context found."]
        for snippet in self.snippets:
            lines.extend(
                [
                    f"[{snippet.source_type}] {snippet.title}",
                    snippet.excerpt,
                    "",
                ]
            )
        return "\n".join(lines).strip()


class ReviewFinding(BaseModel):
    severity: FindingSeverity
    code: str
    message: str
    source_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class ReviewModelFeedback(BaseModel):
    summary: str = ""
    approve: bool = True
    findings: list[ReviewFinding] = Field(default_factory=list)


class CandidateDraftSummary(BaseModel):
    draft_id: str
    variant_index: int = 1
    status: Literal["approved", "blocked"] = "blocked"
    score: float = 0.0
    summary: str = ""
    cited_source_ids: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    invalid_source_ids: list[str] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    finding_count: int = 0
    draft_preview: str = ""


class ReviewReport(BaseModel):
    status: Literal["approved", "blocked"]
    allow_save: bool
    summary: str = ""
    findings: list[ReviewFinding] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    invalid_source_ids: list[str] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    selected_draft_id: str | None = None
    candidate_drafts: list[CandidateDraftSummary] = Field(default_factory=list)


class AgentRunTraceEvent(BaseModel):
    timestamp: str
    stage: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)
