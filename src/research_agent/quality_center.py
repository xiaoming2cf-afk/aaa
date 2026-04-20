from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .entities import AgentRun, KnowledgeRecord, User, Workspace
from .runtime_models import (
    DeliveryReviewReport,
    DeliveryScorecard,
    EngineeringGateCheck,
    EngineeringGateReport,
    RunQualitySnapshot,
    ScoreCheck,
    ScoreDimension,
)

_ENGINEERING_GATE_FILENAME = "engineering-gate.json"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_PRODUCTION_IMPORT_TARGETS = (
    "src/research_agent/cli.py",
    "src/research_agent/service.py",
    "src/research_agent/webapp.py",
    "src/research_agent/platform_research.py",
    "src/research_agent/platform_core.py",
    "src/research_agent/quality_center.py",
    "src/research_agent/agent_diagnostics.py",
    "src/research_agent/team_library.py",
)
_FORBIDDEN_IMPORT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai", re.compile(r"^\s*(?:from|import)\s+openai\b", re.MULTILINE)),
    ("anthropic", re.compile(r"^\s*(?:from|import)\s+anthropic\b", re.MULTILINE)),
    ("google", re.compile(r"^\s*(?:from|import)\s+google(?:\.generativeai|\.genai)?\b", re.MULTILINE)),
    ("ollama", re.compile(r"^\s*(?:from|import)\s+ollama\b", re.MULTILINE)),
    ("vllm", re.compile(r"^\s*(?:from|import)\s+vllm\b", re.MULTILINE)),
    ("provider_gateway", re.compile(r"^\s*from\s+\.provider_gateway\s+import\b", re.MULTILINE)),
    ("runtime_provider", re.compile(r"^\s*from\s+\.runtime_provider\s+import\b", re.MULTILINE)),
    ("local_runtime", re.compile(r"^\s*from\s+\.local_runtime\s+import\b", re.MULTILINE)),
    ("runtime_bundles", re.compile(r"^\s*from\s+\.runtime_bundles\s+import\b", re.MULTILINE)),
    ("runtime_profiles", re.compile(r"^\s*from\s+\.runtime_profiles\s+import\b", re.MULTILINE)),
)
_RUNTIME_NARRATIVE_UI_FILES = (
    "frontend-spa/src/pages/ResearchPage.tsx",
    "frontend-spa/src/pages/KnowledgePage.tsx",
    "frontend-spa/src/pages/QualityPage.tsx",
)
_FORBIDDEN_RUNTIME_NARRATIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("readme_mentions_ollama", re.compile(r"\bollama\b", re.IGNORECASE)),
    ("readme_mentions_vllm", re.compile(r"\bvllm\b", re.IGNORECASE)),
    ("readme_mentions_gemini", re.compile(r"\bgemini\b", re.IGNORECASE)),
    ("readme_mentions_anthropic", re.compile(r"\banthropic\b", re.IGNORECASE)),
)
_MANUAL_SOURCE_METADATA_KEYS = (
    "source",
    "source_type",
    "source_url",
    "source_urls",
    "sources",
    "reference",
    "references",
    "detail_path",
    "briefing_id",
    "openalex_id",
    "publication",
    "agent_run_id",
)


class DeliveryGateError(ValueError):
    def __init__(
        self,
        *,
        message: str,
        delivery_review: dict[str, Any],
        engineering_gate: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.delivery_review = delivery_review
        self.engineering_gate = engineering_gate or {}

    def to_http_detail(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "delivery_review": self.delivery_review,
            "engineering_gate": self.engineering_gate,
            "allowed_actions": list(self.delivery_review.get("allowed_actions") or []),
            "blocked_actions": list(self.delivery_review.get("blocked_actions") or []),
            "blocking_reasons": list(self.delivery_review.get("blocking_reasons") or []),
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _web_dir() -> Path:
    return Path(__file__).with_name("web")


def _snapshot_path(settings: Any) -> Path | None:
    storage_dir = getattr(settings, "storage_dir", None)
    if not storage_dir:
        return None
    return Path(storage_dir).resolve() / "quality" / _ENGINEERING_GATE_FILENAME


def _load_snapshot(settings: Any) -> dict[str, Any] | None:
    path = _snapshot_path(settings)
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EngineeringGateReport.model_validate(payload).model_dump(mode="json")
    except Exception:
        return None


def _write_snapshot(settings: Any, report: dict[str, Any]) -> None:
    path = _snapshot_path(settings)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_engineering_gate(*, source: str = "missing") -> dict[str, Any]:
    return EngineeringGateReport(
        passed=False,
        checks=[
            EngineeringGateCheck(
                key="engineering_review_missing",
                label="Engineering review has been executed",
                passed=False,
                detail="No engineering gate snapshot is available yet.",
            )
        ],
        checked_at=_utc_now_iso(),
        source=source,
    ).model_dump(mode="json")


def _run_citation_coverage(run: AgentRun) -> float:
    metrics = dict(run.metrics_json or {}) if isinstance(run.metrics_json, dict) else {}
    try:
        return round(float(metrics.get("citation_coverage") or 0.0), 3)
    except (TypeError, ValueError):
        return 0.0


def _run_unsupported_claim_rate(run: AgentRun) -> float:
    metrics = dict(run.metrics_json or {}) if isinstance(run.metrics_json, dict) else {}
    review = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
    unsupported_claim_count = int(metrics.get("unsupported_claim_count") or review.get("unsupported_claim_count") or 0)
    return 0.0 if unsupported_claim_count == 0 else 1.0


def _run_review_block_precision(run: AgentRun) -> float:
    review = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
    review_status = str(review.get("status") or "").strip().lower()
    missing_sections = list(review.get("missing_sections") or [])
    invalid_source_ids = list(review.get("invalid_source_ids") or [])
    unsupported_claim_rate = _run_unsupported_claim_rate(run)
    issue_present = bool(missing_sections or invalid_source_ids or unsupported_claim_rate > 0)
    if review_status == "blocked":
        return 1.0 if issue_present else 0.0
    if review_status == "approved":
        return 1.0 if not issue_present else 0.0
    if review_status == "failed":
        return 1.0
    return 0.0


def _dimension(key: str, label: str, checks: list[ScoreCheck]) -> ScoreDimension:
    passed = all(check.passed for check in checks)
    return ScoreDimension(
        key=key,
        label=label,
        score=100 if passed else 0,
        checks=checks,
    )


def _workflow_integrity_checks(run_snapshots: list[dict[str, Any]]) -> list[ScoreCheck]:
    has_recent_runs = bool(run_snapshots)
    statuses_present = has_recent_runs and all(
        str(item.get("status") or "").strip() and str(item.get("current_stage") or "").strip()
        for item in run_snapshots
    )
    queue_state_present = has_recent_runs and all(str(item.get("queue_status") or "").strip() for item in run_snapshots)
    return [
        ScoreCheck(
            key="recent_runs_present",
            label="Recent research runs exist",
            passed=has_recent_runs,
            detail=str(len(run_snapshots)),
        ),
        ScoreCheck(
            key="run_statuses_recorded",
            label="Run status and stage are recorded",
            passed=statuses_present,
            detail="status/current_stage",
        ),
        ScoreCheck(
            key="queue_state_recorded",
            label="Queue state is recorded",
            passed=queue_state_present,
            detail="queue_status",
        ),
    ]


def _research_quality_checks(run_snapshots: list[dict[str, Any]]) -> tuple[list[ScoreCheck], dict[str, float]]:
    citation_coverage = min((float(item.get("citation_coverage") or 0.0) for item in run_snapshots), default=0.0)
    unsupported_claim_rate = max(
        (
            float(item["unsupported_claim_rate"])
            if item.get("unsupported_claim_rate") is not None
            else 1.0
            for item in run_snapshots
        ),
        default=1.0,
    )
    review_block_precision = min(
        (float(item.get("review_block_precision") or 0.0) for item in run_snapshots),
        default=0.0,
    )
    checks = [
        ScoreCheck(
            key="citation_coverage",
            label="Citation coverage equals 1.00",
            passed=citation_coverage == 1.0,
            detail=f"{citation_coverage:.2f}",
        ),
        ScoreCheck(
            key="unsupported_claim_rate",
            label="Unsupported claim rate equals 0.00",
            passed=unsupported_claim_rate == 0.0,
            detail=f"{unsupported_claim_rate:.2f}",
        ),
        ScoreCheck(
            key="review_block_precision",
            label="Review block precision equals 1.00",
            passed=review_block_precision == 1.0,
            detail=f"{review_block_precision:.2f}",
        ),
    ]
    return checks, {
        "citation_coverage": citation_coverage,
        "unsupported_claim_rate": unsupported_claim_rate,
        "review_block_precision": review_block_precision,
    }


def _artifact_checks(runs: list[AgentRun]) -> list[ScoreCheck]:
    saved_runs = [run for run in runs if (run.status or "").strip().lower() == "saved"]
    blocked_runs = [run for run in runs if (run.status or "").strip().lower() == "blocked"]
    saved_have_reports = bool(saved_runs) and all(
        bool(str(run.report_path or "").strip()) or bool(str(run.final_text or "").strip()) for run in saved_runs
    )
    blocked_not_published = all((run.publish_status or "unpublished") != "published" for run in blocked_runs)
    return [
        ScoreCheck(
            key="saved_runs_have_artifacts",
            label="Saved runs retain a report artifact",
            passed=saved_have_reports,
            detail=str(len(saved_runs)),
        ),
        ScoreCheck(
            key="blocked_runs_not_published",
            label="Blocked runs are not marked as published",
            passed=blocked_not_published,
            detail=str(len(blocked_runs)),
        ),
    ]


def _product_surface_checks() -> list[ScoreCheck]:
    repo_root = _repo_root()
    spa_root = repo_root / "frontend-spa"
    web_dir = _web_dir()
    route_sources = [
        spa_root / "src" / "pages" / "ResearchPage.tsx",
        spa_root / "src" / "pages" / "TeamLibraryPage.tsx",
        spa_root / "src" / "pages" / "KnowledgePage.tsx",
        spa_root / "src" / "pages" / "ProvidersPage.tsx",
        spa_root / "src" / "pages" / "QualityPage.tsx",
    ]
    return [
        ScoreCheck(
            key="spa_source_routes_present",
            label="SPA source routes are present",
            passed=all(path.exists() for path in route_sources),
            detail="frontend-spa source route files",
        ),
        ScoreCheck(
            key="legacy_pages_preserved",
            label="Legacy compatibility pages are preserved",
            passed=all(
                (web_dir / name).exists()
                for name in ("workspace.html", "research_agent.html", "provider_center.html", "knowledge_base.html")
            ),
            detail="legacy workspace/research/provider/knowledge pages",
        ),
    ]


def _publication_checks(runs: list[AgentRun]) -> list[ScoreCheck]:
    saved_runs = [run for run in runs if (run.status or "").strip().lower() == "saved"]
    knowledge_link_state = all(
        (run.workspace_knowledge_record_id or "") == "" or str(run.workspace_knowledge_record_id).strip()
        for run in runs
    )
    publish_state_recorded = all(str(run.publish_status or "unpublished").strip() for run in runs)
    return [
        ScoreCheck(
            key="publish_state_recorded",
            label="Publish state is recorded for recent runs",
            passed=publish_state_recorded,
            detail=str(len(runs)),
        ),
        ScoreCheck(
            key="knowledge_link_state_valid",
            label="Knowledge linkage fields remain consistent",
            passed=knowledge_link_state,
            detail=str(len(saved_runs)),
        ),
    ]


def _normalize_engineering_gate(engineering_gate: dict[str, Any] | EngineeringGateReport | None) -> dict[str, Any] | None:
    if engineering_gate is None:
        return None
    if isinstance(engineering_gate, EngineeringGateReport):
        return engineering_gate.model_dump(mode="json")
    return EngineeringGateReport.model_validate(engineering_gate).model_dump(mode="json")


def _load_agent_runs(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    limit: int = 20,
) -> list[AgentRun]:
    from .agent_diagnostics import list_agent_runs

    return list_agent_runs(db, user=user, workspace=workspace, limit=limit)


def _command_output_detail(result: subprocess.CompletedProcess[str]) -> str:
    combined = "\n".join(item for item in [result.stdout, result.stderr] if item).strip()
    if not combined:
        return f"exit={result.returncode}"
    combined = _ANSI_ESCAPE_RE.sub("", combined).replace("✓", "OK")
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    return "\n".join(lines[-6:])


def _run_command(command: list[str], *, cwd: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    return result.returncode == 0, _command_output_detail(result)


def _format_repo_hygiene_issues(issues: list[dict[str, Any]]) -> str:
    formatted: list[str] = []
    for issue in issues[:5]:
        path = str(issue.get("path") or "").strip()
        line_number = issue.get("line_number")
        kind = str(issue.get("kind") or "").strip()
        label = str(issue.get("label") or "").strip()
        location = f"{path}:{line_number}" if line_number else path
        summary = " / ".join(part for part in (kind, label) if part)
        formatted.append(": ".join(part for part in (location, summary) if part))
    return "; ".join(item for item in formatted if item)


def scan_production_imports(repo_root: Path | None = None) -> list[str]:
    root = repo_root or _repo_root()
    violations: list[str] = []
    for relative_path in _PRODUCTION_IMPORT_TARGETS:
        path = root / relative_path
        if not path.exists():
            violations.append(f"{relative_path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in _FORBIDDEN_IMPORT_PATTERNS:
            if pattern.search(text):
                violations.append(f"{relative_path}: {label}")
    return violations


def scan_runtime_narrative(repo_root: Path | None = None) -> list[str]:
    root = repo_root or _repo_root()
    violations: list[str] = []

    readme_path = root / "README.md"
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        for label, pattern in _FORBIDDEN_RUNTIME_NARRATIVE_PATTERNS:
            if pattern.search(readme_text):
                violations.append(f"README.md: {label}")
    else:
        violations.append("README.md: missing")

    env_path = root / ".env.example"
    if env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
        if "OLLAMA_" in env_text or "VLLM_" in env_text:
            violations.append(".env.example: local runtime variables still present")
        if "OPENAI_API_KEY" in env_text and "training-only" not in env_text.lower():
            violations.append(".env.example: OPENAI_API_KEY must remain training-only")
    else:
        violations.append(".env.example: missing")

    for relative_path in _RUNTIME_NARRATIVE_UI_FILES:
        path = root / relative_path
        if not path.exists():
            violations.append(f"{relative_path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b(?:openai|anthropic|gemini|ollama|vllm)\b", text, re.IGNORECASE):
            violations.append(f"{relative_path}: runtime provider wording present")

    provider_page = root / "frontend-spa" / "src" / "pages" / "ProvidersPage.tsx"
    if provider_page.exists():
        provider_text = provider_page.read_text(encoding="utf-8")
        if "not available in the current product scope" not in provider_text.lower():
            violations.append("frontend-spa/src/pages/ProvidersPage.tsx: disabled scope notice missing")
    else:
        violations.append("frontend-spa/src/pages/ProvidersPage.tsx: missing")

    render_path = root / "render.yaml"
    if render_path.exists():
        render_text = render_path.read_text(encoding="utf-8")
        if "frontend-spa" not in render_text or "npm run build" not in render_text:
            violations.append("render.yaml: SPA build step missing")
        if "RESEARCH_AGENT_MODEL" in render_text:
            violations.append("render.yaml: runtime model variable still present")
        if "OPENAI_API_KEY" in render_text:
            violations.append("render.yaml: training-only OpenAI variable must not be part of production deploy config")
    else:
        violations.append("render.yaml: missing")

    return violations


def load_engineering_gate_report(
    settings: Any | None = None,
    *,
    refresh: bool = False,
    auto_refresh_if_missing: bool = False,
) -> dict[str, Any]:
    snapshot = _load_snapshot(settings) if settings is not None else None
    if snapshot is not None and not refresh:
        snapshot["source"] = "snapshot"
        return EngineeringGateReport.model_validate(snapshot).model_dump(mode="json")
    if not refresh and not auto_refresh_if_missing:
        return _default_engineering_gate(source="missing")

    from .repo_hygiene import scan_repo_hygiene

    repo_root = _repo_root()
    repo_hygiene_issues = scan_repo_hygiene(repo_root)
    import_violations = scan_production_imports(repo_root)
    narrative_violations = scan_runtime_narrative(repo_root)
    backend_passed, backend_detail = _run_command([sys.executable, "-m", "pytest"], cwd=repo_root)

    frontend_dir = repo_root / "frontend-spa"
    if frontend_dir.exists():
        npm_command = ["npm.cmd", "run", "build"] if os.name == "nt" else ["npm", "run", "build"]
        frontend_passed, frontend_detail = _run_command(npm_command, cwd=frontend_dir)
    else:
        frontend_passed, frontend_detail = False, "frontend-spa directory is missing."

    report = EngineeringGateReport(
        passed=not any(
            (
                repo_hygiene_issues,
                import_violations,
                narrative_violations,
                not backend_passed,
                not frontend_passed,
            )
        ),
        checks=[
            EngineeringGateCheck(
                key="repo_hygiene_clean",
                label="Repository hygiene is clean",
                passed=not repo_hygiene_issues,
                detail="clean" if not repo_hygiene_issues else _format_repo_hygiene_issues(repo_hygiene_issues),
            ),
            EngineeringGateCheck(
                key="production_import_scan_clean",
                label="Production paths avoid runtime model dependencies",
                passed=not import_violations,
                detail="clean" if not import_violations else "; ".join(import_violations[:5]),
            ),
            EngineeringGateCheck(
                key="backend_tests_green",
                label="Backend pytest suite passes",
                passed=backend_passed,
                detail=backend_detail,
            ),
            EngineeringGateCheck(
                key="frontend_build_green",
                label="SPA build passes",
                passed=frontend_passed,
                detail=frontend_detail,
            ),
            EngineeringGateCheck(
                key="runtime_narrative_clean",
                label="Runtime provider narrative is removed from product docs and UI",
                passed=not narrative_violations,
                detail="clean" if not narrative_violations else "; ".join(narrative_violations[:5]),
            ),
        ],
        checked_at=_utc_now_iso(),
        source="fresh",
    ).model_dump(mode="json")
    if settings is not None:
        _write_snapshot(settings, report)
    return report


def refresh_engineering_gate_report(settings: Any | None = None) -> dict[str, Any]:
    return load_engineering_gate_report(settings, refresh=True, auto_refresh_if_missing=True)


def _failed_engineering_reasons(engineering_gate: dict[str, Any] | None) -> list[str]:
    if not engineering_gate:
        return ["Engineering gate has not been reviewed yet."]
    checks = list(engineering_gate.get("checks") or [])
    failures = [
        f"{check.get('label')}: {check.get('detail') or 'failed'}"
        for check in checks
        if not bool(check.get("passed"))
    ]
    return failures or ["Engineering gate has not passed."]


def build_agent_run_delivery_review(
    run: AgentRun,
    *,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
) -> dict[str, Any]:
    normalized_gate = _normalize_engineering_gate(engineering_gate)
    review = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
    citation_coverage = _run_citation_coverage(run)
    unsupported_claim_rate = _run_unsupported_claim_rate(run)
    review_block_precision = _run_review_block_precision(run)
    checks = [
        ScoreCheck(
            key="status_saved",
            label="Run status is saved",
            passed=(run.status or "").strip().lower() == "saved",
            detail=str(run.status or ""),
        ),
        ScoreCheck(
            key="review_approved",
            label="Review status is approved",
            passed=str(review.get("status") or "").strip().lower() == "approved",
            detail=str(review.get("status") or ""),
        ),
        ScoreCheck(
            key="citation_coverage",
            label="Citation coverage equals 1.00",
            passed=citation_coverage == 1.0,
            detail=f"{citation_coverage:.2f}",
        ),
        ScoreCheck(
            key="unsupported_claim_rate",
            label="Unsupported claim rate equals 0.00",
            passed=unsupported_claim_rate == 0.0,
            detail=f"{unsupported_claim_rate:.2f}",
        ),
        ScoreCheck(
            key="review_block_precision",
            label="Review block precision equals 1.00",
            passed=review_block_precision == 1.0,
            detail=f"{review_block_precision:.2f}",
        ),
        ScoreCheck(
            key="artifact_present",
            label="Report artifact is present",
            passed=bool(str(run.report_path or "").strip()) or bool(str(run.final_text or "").strip()),
            detail="report_path/final_text",
        ),
    ]
    business_deliverable = all(check.passed for check in checks)
    engineering_gate_passed = bool(normalized_gate and normalized_gate.get("passed"))
    blocking_reasons = [
        f"{check.label}: {check.detail or 'failed'}"
        for check in checks
        if not check.passed
    ]
    if not engineering_gate_passed:
        blocking_reasons.extend(_failed_engineering_reasons(normalized_gate))
    deliverable = business_deliverable and engineering_gate_passed
    return DeliveryReviewReport(
        resource_type="agent_run",
        resource_id=run.id,
        business_score=100 if business_deliverable else 0,
        business_deliverable=business_deliverable,
        engineering_gate_passed=engineering_gate_passed,
        deliverable=deliverable,
        publish_allowed=deliverable,
        allowed_actions=["publish"] if deliverable else [],
        blocked_actions=[] if deliverable else ["publish"],
        blocking_reasons=blocking_reasons,
        checks=checks,
        checked_at=_utc_now_iso(),
    ).model_dump(mode="json")


def _manual_knowledge_source_present(metadata: dict[str, Any]) -> bool:
    for key in _MANUAL_SOURCE_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if str(value or "").strip():
            return True
    return False


def build_knowledge_record_delivery_review(
    db: Session,
    record: KnowledgeRecord,
    *,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
) -> dict[str, Any]:
    normalized_gate = _normalize_engineering_gate(engineering_gate)
    metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    archive_meta = metadata.get("archive", {}) if isinstance(metadata.get("archive"), dict) else {}
    is_archived = bool(metadata.get("is_archived") or archive_meta.get("is_archived") or metadata.get("archived_at"))

    linked_run_id = str(metadata.get("agent_run_id") or "").strip()
    if not linked_run_id and str(metadata.get("source_type") or "").strip() == "agent_report":
        linked_run_id = str(metadata.get("agent_run_id") or "").strip()

    linked_run_review: dict[str, Any] | None = None
    if linked_run_id:
        linked_run = db.get(AgentRun, linked_run_id)
        if linked_run is not None:
            linked_run_review = build_agent_run_delivery_review(linked_run, engineering_gate=normalized_gate)

    checks = [
        ScoreCheck(
            key="title_present",
            label="Title is present",
            passed=bool(str(record.title or "").strip()),
            detail=str(record.title or ""),
        ),
        ScoreCheck(
            key="content_present",
            label="Content is present",
            passed=bool(str(record.content or "").strip()),
            detail=f"{len(record.content or '')} chars",
        ),
        ScoreCheck(
            key="not_archived",
            label="Knowledge record is not archived",
            passed=not is_archived,
            detail="active" if not is_archived else "archived",
        ),
    ]
    if linked_run_id:
        checks.append(
            ScoreCheck(
                key="linked_agent_run_deliverable",
                label="Linked agent run passes delivery gate",
                passed=bool(linked_run_review and linked_run_review.get("publish_allowed")),
                detail=linked_run_id,
            )
        )
    else:
        checks.append(
            ScoreCheck(
                key="manual_source_metadata_present",
                label="Source metadata or provenance is present",
                passed=_manual_knowledge_source_present(metadata),
                detail="metadata provenance",
            )
        )

    business_deliverable = all(check.passed for check in checks)
    engineering_gate_passed = bool(normalized_gate and normalized_gate.get("passed"))
    blocking_reasons = [
        f"{check.label}: {check.detail or 'failed'}"
        for check in checks
        if not check.passed
    ]
    if linked_run_review and not linked_run_review.get("publish_allowed"):
        blocking_reasons.extend(
            f"Linked agent run: {reason}"
            for reason in list(linked_run_review.get("blocking_reasons") or [])
        )
    if not engineering_gate_passed:
        blocking_reasons.extend(_failed_engineering_reasons(normalized_gate))

    deliverable = business_deliverable and engineering_gate_passed
    return DeliveryReviewReport(
        resource_type="knowledge_record",
        resource_id=record.id,
        business_score=100 if business_deliverable else 0,
        business_deliverable=business_deliverable,
        engineering_gate_passed=engineering_gate_passed,
        deliverable=deliverable,
        publish_allowed=deliverable,
        allowed_actions=["publish"] if deliverable else [],
        blocked_actions=[] if deliverable else ["publish"],
        blocking_reasons=blocking_reasons,
        checks=checks,
        checked_at=_utc_now_iso(),
    ).model_dump(mode="json")


def persist_agent_run_delivery_review(
    run: AgentRun,
    delivery_review: dict[str, Any],
) -> dict[str, Any]:
    run.quality_json = delivery_review
    metrics_json = dict(run.metrics_json or {}) if isinstance(run.metrics_json, dict) else {}
    metrics_json["score_snapshot"] = {
        "business_score": delivery_review.get("business_score", 0),
        "business_deliverable": delivery_review.get("business_deliverable", False),
        "engineering_gate_passed": delivery_review.get("engineering_gate_passed", False),
        "deliverable": delivery_review.get("deliverable", False),
        "blocked_actions": list(delivery_review.get("blocked_actions") or []),
        "reviewed_at": delivery_review.get("checked_at", _utc_now_iso()),
    }
    run.metrics_json = metrics_json
    return delivery_review


def persist_knowledge_record_delivery_review(
    record: KnowledgeRecord,
    delivery_review: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(record.metadata_json or {}) if isinstance(record.metadata_json, dict) else {}
    metadata["delivery_review"] = delivery_review
    record.metadata_json = metadata
    return delivery_review


def review_agent_run_delivery(
    run: AgentRun,
    *,
    settings: Any | None = None,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_gate = _normalize_engineering_gate(engineering_gate) or load_engineering_gate_report(
        settings,
        refresh=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    delivery_review = build_agent_run_delivery_review(run, engineering_gate=normalized_gate)
    persist_agent_run_delivery_review(run, delivery_review)
    return delivery_review, normalized_gate


def review_knowledge_record_delivery(
    db: Session,
    record: KnowledgeRecord,
    *,
    settings: Any | None = None,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_gate = _normalize_engineering_gate(engineering_gate) or load_engineering_gate_report(
        settings,
        refresh=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    delivery_review = build_knowledge_record_delivery_review(db, record, engineering_gate=normalized_gate)
    persist_knowledge_record_delivery_review(record, delivery_review)
    return delivery_review, normalized_gate


def ensure_delivery_allowed(
    delivery_review: dict[str, Any],
    *,
    engineering_gate: dict[str, Any] | None = None,
    action: str = "publish",
) -> None:
    blocked_actions = set(delivery_review.get("blocked_actions") or [])
    if blocked_actions and action in blocked_actions:
        raise DeliveryGateError(
            message="Delivery gate blocked this action until review reaches 100%.",
            delivery_review=delivery_review,
            engineering_gate=engineering_gate,
        )


def build_run_quality_snapshot(
    run: AgentRun,
    *,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
) -> dict[str, Any]:
    citation_coverage = _run_citation_coverage(run)
    unsupported_claim_rate = _run_unsupported_claim_rate(run)
    review_block_precision = _run_review_block_precision(run)
    review = dict(run.review_json or {}) if isinstance(run.review_json, dict) else {}
    review_status = str(review.get("status") or "").strip().lower()
    delivery_review = build_agent_run_delivery_review(run, engineering_gate=engineering_gate)
    snapshot = RunQualitySnapshot(
        run_id=run.id,
        status=run.status,
        current_stage=run.current_stage,
        queue_status=run.queue_status,
        quality_score=int(delivery_review.get("business_score") or 0),
        business_deliverable=bool(delivery_review.get("business_deliverable")),
        citation_coverage=citation_coverage,
        unsupported_claim_rate=unsupported_claim_rate,
        review_block_precision=review_block_precision,
        provider_kinds=[],
        runtime_bundle_id="",
        runtime_bundle_version="",
        review_status=review_status,
        blocked_reason=str(review.get("summary") or "").strip(),
        deliverable=bool(delivery_review.get("deliverable")),
        publish_allowed=bool(delivery_review.get("publish_allowed")),
        blocking_reasons=list(delivery_review.get("blocking_reasons") or []),
        delivery_review=DeliveryReviewReport.model_validate(delivery_review),
    )
    return snapshot.model_dump(mode="json")


def list_run_quality_snapshots(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    limit: int = 20,
    settings: Any | None = None,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
    auto_refresh_if_missing: bool = False,
) -> list[dict[str, Any]]:
    runs = _load_agent_runs(db, user=user, workspace=workspace, limit=limit)
    normalized_gate = _normalize_engineering_gate(engineering_gate) or load_engineering_gate_report(
        settings,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    return [build_run_quality_snapshot(run, engineering_gate=normalized_gate) for run in runs]


def build_delivery_scorecard(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    settings: Any | None = None,
    bundle: Any | None = None,
    engineering_gate: dict[str, Any] | EngineeringGateReport | None = None,
    refresh_engineering: bool = False,
    auto_refresh_if_missing: bool = False,
) -> dict[str, Any]:
    del bundle
    runs = _load_agent_runs(db, user=user, workspace=workspace, limit=20)
    normalized_gate = _normalize_engineering_gate(engineering_gate) or load_engineering_gate_report(
        settings,
        refresh=refresh_engineering,
        auto_refresh_if_missing=auto_refresh_if_missing,
    )
    run_snapshots = [build_run_quality_snapshot(run, engineering_gate=normalized_gate) for run in runs]

    workflow_integrity = _dimension(
        "workflow_integrity",
        "Workflow Integrity",
        _workflow_integrity_checks(run_snapshots),
    )
    research_checks, metrics = _research_quality_checks(run_snapshots)
    research_quality = _dimension("research_quality", "Research Quality", research_checks)
    artifact_integrity = _dimension("artifact_integrity", "Artifact Integrity", _artifact_checks(runs))
    publication_readiness = _dimension(
        "publication_readiness",
        "Publication Readiness",
        _publication_checks(runs),
    )
    product_surface = _dimension("product_surface", "Product Surface", _product_surface_checks())
    dimensions = [
        workflow_integrity,
        research_quality,
        artifact_integrity,
        publication_readiness,
        product_surface,
    ]
    total_score = sum(item.score for item in dimensions)
    business_deliverable = total_score == 500 and all(item.score == 100 for item in dimensions)
    engineering_passed = bool(normalized_gate.get("passed"))
    deliverable = business_deliverable and engineering_passed
    blocked_actions = [] if deliverable else ["publish_research_run", "publish_knowledge_record", "mark_deliverable"]
    blocking_reasons: list[str] = []
    if not business_deliverable:
        blocking_reasons.append("Business scorecard is not yet 500/500.")
    if not engineering_passed:
        blocking_reasons.extend(_failed_engineering_reasons(normalized_gate))
    scorecard = DeliveryScorecard(
        workspace_id=workspace.id,
        active_bundle_id="",
        active_bundle_version="",
        dimensions=dimensions,
        total_score=total_score,
        business_deliverable=business_deliverable,
        engineering_gate=EngineeringGateReport.model_validate(normalized_gate),
        allowed_actions=[] if not deliverable else ["publish_research_run", "publish_knowledge_record", "mark_deliverable"],
        blocked_actions=blocked_actions,
        blocking_reasons=blocking_reasons,
        deliverable=deliverable,
        generated_at=_utc_now_iso(),
    ).model_dump(mode="json")
    scorecard["active_bundle"] = None
    scorecard["recent_runs"] = run_snapshots
    scorecard["metrics"] = metrics
    return scorecard
