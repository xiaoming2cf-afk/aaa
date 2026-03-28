from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import EconomicBriefing, IntegrationCredential, JobRun, LiteratureEntry, ScheduleJob, User, Workspace
from .platform_core import create_knowledge_record
from .provider_gateway import ProviderGateway
from .research_tools import DEFAULT_HEADERS, OPENALEX_WORKS_API
from .security import decrypt_secret
from .utils import reconstruct_abstract, truncate_text


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
FRED_OBSERVATIONS_API = "https://api.stlouisfed.org/fred/series/observations"


def serialize_literature_entry(entry: LiteratureEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "openalex_id": entry.openalex_id,
        "title": entry.title,
        "authors": entry.authors_json,
        "abstract": entry.abstract,
        "publication_year": entry.publication_year,
        "doi": entry.doi,
        "cited_by_count": entry.cited_by_count,
        "venue": entry.venue,
        "landing_page_url": entry.landing_page_url,
        "pdf_url": entry.pdf_url,
        "keywords": entry.keywords_json,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def serialize_briefing(briefing: EconomicBriefing) -> dict[str, Any]:
    return {
        "id": briefing.id,
        "title": briefing.title,
        "summary_markdown": briefing.summary_markdown,
        "query_text": briefing.query_text,
        "headline_count": briefing.headline_count,
        "items": briefing.items_json,
        "created_at": briefing.created_at.isoformat(),
    }


def serialize_schedule(job: ScheduleJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "job_type": job.job_type,
        "timezone_name": job.timezone_name,
        "local_time": job.local_time,
        "enabled": job.enabled,
        "config": job.config_json,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "created_at": job.created_at.isoformat(),
    }


def normalize_openalex_work(raw_work: dict[str, Any]) -> dict[str, Any]:
    authors = [
        authorship.get("author", {}).get("display_name", "")
        for authorship in raw_work.get("authorships", [])
        if authorship.get("author", {}).get("display_name")
    ]
    keywords = [
        keyword.get("display_name", "")
        for keyword in raw_work.get("keywords", [])[:12]
        if keyword.get("display_name")
    ]
    best_oa_location = raw_work.get("best_oa_location") or {}
    primary_location = raw_work.get("primary_location") or {}
    return {
        "openalex_id": raw_work.get("id", ""),
        "title": raw_work.get("display_name", "Untitled"),
        "authors": authors,
        "abstract": reconstruct_abstract(raw_work.get("abstract_inverted_index")),
        "publication_year": raw_work.get("publication_year"),
        "doi": raw_work.get("doi") or "",
        "cited_by_count": raw_work.get("cited_by_count", 0),
        "venue": primary_location.get("source", {}).get("display_name")
        or best_oa_location.get("source", {}).get("display_name")
        or "",
        "landing_page_url": best_oa_location.get("landing_page_url")
        or primary_location.get("landing_page_url")
        or "",
        "pdf_url": best_oa_location.get("pdf_url")
        or primary_location.get("pdf_url")
        or raw_work.get("open_access", {}).get("oa_url")
        or "",
        "keywords": keywords,
        "raw": raw_work,
    }


def search_openalex(
    *,
    query: str,
    max_results: int = 10,
    open_access_only: bool = False,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[dict[str, Any]]:
    filters = ["has_abstract:true", "is_retracted:false"]
    if open_access_only:
        filters.append("open_access.is_oa:true")
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year:
        filters.append(f"to_publication_date:{to_year}-12-31")

    response = requests.get(
        OPENALEX_WORKS_API,
        headers=DEFAULT_HEADERS,
        params={
            "search": query,
            "filter": ",".join(filters),
            "per-page": max(1, min(max_results, 25)),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return [normalize_openalex_work(item) for item in payload.get("results", [])]


def import_openalex_works(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    works: list[dict[str, Any]],
) -> list[LiteratureEntry]:
    entries: list[LiteratureEntry] = []
    for work in works:
        openalex_id = work.get("openalex_id") or work.get("id")
        existing = db.scalar(
            select(LiteratureEntry).where(
                and_(
                    LiteratureEntry.workspace_id == workspace.id,
                    LiteratureEntry.openalex_id == openalex_id,
                )
            )
        )
        payload = normalize_openalex_work(work.get("raw", work))
        entry = existing or LiteratureEntry(
            workspace_id=workspace.id,
            owner_user_id=user.id,
            openalex_id=openalex_id,
        )
        entry.title = payload["title"]
        entry.authors_json = payload["authors"]
        entry.abstract = payload["abstract"]
        entry.publication_year = payload["publication_year"]
        entry.doi = payload["doi"]
        entry.cited_by_count = payload["cited_by_count"]
        entry.venue = payload["venue"]
        entry.landing_page_url = payload["landing_page_url"]
        entry.pdf_url = payload["pdf_url"]
        entry.keywords_json = payload["keywords"]
        entry.raw_json = payload["raw"]
        db.add(entry)
        entries.append(entry)
    db.flush()
    return entries


def list_literature_entries(db: Session, *, user: User, workspace: Workspace) -> list[LiteratureEntry]:
    return list(
        db.scalars(
            select(LiteratureEntry)
            .where(
                and_(
                    LiteratureEntry.owner_user_id == user.id,
                    LiteratureEntry.workspace_id == workspace.id,
                )
            )
            .order_by(LiteratureEntry.updated_at.desc())
        )
    )


def fetch_gdelt_hotspots(
    settings: Settings,
    *,
    query_text: str = "",
    max_records: int | None = None,
) -> dict[str, Any]:
    query = query_text.strip() or settings.gdelt_query
    response = requests.get(
        GDELT_DOC_API,
        headers=DEFAULT_HEADERS,
        params={
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "sort": "DateDesc",
            "maxrecords": max_records or settings.gdelt_max_records,
        },
        timeout=30,
    )
    if response.status_code == 429:
        return {"status": "rate_limited", "query": query, "items": [], "message": response.text}
    response.raise_for_status()
    payload = response.json()
    items = []
    for article in payload.get("articles", [])[: max_records or settings.gdelt_max_records]:
        items.append(
            {
                "title": article.get("title", ""),
                "seendate": article.get("seendate", ""),
                "domain": article.get("domain", ""),
                "source_country": article.get("sourcecountry", ""),
                "language": article.get("language", ""),
                "url": article.get("url", ""),
                "excerpt": truncate_text(article.get("socialimage", "") or article.get("title", ""), 160),
            }
        )
    return {"status": "ok", "query": query, "items": items}


def fetch_fred_snapshots(fred_api_key: str, *, series_ids: list[str]) -> list[dict[str, Any]]:
    if not fred_api_key.strip():
        return []
    snapshots: list[dict[str, Any]] = []
    for series_id in series_ids:
        response = requests.get(
            FRED_OBSERVATIONS_API,
            params={
                "series_id": series_id,
                "api_key": fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 3,
            },
            timeout=20,
        )
        if response.status_code != 200:
            continue
        observations = response.json().get("observations", [])
        latest = next((item for item in observations if item.get("value") not in {".", None, ""}), None)
        if not latest:
            continue
        snapshots.append(
            {
                "series_id": series_id,
                "date": latest.get("date"),
                "value": latest.get("value"),
            }
        )
    return snapshots


def build_economic_briefing_fallback(
    *,
    headlines: list[dict[str, Any]],
    fred_snapshots: list[dict[str, Any]],
    query_text: str,
) -> str:
    lines = ["# Daily Economic Briefing", "", f"Topic focus: {query_text or 'Global macro and financial developments'}", ""]
    if headlines:
        lines.extend(["## Headline Scan", ""])
        for item in headlines[:10]:
            lines.append(f"- {item['title']} ({item['domain'] or 'unknown source'})")
            if item.get("url"):
                lines.append(f"  Source: {item['url']}")
    else:
        lines.extend(["## Headline Scan", "", "- External headline feed did not return usable items in this run."])
    lines.extend(["", "## FRED Snapshot", ""])
    if fred_snapshots:
        for item in fred_snapshots:
            lines.append(f"- {item['series_id']}: {item['value']} ({item['date']})")
    else:
        lines.append("- No FRED series snapshot was available.")
    lines.extend(["", "## Analyst Note", "", "- Review central bank, inflation, labor, and bond-yield signals against the headline set before making portfolio or macro interpretations."])
    return "\n".join(lines)


def generate_economic_briefing(
    db: Session,
    settings: Settings,
    *,
    user: User,
    workspace: Workspace,
    integration_id: str | None = None,
    query_text: str = "",
    title: str = "",
) -> EconomicBriefing:
    llm_integration: IntegrationCredential | None = None
    if integration_id:
        llm_integration = db.get(IntegrationCredential, integration_id)
    elif user:
        llm_integration = db.scalar(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == "llm",
                    IntegrationCredential.is_default.is_(True),
                )
            )
        )

    fred_integration = db.scalar(
        select(IntegrationCredential).where(
            and_(
                IntegrationCredential.owner_user_id == user.id,
                IntegrationCredential.kind == "fred",
                IntegrationCredential.is_default.is_(True),
            )
        )
    )
    headlines_payload = fetch_gdelt_hotspots(settings, query_text=query_text)
    fred_snapshots = fetch_fred_snapshots(
        decrypt_secret(settings, fred_integration.api_key_encrypted) if fred_integration else "",
        series_ids=[item.strip() for item in settings.default_fred_series.split(",") if item.strip()],
    )
    fallback_markdown = build_economic_briefing_fallback(
        headlines=headlines_payload.get("items", []),
        fred_snapshots=fred_snapshots,
        query_text=query_text,
    )
    summary_markdown = fallback_markdown
    if llm_integration:
        try:
            summary_markdown = ProviderGateway(settings).generate_markdown(
                integration=llm_integration,
                system_prompt=(
                    "You are a senior economics research analyst. Produce a concise daily macro and financial briefing "
                    "with sections for headline summary, market implications, and follow-up research agenda."
                ),
                user_prompt=truncate_text(
                    json.dumps(
                        {
                            "query_text": query_text or settings.gdelt_query,
                            "headlines": headlines_payload.get("items", []),
                            "fred_snapshots": fred_snapshots,
                        },
                        ensure_ascii=False,
                    ),
                    14000,
                ),
                max_output_tokens=1400,
            )
        except Exception:
            summary_markdown = fallback_markdown

    briefing = EconomicBriefing(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        integration_id=llm_integration.id if llm_integration else None,
        title=title.strip() or "Daily Economic Briefing",
        summary_markdown=summary_markdown,
        query_text=query_text.strip() or settings.gdelt_query,
        headline_count=len(headlines_payload.get("items", [])),
        items_json=headlines_payload.get("items", []),
        raw_json={"gdelt": headlines_payload, "fred": fred_snapshots},
    )
    db.add(briefing)
    db.flush()
    create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=briefing.title,
        content=briefing.summary_markdown,
        tags=["economic-briefing", "macro", "daily"],
        metadata={"briefing_id": briefing.id, "headline_count": briefing.headline_count},
    )
    return briefing


def list_briefings(db: Session, *, user: User, workspace: Workspace) -> list[EconomicBriefing]:
    return list(
        db.scalars(
            select(EconomicBriefing)
            .where(
                and_(
                    EconomicBriefing.owner_user_id == user.id,
                    EconomicBriefing.workspace_id == workspace.id,
                )
            )
            .order_by(EconomicBriefing.created_at.desc())
        )
    )


def compute_next_run(local_time_value: str, timezone_name: str, *, now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    tzinfo = ZoneInfo(timezone_name)
    current_local = current.astimezone(tzinfo)
    hour, minute = [int(part) for part in local_time_value.split(":", 1)]
    candidate_local = datetime.combine(current_local.date(), time(hour=hour, minute=minute), tzinfo=tzinfo)
    if candidate_local <= current_local:
        candidate_local = candidate_local + timedelta(days=1)
    return candidate_local.astimezone(timezone.utc)


def create_schedule_job(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    name: str,
    job_type: str,
    timezone_name: str,
    local_time_value: str,
    integration_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> ScheduleJob:
    job = ScheduleJob(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        integration_id=integration_id,
        name=name.strip(),
        job_type=job_type.strip(),
        timezone_name=timezone_name.strip(),
        local_time=local_time_value.strip(),
        config_json=config or {},
        next_run_at=compute_next_run(local_time_value.strip(), timezone_name.strip()),
    )
    db.add(job)
    db.flush()
    return job


def list_schedule_jobs(db: Session, *, user: User, workspace: Workspace) -> list[ScheduleJob]:
    return list(
        db.scalars(
            select(ScheduleJob)
            .where(and_(ScheduleJob.owner_user_id == user.id, ScheduleJob.workspace_id == workspace.id))
            .order_by(ScheduleJob.created_at.desc())
        )
    )


def run_due_schedule_jobs(db: Session, settings: Settings, *, limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    jobs = list(
        db.scalars(
            select(ScheduleJob)
            .where(
                and_(
                    ScheduleJob.enabled.is_(True),
                    ScheduleJob.next_run_at.is_not(None),
                    ScheduleJob.next_run_at <= now,
                )
            )
            .order_by(ScheduleJob.next_run_at.asc())
            .limit(limit)
        )
    )
    results: list[dict[str, Any]] = []
    for job in jobs:
        run = JobRun(job_id=job.id, status="running")
        db.add(run)
        db.flush()
        try:
            user = db.get(User, job.owner_user_id)
            workspace = db.get(Workspace, job.workspace_id)
            if not user or not workspace:
                raise RuntimeError("Job owner or workspace is missing.")
            if job.job_type != "economic_briefing":
                raise ValueError(f"Unsupported job type: {job.job_type}")
            briefing = generate_economic_briefing(
                db,
                settings,
                user=user,
                workspace=workspace,
                integration_id=job.integration_id,
                query_text=job.config_json.get("query_text", ""),
                title=job.config_json.get("title", job.name),
            )
            run.status = "completed"
            run.summary = briefing.title
            run.output_json = {"briefing_id": briefing.id}
            job.last_run_at = now
            job.next_run_at = compute_next_run(job.local_time, job.timezone_name, now=now + timedelta(seconds=1))
            results.append({"job_id": job.id, "status": "completed", "briefing_id": briefing.id})
        except Exception as exc:
            run.status = "failed"
            run.summary = str(exc)
            run.output_json = {"error": str(exc)}
            job.last_run_at = now
            job.next_run_at = compute_next_run(job.local_time, job.timezone_name, now=now + timedelta(seconds=1))
            results.append({"job_id": job.id, "status": "failed", "error": str(exc)})
        finally:
            run.finished_at = datetime.now(timezone.utc)
            db.flush()
    return results
