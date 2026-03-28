from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from markdown import markdown
from rich.console import Console

from .agent import AcademicResearchAgent
from .config import Settings
from .research_tools import ResearchSession
from .utils import slugify, utc_timestamp_slug, write_json


SESSION_METADATA_FILENAME = ".session.json"


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


def run_research(
    *,
    settings: Settings,
    topic: str,
    question: str | None = None,
    language: str = "Chinese",
    api_key: str | None = None,
    console: Console | None = None,
) -> ResearchRunPayload:
    runtime_settings = settings.with_api_key(api_key)
    session_dir = build_session_dir(settings.reports_dir, topic)
    access_token, created_at = create_session_access(session_dir=session_dir, topic=topic)
    session = ResearchSession(session_dir=session_dir)
    agent = AcademicResearchAgent(settings=runtime_settings, session=session, console=console)
    result = agent.run(
        topic=topic,
        research_question=question,
        preferred_language=language,
    )
    update_session_metadata(
        session_dir,
        question=question,
        language=language,
    )
    report_path = Path(result.report_path)
    bibtex_path = Path(result.bibtex_path)
    sources_path = Path(result.sources_path)
    final_text = report_path.read_text(encoding="utf-8")
    bibtex_content = bibtex_path.read_text(encoding="utf-8") if bibtex_path.exists() else ""
    sources_content = (
        json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    )
    return ResearchRunPayload(
        session_id=session_dir.name,
        session_dir=str(session_dir),
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
    )


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
