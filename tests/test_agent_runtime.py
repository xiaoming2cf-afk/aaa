from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from research_agent.config import Settings
from research_agent.entities import AgentRun, KnowledgeRecord, User, Workspace, WorkspaceMemory
from research_agent.models import WorkRecord
from research_agent.orchestrator import (
    AgentStepResult,
    DraftValidationError,
    PlannerAgent,
    ResearchOrchestrator,
    ReviewerAgent,
    WriterAgent,
    WriterDraft,
)
from research_agent.quality_center import build_delivery_scorecard
from research_agent.research_tools import ResearchSession
from research_agent.runtime_models import EvidenceItem, EvidencePack, ResearchPlan, ReviewReport, WorkspaceContextPack
from research_agent.runtime_models import ResearchRunRequest, RunAttachment
from research_agent.service import claim_queued_agent_run
from research_agent.workspace_context import build_workspace_context_pack


REQUIRED_SECTIONS = [
    "Topic",
    "Research Question",
    "Executive Summary",
    "Key Papers",
    "Methodological Patterns",
    "Research Gaps",
    "Suggested Next Reads",
    "References",
]


class _FakeResponse:
    def __init__(self, response_id: str, *, output_parsed=None, output_text: str = "") -> None:
        self.id = response_id
        self.output_parsed = output_parsed
        self.output_text = output_text
        self.output = []


class _FakeResponsesAPI:
    def __init__(self, *, parse_queue=None, create_queue=None) -> None:
        self.parse_queue = list(parse_queue or [])
        self.create_queue = list(create_queue or [])
        self.parse_calls: list[dict] = []
        self.create_calls: list[dict] = []

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self.parse_queue.pop(0)

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_queue.pop(0)


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        openai_api_key="",
        reports_dir=tmp_path / "reports",
        storage_dir=tmp_path / "storage",
        database_url=f"sqlite:///{(tmp_path / 'agent-runtime.db').as_posix()}",
    )
    settings.ensure_directories()
    return settings


def _seed_source(session: ResearchSession, *, source_id: str, title: str) -> None:
    session.sources[source_id] = WorkRecord(
        source_id=source_id,
        openalex_id=f"https://openalex.org/{source_id}",
        title=title,
        authors=["Test Author"],
        abstract=f"{title} explains inflation dynamics with empirical evidence.",
        publication_year=2024,
        cited_by_count=42,
        venue="Journal of Tests",
        raw={},
    )
    session.consulted_source_ids = [*session.consulted_source_ids, source_id]


def _report_text(*, key_papers_citation: str = "[S1]", unsupported: bool = False) -> str:
    unsupported_paragraph = (
        "Researchers across all countries and all episodes reached the same conclusions "
        "about wage pass-through, pricing power, and inflation persistence without any "
        "meaningful heterogeneity in the evidence base, which should force the reviewer "
        "to block the draft because the paragraph makes large claims without citations."
        if unsupported
        else f"Researchers compare supply and demand channels with complementary evidence {key_papers_citation}."
    )
    return "\n\n".join(
        [
            "# Topic",
            "Post-pandemic inflation dynamics",
            "# Research Question",
            "What explains post-pandemic inflation persistence?",
            "# Executive Summary",
            "The literature points to a combination of supply bottlenecks and demand normalization [S1].",
            "# Key Papers",
            f"Core comparative evidence comes from a small set of macro papers {key_papers_citation}.",
            "# Methodological Patterns",
            unsupported_paragraph,
            "# Research Gaps",
            "Cross-country labor-market transmission remains under-studied [S1].",
            "# Suggested Next Reads",
            "A focused wage-setting paper would deepen the comparison [S1].",
            "# References",
            "- [S1] Inflation paper",
        ]
    )


class _StaticPlanner:
    def __init__(self, plan: ResearchPlan) -> None:
        self.plan = plan
        self.calls: list[str | None] = []

    def run(self, **kwargs) -> AgentStepResult[ResearchPlan]:
        self.calls.append(kwargs.get("previous_response_id"))
        return AgentStepResult(value=self.plan, response_id="planner-r1")


class _StaticResearcher:
    def __init__(self, evidence_pack: EvidencePack) -> None:
        self.evidence_pack = evidence_pack
        self.calls: list[str | None] = []

    def run(self, **kwargs) -> AgentStepResult[EvidencePack]:
        self.calls.append(kwargs.get("previous_response_id"))
        return AgentStepResult(value=self.evidence_pack, response_id="researcher-r1")


class _SequencedWriter:
    def __init__(self, drafts: list[str]) -> None:
        self.drafts = list(drafts)
        self.calls: list[str | None] = []

    def run(self, **kwargs) -> AgentStepResult[WriterDraft]:
        self.calls.append(kwargs.get("previous_response_id"))
        draft = self.drafts.pop(0)
        response_id = f"writer-r{len(self.calls)}"
        cited_source_ids = [source_id for source_id in ["S1", "S2"] if source_id in draft]
        return AgentStepResult(
            value=WriterDraft(draft_markdown=draft, cited_source_ids=cited_source_ids),
            response_id=response_id,
        )


class _SequencedReviewer:
    def __init__(self, reviews: list[ReviewReport]) -> None:
        self.reviews = list(reviews)
        self.calls: list[str | None] = []

    def run(self, **kwargs) -> AgentStepResult[ReviewReport]:
        self.calls.append(kwargs.get("previous_response_id"))
        review = self.reviews.pop(0)
        response_id = f"reviewer-r{len(self.calls)}"
        return AgentStepResult(value=review, response_id=response_id)


def test_planner_agent_enforces_structured_schema(tmp_path: Path):
    settings = _settings(tmp_path)
    fake_api = _FakeResponsesAPI(parse_queue=[_FakeResponse("planner-1", output_parsed={"queries": []})])
    agent = PlannerAgent(settings=settings, client=SimpleNamespace(responses=fake_api))

    with pytest.raises(ValidationError):
        agent.run(
            topic="Inflation persistence",
            research_question="What drives inflation persistence?",
            preferred_language="Chinese",
            context_pack=WorkspaceContextPack(
                topic="Inflation persistence",
                research_question="What drives inflation persistence?",
                summary="No workspace context.",
            ),
        )


def test_research_run_request_and_attachment_schema():
    request = ResearchRunRequest(
        topic="Inflation persistence",
        question="What drives inflation persistence?",
        instructions="Focus on wage dynamics.",
        asset_ids=["asset-1"],
        case_id="case-1",
        draft_variants=2,
        mode="deep_research",
    )
    assert request.mode == "deep_research"
    assert request.asset_ids == ["asset-1"]

    attachment = RunAttachment(
        source_id="A1",
        asset_id="asset-1",
        title="CPI chart",
        kind="chart_png",
        mime_type="image/png",
        caption="Inflation acceleration chart.",
        usable_by_vision_model=True,
    )
    assert attachment.source_id == "A1"
    assert attachment.usable_by_vision_model is True

    with pytest.raises(ValidationError):
        RunAttachment(
            asset_id="asset-1",
            title="Broken attachment",
            kind="chart_png",
        )


def test_writer_agent_rejects_citations_outside_evidence_pack(tmp_path: Path):
    settings = _settings(tmp_path)
    fake_api = _FakeResponsesAPI(create_queue=[_FakeResponse("writer-1", output_text=_report_text(key_papers_citation="[S9]"))])
    agent = WriterAgent(settings=settings, client=SimpleNamespace(responses=fake_api))
    plan = ResearchPlan(
        topic="Inflation persistence",
        research_question="What drives inflation persistence?",
        preferred_language="Chinese",
        required_sections=REQUIRED_SECTIONS,
    )
    evidence_pack = EvidencePack(
        topic=plan.topic,
        research_question=plan.research_question,
        items=[
            EvidenceItem(
                source_id="S1",
                title="Inflation paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Core source.",
            )
        ],
        included_source_ids=["S1"],
    )

    with pytest.raises(DraftValidationError) as exc:
        agent.run(
            plan=plan,
            evidence_pack=evidence_pack,
            context_pack=SimpleNamespace(to_prompt_block=lambda: "No workspace context."),
        )

    assert "S9" in str(exc.value)


def test_reviewer_agent_blocks_unsupported_claims():
    reviewer = ReviewerAgent(use_model_feedback=False)
    plan = ResearchPlan(
        topic="Inflation persistence",
        research_question="What drives inflation persistence?",
        preferred_language="Chinese",
        required_sections=REQUIRED_SECTIONS,
    )
    evidence_pack = EvidencePack(
        topic=plan.topic,
        research_question=plan.research_question,
        items=[
            EvidenceItem(
                source_id="S1",
                title="Inflation paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Core source.",
            )
        ],
        included_source_ids=["S1"],
    )

    result = reviewer.run(
        plan=plan,
        evidence_pack=evidence_pack,
        draft_markdown=_report_text(unsupported=True),
    )

    assert result.value.status == "blocked"
    assert result.value.allow_save is False
    assert result.value.unsupported_claim_count >= 1
    assert any(finding.code == "unsupported_claims" for finding in result.value.findings)


def test_claim_queued_run_reclaims_expired_lease(app, db_session):
    user = User(email="queue@example.com", full_name="Queue Tester", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Queue Lab", slug="queue-lab", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()
    run = AgentRun(
        owner_user_id=user.id,
        workspace_id=workspace.id,
        session_id="queue-session",
        topic="Queue reclaim",
        question="Does lease reclaim work?",
        language="Chinese",
        status="running",
        current_stage="researching",
        queue_status="claimed",
        worker_id="stale-worker",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db_session.add(run)
    db_session.commit()

    claimed = claim_queued_agent_run(db=db_session, worker_id="new-worker")

    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.worker_id == "new-worker"
    assert claimed.queue_status == "claimed"
    assert claimed.lease_expires_at is not None


def test_delivery_scorecard_reaches_500_when_all_gates_pass(app, db_session):
    user = User(email="score@example.com", full_name="Score Tester", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Score Lab", slug="score-lab", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()

    run = AgentRun(
        owner_user_id=user.id,
        workspace_id=workspace.id,
        session_id="perfect-run",
        topic="Perfect run",
        question="Can the scorecard hit 500?",
        language="Chinese",
        status="saved",
        current_stage="saved",
        queue_status="completed",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Topic\nPerfect run\n\n# References\n- [S1] Perfect paper",
        report_path="storage/reports/perfect-run/report.md",
        quality_json={"quality_score": 100},
    )
    db_session.add(run)
    db_session.commit()

    scorecard = build_delivery_scorecard(db_session, user=user, workspace=workspace)

    assert scorecard["total_score"] == 500
    assert scorecard["business_deliverable"] is True
    assert scorecard["deliverable"] is False
    assert all(item["score"] == 100 for item in scorecard["dimensions"])
    assert scorecard["active_bundle"] is None


def test_orchestrator_retries_blocked_draft_and_persists_agent_run(app, db_session, tmp_path: Path):
    user = User(email="orchestrator@example.com", full_name="Runtime Tester", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Macro Lab", slug="macro-lab", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()

    session = ResearchSession(tmp_path / "runtime-session")
    _seed_source(session, source_id="S1", title="Inflation paper")
    _seed_source(session, source_id="S2", title="Wage setting paper")

    plan = ResearchPlan(
        topic="Inflation persistence",
        research_question="What drives inflation persistence?",
        preferred_language="Chinese",
        required_sections=REQUIRED_SECTIONS,
    )
    evidence_pack = EvidencePack(
        topic=plan.topic,
        research_question=plan.research_question,
        items=[
            EvidenceItem(
                source_id="S1",
                title="Inflation paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Core source.",
            ),
            EvidenceItem(
                source_id="S2",
                title="Wage setting paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Follow-on source.",
            ),
        ],
        included_source_ids=["S1", "S2"],
    )
    writer = _SequencedWriter(
        [
            _report_text(unsupported=True),
            _report_text(key_papers_citation="[S1] [S2]", unsupported=False),
        ]
    )
    reviewer = _SequencedReviewer(
        [
            ReviewReport(
                status="blocked",
                allow_save=False,
                summary="Missing support in methodology section.",
                findings=[],
                unsupported_claim_count=1,
            ),
            ReviewReport(
                status="approved",
                allow_save=True,
                summary="Approved.",
                findings=[],
            ),
        ]
    )

    orchestrator = ResearchOrchestrator(
        settings=_settings(tmp_path),
        session=session,
        db=db_session,
        user=user,
        workspace=workspace,
        planner=_StaticPlanner(plan),
        researcher=_StaticResearcher(evidence_pack),
        writer=writer,
        reviewer=reviewer,
        max_draft_attempts=2,
    )

    result = orchestrator.run(
        topic=plan.topic,
        research_question=plan.research_question,
        preferred_language=plan.preferred_language,
    )

    assert result.status == "saved"
    assert Path(result.report_path).exists()
    assert Path(result.bibtex_path).exists()
    assert Path(result.sources_path).exists()
    assert writer.calls == [None, "writer-r1"]
    assert reviewer.calls == [None, "reviewer-r1"]
    assert result.previous_response_ids == {
        "planner": "planner-r1",
        "researcher": "researcher-r1",
        "writer": "writer-r2",
        "reviewer": "reviewer-r2",
    }

    record = db_session.scalar(select(AgentRun).where(AgentRun.id == result.agent_run_id))
    assert record is not None
    assert record.status == "saved"
    assert record.current_stage == "saved"
    assert (record.review_json or {}).get("status") == "approved"
    assert (record.metrics_json or {}).get("draft_attempts") == 2
    assert Path(session.session_dir / "agent_run.json").exists()


def test_orchestrator_selects_best_candidate_variant(app, db_session, tmp_path: Path):
    user = User(email="variants@example.com", full_name="Variant Tester", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Variant Lab", slug="variant-lab", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()

    session = ResearchSession(tmp_path / "variant-session")
    _seed_source(session, source_id="S1", title="Inflation paper")
    _seed_source(session, source_id="S2", title="Wage setting paper")

    plan = ResearchPlan(
        topic="Inflation persistence",
        research_question="What drives inflation persistence?",
        preferred_language="Chinese",
        required_sections=REQUIRED_SECTIONS,
    )
    evidence_pack = EvidencePack(
        topic=plan.topic,
        research_question=plan.research_question,
        items=[
            EvidenceItem(
                source_id="S1",
                title="Inflation paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Core source.",
            ),
            EvidenceItem(
                source_id="S2",
                title="Wage setting paper",
                abstract_excerpt="Relevant abstract.",
                evidence_excerpt="Relevant evidence.",
                selection_reason="Follow-on source.",
            ),
        ],
        included_source_ids=["S1", "S2"],
    )
    writer = _SequencedWriter(
        [
            _report_text(key_papers_citation="[S1]", unsupported=False),
            _report_text(key_papers_citation="[S1] [S2]", unsupported=False),
        ]
    )
    reviewer = _SequencedReviewer(
        [
            ReviewReport(
                status="approved",
                allow_save=True,
                summary="Adequate support.",
                findings=[],
            ),
            ReviewReport(
                status="approved",
                allow_save=True,
                summary="Stronger support and broader citations.",
                findings=[],
            ),
        ]
    )

    orchestrator = ResearchOrchestrator(
        settings=_settings(tmp_path),
        session=session,
        db=db_session,
        user=user,
        workspace=workspace,
        planner=_StaticPlanner(plan),
        researcher=_StaticResearcher(evidence_pack),
        writer=writer,
        reviewer=reviewer,
        max_draft_attempts=1,
    )

    result = orchestrator.run(
        topic=plan.topic,
        research_question=plan.research_question,
        preferred_language=plan.preferred_language,
        draft_variants=2,
    )

    assert result.status == "saved"
    assert result.selected_draft_id == "D1-2"
    assert len(result.candidate_drafts_json) == 2
    assert [item["draft_id"] for item in result.candidate_drafts_json] == ["D1-1", "D1-2"]
    assert result.review_json["selected_draft_id"] == "D1-2"

    record = db_session.scalar(select(AgentRun).where(AgentRun.id == result.agent_run_id))
    assert record is not None
    assert record.selected_draft_id == "D1-2"
    assert len(record.candidate_drafts_json or []) == 2


def test_workspace_context_pack_only_keeps_relevant_memory(app, db_session):
    user = User(email="context@example.com", full_name="Context Tester", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Context Lab", slug="context-lab", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()

    db_session.add_all(
        [
            WorkspaceMemory(
                workspace_id=workspace.id,
                owner_user_id=user.id,
                title="Inflation expectations note",
                content="Inflation expectations affect bargaining, wage setting, and price persistence.",
            ),
            WorkspaceMemory(
                workspace_id=workspace.id,
                owner_user_id=user.id,
                title="Travel checklist",
                content="Book hotels and compare airline prices for summer vacation.",
            ),
            KnowledgeRecord(
                workspace_id=workspace.id,
                owner_user_id=user.id,
                title="Wage adjustment memo",
                content="Nominal wage rigidity changes the pass-through from expectations to inflation.",
                tags_json=["inflation"],
                metadata_json={},
            ),
        ]
    )
    db_session.flush()

    pack = build_workspace_context_pack(
        db_session,
        user=user,
        workspace=workspace,
        topic="inflation expectations",
        research_question="How do inflation expectations affect wage setting?",
    )

    titles = [snippet.title for snippet in pack.snippets]
    assert "Inflation expectations note" in titles
    assert "Wage adjustment memo" in titles
    assert "Travel checklist" not in titles
