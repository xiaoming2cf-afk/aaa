from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from research_agent.entities import AgentRun, KnowledgeRecord, User, Workspace
from research_agent.config import Settings
import research_agent.quality_center as quality_center
from research_agent.quality_center import (
    build_agent_run_delivery_review,
    build_delivery_scorecard,
    build_knowledge_record_delivery_review,
    load_engineering_gate_report,
    scan_production_imports,
    scan_runtime_narrative,
)


def _passed_engineering_gate() -> dict[str, object]:
    return {
        "passed": True,
        "checks": [],
        "checked_at": "2026-01-01T00:00:00+00:00",
        "source": "test",
    }


def _failed_engineering_gate() -> dict[str, object]:
    return {
        "passed": False,
        "checks": [{"key": "backend_tests_green", "label": "Backend pytest suite passes", "passed": False, "detail": "failed"}],
        "checked_at": "2026-01-01T00:00:00+00:00",
        "source": "test",
    }


def _unique_token() -> str:
    return uuid4().hex[:8]


def _math_settings(tmp_path: Path, *, mode: str = "active") -> Settings:
    settings = Settings(
        app_env="test",
        app_secret="test-secret-with-sufficient-length-1234567890",
        storage_dir=tmp_path / "storage",
        reports_dir=tmp_path / "reports",
        database_url=f"sqlite:///{(tmp_path / 'quality-review.db').as_posix()}",
        agent_math_mode=mode,
    )
    settings.ensure_directories()
    return settings


def test_agent_run_delivery_review_requires_all_checks():
    run = AgentRun(
        id="run-1",
        status="saved",
        current_stage="saved",
        report_path="storage/reports/run-1/report.md",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Report",
    )

    passing = build_agent_run_delivery_review(run, engineering_gate=_passed_engineering_gate())
    assert passing["publish_allowed"] is True
    assert passing["deliverable"] is True

    run.metrics_json = {"citation_coverage": 0.5, "unsupported_claim_count": 1}
    failing = build_agent_run_delivery_review(run, engineering_gate=_passed_engineering_gate())
    assert failing["publish_allowed"] is False
    assert any("Citation coverage equals 1.00" in reason for reason in failing["blocking_reasons"])


def test_agent_run_delivery_review_exposes_arbiter_delivery_posterior(tmp_path: Path):
    settings = _math_settings(tmp_path, mode="active")
    run = AgentRun(
        id="run-math",
        status="saved",
        current_stage="saved",
        report_path="storage/reports/run-math/report.md",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Report",
    )

    review = build_agent_run_delivery_review(run, settings=settings, engineering_gate=_passed_engineering_gate())

    assert review["metadata"]["arbiter"]["mode"] == "active"
    assert 0.0 <= review["metadata"]["arbiter"]["delivery_posterior"] <= 1.0
    assert review["metadata"]["arbiter"]["deliverable_proxy"] is True
    assert review["metadata"]["arbiter"]["v2"]["chosen_deliverable"] is True
    assert review["metadata"]["arbiter"]["v2"]["comparison"]["fallback_reason"] == "proposed_choice_matches_baseline"


def test_knowledge_record_delivery_review_handles_manual_and_agent_derived(db_session):
    token = _unique_token()
    user = User(email=f"knowledge-review-{token}@example.com", full_name="Knowledge Review", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Knowledge Review", slug=f"knowledge-review-{token}", description="Test")
    db_session.add(user)
    db_session.flush()
    workspace.owner_user_id = user.id
    db_session.add(workspace)
    db_session.flush()

    run = AgentRun(
        owner_user_id=user.id,
        workspace_id=workspace.id,
        status="saved",
        current_stage="saved",
        report_path="storage/reports/run/report.md",
        review_json={"status": "approved", "summary": "Approved.", "missing_sections": [], "invalid_source_ids": [], "unsupported_claim_count": 0},
        metrics_json={"citation_coverage": 1.0, "unsupported_claim_count": 0},
        final_text="# Report",
        started_at=datetime.now(timezone.utc),
    )
    manual_record = KnowledgeRecord(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title="Manual note",
        content="A manually curated note.",
        metadata_json={"source_type": "workspace_note", "source": "manual"},
    )
    derived_record = KnowledgeRecord(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title="Derived note",
        content="A published agent report.",
        metadata_json={"source_type": "agent_report", "agent_run_id": run.id},
    )
    db_session.add_all([run, manual_record, derived_record])
    db_session.commit()

    manual_review = build_knowledge_record_delivery_review(db_session, manual_record, engineering_gate=_passed_engineering_gate())
    assert manual_review["publish_allowed"] is True

    derived_review = build_knowledge_record_delivery_review(db_session, derived_record, engineering_gate=_passed_engineering_gate())
    assert derived_review["publish_allowed"] is True

    blocked_review = build_knowledge_record_delivery_review(db_session, derived_record, engineering_gate=_failed_engineering_gate())
    assert blocked_review["publish_allowed"] is False
    assert any("Backend pytest suite passes" in reason for reason in blocked_review["blocking_reasons"])


def test_delivery_scorecard_requires_engineering_gate_even_with_500_business_score(db_session):
    token = _unique_token()
    user = User(email=f"scorecard-review-{token}@example.com", full_name="Scorecard Review", password_hash="hashed")
    workspace = Workspace(owner_user_id="", name="Scorecard Review", slug=f"scorecard-review-{token}", description="Test")
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

    blocked = build_delivery_scorecard(
        db_session,
        user=user,
        workspace=workspace,
        engineering_gate=_failed_engineering_gate(),
    )
    assert blocked["total_score"] == 500
    assert blocked["business_deliverable"] is True
    assert blocked["deliverable"] is False

    passing = build_delivery_scorecard(
        db_session,
        user=user,
        workspace=workspace,
        settings=_math_settings(Path(db_session.bind.url.database).parent if db_session.bind and db_session.bind.url.database else Path("."), mode="active"),
        engineering_gate=_passed_engineering_gate(),
    )
    assert passing["deliverable"] is True
    assert "arbiter" in passing["metadata"]
    assert passing["metadata"]["arbiter"]["mode"] == "active"
    assert "v2" in passing["metadata"]["arbiter"]
    assert isinstance(passing["metadata"]["arbiter"]["v2"]["recent_choices"], list)


def test_production_import_scan_detects_forbidden_dependency(tmp_path: Path):
    cli_path = tmp_path / "src" / "research_agent"
    cli_path.mkdir(parents=True)
    for relative_path in (
        "cli.py",
        "service.py",
        "webapp.py",
        "platform_research.py",
        "platform_core.py",
        "quality_center.py",
        "agent_diagnostics.py",
        "team_library.py",
    ):
        target = cli_path / relative_path
        target.write_text("pass\n", encoding="utf-8")
    (cli_path / "cli.py").write_text("from .runtime_provider import build_runtime_client\n", encoding="utf-8")

    violations = scan_production_imports(tmp_path)

    assert any("cli.py: runtime_provider" in item for item in violations)


def test_runtime_narrative_scan_detects_runtime_wording(tmp_path: Path):
    (tmp_path / "frontend-spa" / "src" / "pages").mkdir(parents=True)
    (tmp_path / "README.md").write_text("Run Ollama before starting the app.\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("OLLAMA_BASE_URL=http://127.0.0.1:11434/v1\n", encoding="utf-8")
    (tmp_path / "render.yaml").write_text("buildCommand: pip install -e .\nenvVars:\n  - key: RESEARCH_AGENT_MODEL\n", encoding="utf-8")
    for name in ("ResearchPage.tsx", "KnowledgePage.tsx", "QualityPage.tsx"):
        (tmp_path / "frontend-spa" / "src" / "pages" / name).write_text("Use OpenAI at runtime.\n", encoding="utf-8")
    (tmp_path / "frontend-spa" / "src" / "pages" / "ProvidersPage.tsx").write_text("Provider settings.\n", encoding="utf-8")

    violations = scan_runtime_narrative(tmp_path)

    assert any("README.md" in item for item in violations)
    assert any(".env.example" in item for item in violations)
    assert any("ResearchPage.tsx" in item for item in violations)
    assert any("ProvidersPage.tsx" in item for item in violations)
    assert any("render.yaml" in item for item in violations)


def test_production_engineering_gate_reads_commit_artifact_without_refresh(tmp_path: Path, monkeypatch):
    settings = _math_settings(tmp_path, mode="shadow").model_copy(update={"app_env": "production"})
    commit_sha = "abc123def456"
    monkeypatch.setenv("RESEARCH_AGENT_ENGINEERING_GATE_COMMIT", commit_sha)
    artifact_path = settings.storage_dir / "quality" / "gates" / f"engineering-gate.{commit_sha}.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": commit_sha,
                "passed": True,
                "checks": [
                    {
                        "key": "backend_tests_green",
                        "label": "Backend pytest suite passes",
                        "passed": True,
                        "detail": "passed",
                    }
                ],
                "checked_at": "2026-01-01T00:00:00+00:00",
                "source": "ci",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_command(*args, **kwargs):
        raise AssertionError("production quality paths must not execute local commands")

    monkeypatch.setattr(quality_center, "_run_command", fail_command)

    report = load_engineering_gate_report(settings, refresh=True, auto_refresh_if_missing=True)

    assert report["passed"] is True
    assert report["source"] == "artifact:abc123def456"


def test_production_engineering_gate_missing_artifact_fails_closed(tmp_path: Path, monkeypatch):
    settings = _math_settings(tmp_path, mode="shadow").model_copy(update={"app_env": "production"})
    monkeypatch.setenv("RESEARCH_AGENT_ENGINEERING_GATE_COMMIT", "missing123")

    def fail_command(*args, **kwargs):
        raise AssertionError("production quality paths must not execute local commands")

    monkeypatch.setattr(quality_center, "_run_command", fail_command)

    report = load_engineering_gate_report(settings, auto_refresh_if_missing=True)

    assert report["passed"] is False
    assert report["source"] == "artifact_missing"
    assert report["checks"][0]["key"] == "engineering_gate_artifact_missing"
