from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import (
    EconomicBriefing,
    IntegrationCredential,
    JobRun,
    LiteratureEntry,
    PublicEconomicBriefing,
    ScheduleJob,
    User,
    Workspace,
)
from .platform_core import create_knowledge_record
from .provider_gateway import ProviderGateway
from .research_tools import DEFAULT_HEADERS, OPENALEX_WORKS_API
from .security import decrypt_secret
from .utils import reconstruct_abstract, slugify, truncate_text


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
FRED_OBSERVATIONS_API = "https://api.stlouisfed.org/fred/series/observations"
PUBLIC_TEMPLATE_VERSION = "daily-macro-v1"
FRED_SERIES_LABELS = {
    "FEDFUNDS": "Fed policy rate",
    "CPIAUCSL": "US CPI index",
    "UNRATE": "US unemployment rate",
    "DGS10": "US 10Y Treasury yield",
}
MACRO_THEME_KEYWORDS = {
    "inflation": ["inflation", "cpi", "price", "disinflation", "deflation"],
    "monetary policy": ["central bank", "fed", "ecb", "boj", "boe", "rate hike", "rate cut", "interest rate"],
    "growth": ["gdp", "growth", "recession", "activity", "manufacturing", "demand"],
    "labor": ["jobs", "labor", "labour", "unemployment", "wages", "payroll"],
    "trade": ["trade", "tariff", "export", "import", "supply chain"],
    "energy": ["oil", "gas", "energy", "crude", "opec"],
    "markets": ["yield", "bond", "stocks", "equity", "currency", "dollar", "fx"],
}


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


def _extract_markdown_excerpt(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#") and not candidate.startswith("- "):
            return truncate_text(candidate, 220)
    return truncate_text(markdown_text, 220)


def _headline_theme_labels(item: dict[str, Any]) -> list[str]:
    existing = [str(theme).strip() for theme in item.get("themes", []) if str(theme).strip()]
    if existing:
        return existing
    title = str(item.get("title", "")).strip().lower()
    labels: list[str] = []
    for theme_name, keywords in MACRO_THEME_KEYWORDS.items():
        if any(keyword in title for keyword in keywords):
            labels.append(theme_name)
    return labels


def _annotate_headlines_with_themes(headlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for item in headlines:
        themes = _headline_theme_labels(item)
        annotated.append(
            {
                **item,
                "themes": themes,
                "primary_theme": themes[0] if themes else "",
            }
        )
    return annotated


def _build_public_briefing_url(slug: str, public_base_url: str = "") -> str:
    clean_base = public_base_url.strip().rstrip("/")
    if clean_base:
        return f"{clean_base}/briefings/{slug}"
    return f"/briefings/{slug}"


def serialize_public_briefing(
    briefing: PublicEconomicBriefing,
    *,
    public_base_url: str = "",
) -> dict[str, Any]:
    theme_counts = _theme_counts(briefing.items_json)
    return {
        "id": briefing.id,
        "slug": briefing.slug,
        "title": briefing.title,
        "briefing_date": briefing.briefing_date,
        "timezone_name": briefing.timezone_name,
        "summary_markdown": briefing.summary_markdown,
        "summary_excerpt": _extract_markdown_excerpt(briefing.summary_markdown),
        "query_text": briefing.query_text,
        "template_version": briefing.template_version,
        "headline_count": briefing.headline_count,
        "items": briefing.items_json,
        "top_themes": [{"theme": theme, "count": count} for theme, count in theme_counts.most_common(5)],
        "share_url": _build_public_briefing_url(briefing.slug, public_base_url),
        "detail_path": f"/briefings/{briefing.slug}",
        "created_at": briefing.created_at.isoformat(),
        "updated_at": briefing.updated_at.isoformat(),
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


def _current_local_time(timezone_name: str, *, now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(timezone_name))


def _title_texts(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("title", "")).strip() for item in items if str(item.get("title", "")).strip()]


def _theme_counts(headlines: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in headlines:
        labels = _headline_theme_labels(item)
        counts.update(labels)
    return counts


def _theme_examples(headlines: list[dict[str, Any]], theme_name: str, *, limit: int = 2) -> list[str]:
    examples: list[str] = []
    for item in headlines:
        title = str(item.get("title", "")).strip()
        labels = _headline_theme_labels(item)
        if title and theme_name in labels:
            examples.append(title)
        if len(examples) >= limit:
            break
    return examples


def _top_domains(headlines: list[dict[str, Any]], *, limit: int = 5) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for item in headlines:
        domain = str(item.get("domain", "")).strip().lower()
        if domain:
            counts[domain] += 1
    return counts.most_common(limit)


def _top_source_countries(headlines: list[dict[str, Any]], *, limit: int = 4) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for item in headlines:
        country = str(item.get("source_country", "")).strip().upper()
        if country:
            counts[country] += 1
    return counts.most_common(limit)


def _parse_numeric_value(raw_value: str | int | float | None) -> float | None:
    if raw_value in {None, "", "."}:
        return None
    try:
        return float(str(raw_value).replace(",", ""))
    except ValueError:
        return None


def _build_fred_lines(fred_snapshots: list[dict[str, Any]]) -> list[str]:
    if not fred_snapshots:
        return ["- No public FRED snapshot was available for this run."]
    lines: list[str] = []
    for item in fred_snapshots:
        series_id = str(item.get("series_id", "")).strip()
        label = FRED_SERIES_LABELS.get(series_id, series_id or "Unknown series")
        value = item.get("value") or "n/a"
        date_value = item.get("date") or "n/a"
        lines.append(f"- {label} ({series_id}): {value} on {date_value}")
    return lines


def _build_watchlist(theme_counts: Counter[str], fred_snapshots: list[dict[str, Any]]) -> list[str]:
    watchlist: list[str] = []
    if theme_counts.get("monetary policy"):
        watchlist.append("Track how central-bank guidance is shifting rate-cut or rate-hike expectations.")
    if theme_counts.get("inflation"):
        watchlist.append("Check whether inflation headlines are broadening from goods into services and wages.")
    if theme_counts.get("growth"):
        watchlist.append("Compare growth headlines with incoming activity data to separate slowdown risk from noise.")
    if theme_counts.get("trade") or theme_counts.get("energy"):
        watchlist.append("Review cross-border trade and energy shocks for second-round inflation effects.")
    for item in fred_snapshots:
        if item.get("series_id") == "DGS10":
            value = _parse_numeric_value(item.get("value"))
            if value is not None and value >= 4.0:
                watchlist.append("Long-end yields remain elevated; watch duration-sensitive sectors and financing conditions.")
                break
    return watchlist[:4] or ["Monitor whether today's headlines are confirmed by market pricing and official data releases."]


def _build_research_agenda(theme_counts: Counter[str]) -> list[str]:
    agenda: list[str] = []
    top_themes = [theme for theme, _ in theme_counts.most_common(3)]
    if not top_themes:
        return [
            "Check whether the headline set is broad enough to support a macro conclusion.",
            "Refresh the default indicator panel before drawing directional views.",
        ]
    for theme in top_themes:
        if theme == "monetary policy":
            agenda.append("Map the latest policy headlines against expected rate paths and front-end yield moves.")
        elif theme == "inflation":
            agenda.append("Separate one-off price shocks from broader inflation persistence signals.")
        elif theme == "growth":
            agenda.append("Cross-check growth headlines with PMIs, GDP trackers, and credit conditions.")
        elif theme == "labor":
            agenda.append("Compare labor-market headlines with unemployment, payroll, and wage trend releases.")
        elif theme == "trade":
            agenda.append("Assess whether trade-policy changes materially affect supply chains or export demand.")
        elif theme == "energy":
            agenda.append("Estimate pass-through from energy headlines into inflation and industrial margins.")
        elif theme == "markets":
            agenda.append("Link market headlines to rate, credit, and currency transmission channels.")
    return agenda[:4]


def build_structured_economic_briefing(
    *,
    title: str,
    report_date: str,
    timezone_name: str,
    headlines: list[dict[str, Any]],
    fred_snapshots: list[dict[str, Any]],
    query_text: str,
    template_version: str = PUBLIC_TEMPLATE_VERSION,
) -> str:
    theme_counts = _theme_counts(headlines)
    theme_lines: list[str] = []
    for theme_name, count in theme_counts.most_common(4):
        examples = _theme_examples(headlines, theme_name)
        example_suffix = f" Representative headlines: {'; '.join(examples)}." if examples else ""
        theme_lines.append(f"- {theme_name.title()}: {count} headline(s).{example_suffix}")
    if not theme_lines:
        theme_lines = ["- The feed was relatively thin, so today's report should be treated as a low-conviction signal scan."]

    domain_lines = [f"- {domain}: {count} item(s)" for domain, count in _top_domains(headlines)]
    if not domain_lines:
        domain_lines = ["- No stable source-domain pattern was available in this run."]

    source_country_lines = [f"- {country}: {count} item(s)" for country, count in _top_source_countries(headlines)]
    if not source_country_lines:
        source_country_lines = ["- Source-country information was sparse in this run."]

    watchlist = _build_watchlist(theme_counts, fred_snapshots)
    research_agenda = _build_research_agenda(theme_counts)

    if theme_counts:
        top_theme_names = ", ".join(theme for theme, _ in theme_counts.most_common(3))
        executive_line = (
            f"Today's macro scan collected {len(headlines)} headline(s) and points mainly toward {top_theme_names}."
        )
    else:
        executive_line = (
            f"Today's macro scan collected {len(headlines)} headline(s); the signal set is limited, so treat it as a monitoring pass."
        )

    lines = [
        f"# {title}",
        "",
        f"- Report date: {report_date} ({timezone_name})",
        f"- Topic scope: {query_text or 'Global macro and financial developments'}",
        f"- Template version: {template_version}",
        "",
        "## Executive Summary",
        "",
        executive_line,
        "",
        "## Macro Theme Map",
        "",
        *theme_lines,
        "",
        "## Market And Data Snapshot",
        "",
        *_build_fred_lines(fred_snapshots),
        "",
        "## Watchlist",
        "",
        *[f"- {line}" for line in watchlist],
        "",
        "## Source Map",
        "",
        *domain_lines,
        "",
        "## Source Countries",
        "",
        *source_country_lines,
        "",
        "## Research Agenda",
        "",
        *[f"- {line}" for line in research_agenda],
        "",
        "## Headline Register",
        "",
    ]
    if headlines:
        for item in headlines[:8]:
            title_text = item.get("title", "Untitled headline")
            source_name = item.get("domain") or "unknown source"
            lines.append(f"- {title_text} ({source_name})")
            if item.get("url"):
                lines.append(f"  Source: {item['url']}")
    else:
        lines.append("- No usable headlines were available from the external feed.")
    return "\n".join(lines)


def build_economic_briefing_fallback(
    *,
    headlines: list[dict[str, Any]],
    fred_snapshots: list[dict[str, Any]],
    query_text: str,
) -> str:
    return build_structured_economic_briefing(
        title="Daily Economic Briefing",
        report_date=datetime.now(timezone.utc).date().isoformat(),
        timezone_name="UTC",
        headlines=headlines,
        fred_snapshots=fred_snapshots,
        query_text=query_text,
    )


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
    resolved_title = title.strip() or "Daily Economic Briefing"
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
                    "You are a senior economics research analyst. Produce concise markdown using exactly these sections: "
                    "Executive Summary, Macro Theme Map, Market And Data Snapshot, Watchlist, Source Map, "
                    "Source Countries, Research Agenda, Headline Register. Be specific, cautious, and research-oriented."
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
        title=resolved_title,
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


def list_public_briefings(db: Session, *, limit: int = 14) -> list[PublicEconomicBriefing]:
    return list(
        db.scalars(
            select(PublicEconomicBriefing)
            .order_by(PublicEconomicBriefing.briefing_date.desc(), PublicEconomicBriefing.created_at.desc())
            .limit(max(1, min(limit, 60)))
        )
    )


def get_public_briefing_by_slug(db: Session, *, slug: str) -> PublicEconomicBriefing | None:
    return db.scalar(select(PublicEconomicBriefing).where(PublicEconomicBriefing.slug == slug.strip()))


def get_latest_public_briefing(db: Session) -> PublicEconomicBriefing | None:
    return db.scalar(
        select(PublicEconomicBriefing).order_by(
            PublicEconomicBriefing.briefing_date.desc(), PublicEconomicBriefing.created_at.desc()
        )
    )


def _public_digest_is_due(settings: Settings, *, now: datetime | None = None) -> bool:
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    hour, minute = [int(part) for part in settings.public_digest_local_time.split(":", 1)]
    due_at = datetime.combine(local_now.date(), time(hour=hour, minute=minute), tzinfo=local_now.tzinfo)
    return local_now >= due_at


def generate_public_daily_briefing(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> PublicEconomicBriefing:
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    briefing_date = local_now.date().isoformat()
    existing = db.scalar(
        select(PublicEconomicBriefing).where(PublicEconomicBriefing.briefing_date == briefing_date)
    )
    if existing and not force:
        return existing

    query_text = settings.public_digest_query or settings.gdelt_query
    headlines_payload = fetch_gdelt_hotspots(settings, query_text=query_text)
    annotated_items = _annotate_headlines_with_themes(headlines_payload.get("items", []))
    fred_snapshots = fetch_fred_snapshots(
        settings.fred_api_key,
        series_ids=[item.strip() for item in settings.default_fred_series.split(",") if item.strip()],
    )
    title = f"{settings.public_digest_title} | {briefing_date}"
    summary_markdown = build_structured_economic_briefing(
        title=title,
        report_date=briefing_date,
        timezone_name=settings.public_digest_timezone,
        headlines=annotated_items,
        fred_snapshots=fred_snapshots,
        query_text=query_text,
        template_version=PUBLIC_TEMPLATE_VERSION,
    )

    briefing = existing or PublicEconomicBriefing(
        slug=slugify(f"{settings.public_digest_title}-{briefing_date}", max_length=220),
        briefing_date=briefing_date,
    )
    briefing.title = title
    briefing.timezone_name = settings.public_digest_timezone
    briefing.summary_markdown = summary_markdown
    briefing.query_text = query_text
    briefing.template_version = PUBLIC_TEMPLATE_VERSION
    briefing.headline_count = len(annotated_items)
    briefing.items_json = annotated_items
    briefing.raw_json = {
        "gdelt": {**headlines_payload, "items": annotated_items},
        "fred": fred_snapshots,
    }
    db.add(briefing)
    db.flush()
    return briefing


def ensure_public_daily_briefing(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> PublicEconomicBriefing | None:
    if not settings.public_digest_enabled:
        return None
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    briefing_date = local_now.date().isoformat()
    existing = db.scalar(
        select(PublicEconomicBriefing).where(PublicEconomicBriefing.briefing_date == briefing_date)
    )
    if existing and not force:
        return existing
    if not force and not _public_digest_is_due(settings, now=now):
        return existing
    return generate_public_daily_briefing(db, settings, now=now, force=force)


def build_public_briefing_summary(
    db: Session,
    *,
    days: int = 7,
    now: datetime | None = None,
    public_base_url: str = "",
) -> dict[str, Any]:
    window_days = max(2, min(days, 30))
    local_now = _current_local_time("UTC", now=now)
    window_start = (local_now.date() - timedelta(days=window_days - 1)).isoformat()
    briefings = list(
        db.scalars(
            select(PublicEconomicBriefing)
            .where(PublicEconomicBriefing.briefing_date >= window_start)
            .order_by(PublicEconomicBriefing.briefing_date.desc(), PublicEconomicBriefing.created_at.desc())
        )
    )

    theme_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    total_headlines = 0
    fred_window: dict[str, list[dict[str, Any]]] = {}
    for briefing in reversed(briefings):
        theme_counts.update(_theme_counts(briefing.items_json))
        domain_counts.update(dict(_top_domains(briefing.items_json, limit=20)))
        total_headlines += briefing.headline_count
        for snapshot in briefing.raw_json.get("fred", []):
            series_id = str(snapshot.get("series_id", "")).strip()
            if series_id:
                fred_window.setdefault(series_id, []).append(snapshot)

    top_themes = [
        {"theme": theme_name, "count": count}
        for theme_name, count in theme_counts.most_common(5)
    ]
    top_domains = [
        {"domain": domain, "count": count}
        for domain, count in domain_counts.most_common(5)
    ]

    fred_lines: list[str] = []
    latest_fred: list[dict[str, Any]] = []
    for series_id, observations in fred_window.items():
        latest = observations[-1]
        latest_value = _parse_numeric_value(latest.get("value"))
        earliest_value = _parse_numeric_value(observations[0].get("value"))
        delta_text = ""
        if latest_value is not None and earliest_value is not None:
            delta = latest_value - earliest_value
            delta_text = f", change over window {delta:+.2f}"
        latest_fred.append(
            {
                "series_id": series_id,
                "label": FRED_SERIES_LABELS.get(series_id, series_id),
                "date": latest.get("date"),
                "value": latest.get("value"),
            }
        )
        fred_lines.append(
            f"- {FRED_SERIES_LABELS.get(series_id, series_id)} ({series_id}): "
            f"{latest.get('value', 'n/a')} on {latest.get('date', 'n/a')}{delta_text}"
        )
    if not fred_lines:
        fred_lines = ["- No FRED window summary was available."]

    if briefings:
        date_range = f"{briefings[-1].briefing_date} to {briefings[0].briefing_date}"
    else:
        date_range = "No published public briefings yet"
    takeaway_lines = _build_research_agenda(theme_counts)
    markdown_lines = [
        f"# Public Economic Summary ({window_days}-day window)",
        "",
        "## Coverage",
        "",
        f"- Date range: {date_range}",
        f"- Public briefing count: {len(briefings)}",
        f"- Total headlines scanned: {total_headlines}",
        "",
        "## Recurrent Themes",
        "",
    ]
    if top_themes:
        markdown_lines.extend([f"- {item['theme'].title()}: {item['count']} headline matches" for item in top_themes])
    else:
        markdown_lines.append("- No stable theme pattern is available yet.")
    markdown_lines.extend(["", "## Data Direction", "", *fred_lines, "", "## Source Concentration", ""])
    if top_domains:
        markdown_lines.extend([f"- {item['domain']}: {item['count']} items" for item in top_domains])
    else:
        markdown_lines.append("- No stable source-domain pattern is available yet.")
    markdown_lines.extend(["", "## Follow-up Takeaways", ""])
    markdown_lines.extend([f"- {line}" for line in takeaway_lines or ["Wait for more public daily reports to accumulate before drawing a trend view."]])

    return {
        "available_windows": [7, 14, 30],
        "selected_days": window_days,
        "days": window_days,
        "report_count": len(briefings),
        "total_headlines": total_headlines,
        "top_themes": top_themes,
        "top_domains": top_domains,
        "latest_fred": latest_fred,
        "markdown": "\n".join(markdown_lines),
        "latest_briefing": serialize_public_briefing(briefings[0], public_base_url=public_base_url)
        if briefings
        else None,
    }


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
