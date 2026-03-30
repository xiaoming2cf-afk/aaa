from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import (
    DataAsset,
    EconomicBriefing,
    IntegrationCredential,
    JobRun,
    LiteratureEntry,
    PublicEconomicBriefing,
    ScheduleJob,
    User,
    Workspace,
)
from .platform_core import create_knowledge_record, save_upload_asset, serialize_asset
from .provider_gateway import ProviderGateway
from .research_tools import DEFAULT_HEADERS, OPENALEX_WORKS_API
from .security import decrypt_secret
from .utils import reconstruct_abstract, slugify, truncate_text


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
FRED_OBSERVATIONS_API = "https://api.stlouisfed.org/fred/series/observations"
PUBLIC_TEMPLATE_VERSION = "daily-macro-v2"
PUBLIC_OFFICIAL_LOOKBACK_DAYS = 5
PUBLIC_MEDIA_RSS_FEEDS = [
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "domain": "bbc.com",
        "source_country": "GB",
        "language": "English",
        "source_type": "media",
        "region_focus": "United Kingdom",
        "credibility": "major public-service media",
        "note": "BBC business feed",
    },
    {
        "name": "NYT Business",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "domain": "nytimes.com",
        "source_country": "US",
        "language": "English",
        "source_type": "media",
        "region_focus": "United States",
        "credibility": "major national newspaper",
        "note": "New York Times business feed",
    },
    {
        "name": "CNBC Top News",
        "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "domain": "cnbc.com",
        "source_country": "US",
        "language": "English",
        "source_type": "media",
        "region_focus": "United States",
        "credibility": "major financial media outlet",
        "note": "CNBC top news feed",
    },
    {
        "name": "MarketWatch Top Stories",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "domain": "marketwatch.com",
        "source_country": "US",
        "language": "English",
        "source_type": "media",
        "region_focus": "United States",
        "credibility": "major financial media outlet",
        "note": "MarketWatch top-stories feed",
    },
    {
        "name": "Investing.com News",
        "url": "https://www.investing.com/rss/news_25.rss",
        "domain": "investing.com",
        "source_country": "US",
        "language": "English",
        "source_type": "media",
        "region_focus": "Global",
        "credibility": "market-data media feed",
        "note": "Investing.com market news feed",
    },
    {
        "name": "SCMP China",
        "url": "https://www.scmp.com/rss/4/feed",
        "domain": "scmp.com",
        "source_country": "CN",
        "language": "English",
        "source_type": "media",
        "region_focus": "China",
        "credibility": "major China-focused newspaper",
        "note": "South China Morning Post China feed",
    },
    {
        "name": "Nikkei Asia",
        "url": "https://asia.nikkei.com/rss/feed/nar",
        "domain": "asia.nikkei.com",
        "source_country": "JP",
        "language": "English",
        "source_type": "media",
        "region_focus": "Asia",
        "credibility": "major Asia business newspaper",
        "note": "Nikkei Asia feed",
    },
]
PUBLIC_OFFICIAL_RSS_FEEDS = [
    {
        "name": "Federal Reserve Press Releases",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "domain": "federalreserve.gov",
        "source_country": "US",
        "language": "English",
        "source_type": "official",
        "region_focus": "United States",
        "credibility": "official central bank",
        "note": "Federal Reserve Board press release feed",
    },
    {
        "name": "European Central Bank Press",
        "url": "https://www.ecb.europa.eu/rss/press.xml",
        "domain": "ecb.europa.eu",
        "source_country": "EA",
        "language": "English",
        "source_type": "official",
        "region_focus": "Euro Area",
        "credibility": "official central bank",
        "note": "European Central Bank press feed",
    },
    {
        "name": "Bank of England News",
        "url": "https://www.bankofengland.co.uk/rss/news",
        "domain": "bankofengland.co.uk",
        "source_country": "GB",
        "language": "English",
        "source_type": "official",
        "region_focus": "United Kingdom",
        "credibility": "official central bank",
        "note": "Bank of England news feed",
    },
    {
        "name": "China NBS Latest Releases",
        "url": "https://www.stats.gov.cn/english/PressRelease/rss.xml",
        "domain": "stats.gov.cn",
        "source_country": "CN",
        "language": "English",
        "source_type": "official",
        "region_focus": "China",
        "credibility": "official statistics agency",
        "note": "National Bureau of Statistics of China release feed",
    },
]
PUBLIC_OFFICIAL_PAGE_SOURCES = [
    {
        "name": "U.S. Treasury Press Releases",
        "url": "https://home.treasury.gov/news/press-releases",
        "domain": "home.treasury.gov",
        "source_country": "US",
        "language": "English",
        "source_type": "official",
        "region_focus": "United States",
        "credibility": "official government",
        "note": "U.S. Treasury press-release page",
        "kind": "html",
        "parser": "treasury_press",
    },
    {
        "name": "U.S. BEA Current Releases",
        "url": "https://www.bea.gov/news/current-releases",
        "domain": "bea.gov",
        "source_country": "US",
        "language": "English",
        "source_type": "official",
        "region_focus": "United States",
        "credibility": "official statistics agency",
        "note": "Bureau of Economic Analysis current releases page",
        "kind": "html",
        "parser": "bea_current_releases",
    },
    {
        "name": "State Council China News",
        "url": "https://english.www.gov.cn/news/latestnews/index.htm",
        "domain": "english.www.gov.cn",
        "source_country": "CN",
        "language": "English",
        "source_type": "official",
        "region_focus": "China",
        "credibility": "official government",
        "note": "State Council of China English news page",
        "kind": "html",
        "parser": "state_council",
    },
    {
        "name": "SAFE China Updates",
        "url": "http://www.safe.gov.cn/en/",
        "domain": "safe.gov.cn",
        "source_country": "CN",
        "language": "English",
        "source_type": "official",
        "region_focus": "China",
        "credibility": "official regulator",
        "note": "State Administration of Foreign Exchange updates",
        "kind": "html",
        "parser": "safe_updates",
    },
    {
        "name": "Bank of Canada Press Releases",
        "url": "https://www.bankofcanada.ca/press/press-releases/",
        "domain": "bankofcanada.ca",
        "source_country": "CA",
        "language": "English",
        "source_type": "official",
        "region_focus": "Canada",
        "credibility": "official central bank",
        "note": "Bank of Canada press-release page",
        "kind": "html",
        "parser": "bank_of_canada",
    },
    {
        "name": "Japan Ministry of Finance Updates",
        "url": "https://www.mof.go.jp/english/public_relations/whats_new/202603.html",
        "domain": "mof.go.jp",
        "source_country": "JP",
        "language": "English",
        "source_type": "official",
        "region_focus": "Japan",
        "credibility": "official government",
        "note": "Japan Ministry of Finance monthly updates page",
        "kind": "html",
        "parser": "mof_japan",
    },
]
PUBLIC_RSS_FEEDS = [*PUBLIC_MEDIA_RSS_FEEDS, *PUBLIC_OFFICIAL_RSS_FEEDS]
PUBLIC_SOURCE_DIRECTORY = [*PUBLIC_MEDIA_RSS_FEEDS, *PUBLIC_OFFICIAL_RSS_FEEDS, *PUBLIC_OFFICIAL_PAGE_SOURCES]
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
PUBLIC_NEWS_KEYWORDS = sorted(
    {
        keyword.lower()
        for keywords in MACRO_THEME_KEYWORDS.values()
        for keyword in keywords
    }
    | {
        "economy",
        "economic",
        "bank",
        "treasury",
        "tariffs",
        "inflation report",
        "policy rate",
        "employment",
        "fiscal",
        "markets",
        "foreign exchange",
        "balance of payments",
        "external debt",
        "financial stability",
        "capital market",
        "credit",
        "liquidity",
        "market operations",
        "private sector",
        "renminbi",
        "yuan",
        "consumption",
        "trade in goods",
    }
)
PUBLIC_SUMMARY_WINDOWS = {
    "weekly": {
        "days": 7,
        "title": "Weekly Macro Roundup",
        "subtitle": "A standalone 7-day public page for the latest macro and market signal stack.",
    },
    "monthly": {
        "days": 30,
        "title": "Monthly Macro Review",
        "subtitle": "A standalone 30-day public page for broader economic and financial trend review.",
    },
}


def serialize_literature_entry(entry: LiteratureEntry) -> dict[str, Any]:
    workspace_pdf_asset_id = str((entry.raw_json or {}).get("_workspace_pdf_asset_id") or "").strip()
    workspace_pdf_asset_title = str((entry.raw_json or {}).get("_workspace_pdf_asset_title") or "").strip()
    workspace_knowledge_record_id = str((entry.raw_json or {}).get("_workspace_knowledge_record_id") or "").strip()
    workspace_knowledge_record_title = str((entry.raw_json or {}).get("_workspace_knowledge_record_title") or "").strip()
    can_import_pdf = bool(str(entry.pdf_url or "").strip() or str(entry.landing_page_url or "").strip())
    return {
        "id": entry.id,
        "openalex_id": entry.openalex_id,
        "title": entry.title,
        "authors": entry.authors_json,
        "abstract": entry.abstract,
        "abstract_excerpt": truncate_text(entry.abstract or "", 280),
        "publication_year": entry.publication_year,
        "doi": entry.doi,
        "cited_by_count": entry.cited_by_count,
        "venue": entry.venue,
        "landing_page_url": entry.landing_page_url,
        "pdf_url": entry.pdf_url,
        "has_open_access_pdf": can_import_pdf,
        "can_import_pdf": can_import_pdf,
        "workspace_pdf_asset_id": workspace_pdf_asset_id,
        "workspace_pdf_asset_title": workspace_pdf_asset_title,
        "workspace_pdf_download_url": f"/api/assets/{workspace_pdf_asset_id}/download" if workspace_pdf_asset_id else "",
        "workspace_knowledge_record_id": workspace_knowledge_record_id,
        "workspace_knowledge_record_title": workspace_knowledge_record_title,
        "citation_text": build_literature_citation(entry),
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


def _build_public_summary_url(window: str, public_base_url: str = "") -> str:
    clean_base = public_base_url.strip().rstrip("/")
    if clean_base:
        return f"{clean_base}/summaries/{window}"
    return f"/summaries/{window}"


def _public_summary_pages(public_base_url: str = "") -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for window_name, config in PUBLIC_SUMMARY_WINDOWS.items():
        pages.append(
            {
                "window": window_name,
                "days": config["days"],
                "title": config["title"],
                "subtitle": config["subtitle"],
                "detail_path": f"/summaries/{window_name}",
                "share_url": _build_public_summary_url(window_name, public_base_url),
            }
        )
    return pages


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


def _cluster_headline_bucket(item: dict[str, Any]) -> str:
    primary_theme = str(item.get("primary_theme", "")).strip()
    if primary_theme:
        return primary_theme
    themes = _headline_theme_labels(item)
    if themes:
        return themes[0]
    domain = str(item.get("domain", "")).strip().lower()
    return domain or "cross-market"


def _cluster_display_label(bucket_name: str) -> str:
    if bucket_name == "cross-market":
        return "Cross-Market"
    return bucket_name.replace("-", " ").title()


def _describe_news_cluster(
    bucket_name: str,
    items: list[dict[str, Any]],
    domains: list[tuple[str, int]],
    countries: list[tuple[str, int]],
) -> str:
    label = _cluster_display_label(bucket_name)
    domain_text = ", ".join(domain for domain, _ in domains[:2]) or "mixed sources"
    country_text = ", ".join(country for country, _ in countries[:2]) or "multiple geographies"
    lead_title = str(items[0].get("title", "")).strip() if items else ""
    if lead_title:
        return (
            f"{label} cluster with {len(items)} headline(s), led by '{lead_title}', "
            f"spanning {domain_text} and {country_text}."
        )
    return f"{label} cluster with {len(items)} headline(s) across {domain_text} and {country_text}."


def build_public_news_clusters(headlines: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in headlines:
        buckets.setdefault(_cluster_headline_bucket(item), []).append(item)

    ranked_buckets = sorted(
        buckets.items(),
        key=lambda entry: (len(entry[1]), _cluster_display_label(entry[0]).lower()),
        reverse=True,
    )
    clusters: list[dict[str, Any]] = []
    for bucket_name, items in ranked_buckets[:limit]:
        domains = _top_domains(items, limit=3)
        countries = _top_source_countries(items, limit=3)
        clusters.append(
            {
                "cluster_id": slugify(bucket_name or "cluster", max_length=80),
                "label": _cluster_display_label(bucket_name),
                "headline_count": len(items),
                "summary": _describe_news_cluster(bucket_name, items, domains, countries),
                "domains": [{"domain": domain, "count": count} for domain, count in domains],
                "source_countries": [{"country": country, "count": count} for country, count in countries],
                "items": [
                    {
                        "title": str(item.get("title", "")).strip(),
                        "url": str(item.get("url", "")).strip(),
                        "domain": str(item.get("domain", "")).strip(),
                        "source_country": str(item.get("source_country", "")).strip(),
                        "themes": _headline_theme_labels(item),
                    }
                    for item in items[:4]
                    if str(item.get("title", "")).strip()
                ],
            }
        )
    return clusters


def _recommended_source_articles(headlines: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in headlines:
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title or not url or url in seen_urls:
            continue
        themes = _headline_theme_labels(item)
        domain = str(item.get("domain", "")).strip()
        geography = str(item.get("source_country", "")).strip().upper()
        subtitle_parts = [part for part in [domain, geography, ", ".join(themes[:2])] if part]
        results.append(
            {
                "kind": "article",
                "title": title,
                "url": url,
                "subtitle": " | ".join(subtitle_parts) or "Source article",
            }
        )
        seen_urls.add(url)
        if len(results) >= limit:
            break
    return results


def _related_public_briefings(
    db: Session,
    briefing: PublicEconomicBriefing,
    *,
    limit: int = 3,
) -> list[tuple[PublicEconomicBriefing, list[str]]]:
    current_themes = set(_theme_counts(briefing.items_json).keys())
    if not current_themes:
        return []

    candidates = list(
        db.scalars(
            select(PublicEconomicBriefing)
            .where(PublicEconomicBriefing.briefing_date < briefing.briefing_date)
            .order_by(PublicEconomicBriefing.briefing_date.desc(), PublicEconomicBriefing.created_at.desc())
            .limit(28)
        )
    )
    scored: list[tuple[int, str, PublicEconomicBriefing, list[str]]] = []
    for candidate in candidates:
        overlap = sorted(current_themes & set(_theme_counts(candidate.items_json).keys()))
        if not overlap:
            continue
        score = (len(overlap) * 10) + min(candidate.headline_count, 8)
        scored.append((score, candidate.briefing_date, candidate, overlap))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [(candidate, overlap) for _, _, candidate, overlap in scored[:limit]]


def build_public_recommended_reading(
    db: Session,
    briefing: PublicEconomicBriefing,
    *,
    public_base_url: str = "",
) -> dict[str, Any]:
    source_articles = _recommended_source_articles(briefing.items_json)
    related_briefings = [
        {
            "kind": "briefing",
            "title": candidate.title,
            "url": _build_public_briefing_url(candidate.slug, public_base_url),
            "subtitle": f"{candidate.briefing_date} | shared themes: {', '.join(overlap)}",
        }
        for candidate, overlap in _related_public_briefings(db, briefing)
    ]
    summary_pages = [
        {
            "kind": "summary",
            "title": page["title"],
            "url": page["share_url"],
            "subtitle": page["subtitle"],
        }
        for page in _public_summary_pages(public_base_url)
    ]
    return {
        "source_articles": source_articles,
        "related_briefings": related_briefings,
        "summary_pages": summary_pages,
    }


def _copy_public_item(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    if isinstance(item.get("themes"), list):
        copied["themes"] = list(item.get("themes") or [])
    return copied


def _public_item_identity(item: dict[str, Any]) -> str:
    url = str(item.get("url", "")).strip().lower()
    if url:
        return url
    title = str(item.get("title", "")).strip().lower()
    if title:
        return title
    return slugify(str(item), max_length=120)


def _sorted_public_items(items: list[dict[str, Any]], *, timezone_name: str) -> list[dict[str, Any]]:
    return sorted(
        [_copy_public_item(item) for item in items],
        key=lambda item: _public_item_sort_key(item, timezone_name=timezone_name),
        reverse=True,
    )


def _all_public_briefing_items(briefing: PublicEconomicBriefing) -> list[dict[str, Any]]:
    public_news = briefing.raw_json.get("public_news", {}) if isinstance(briefing.raw_json, dict) else {}
    all_items = public_news.get("all_items")
    if isinstance(all_items, list) and all_items:
        return [_copy_public_item(item) for item in all_items if isinstance(item, dict)]
    fallback_items = public_news.get("items")
    if isinstance(fallback_items, list) and fallback_items:
        return [_copy_public_item(item) for item in fallback_items if isinstance(item, dict)]
    return [_copy_public_item(item) for item in briefing.items_json if isinstance(item, dict)]


def _excluded_public_briefing_items(briefing: PublicEconomicBriefing) -> list[dict[str, Any]]:
    manual_filters = briefing.raw_json.get("manual_filters", {}) if isinstance(briefing.raw_json, dict) else {}
    excluded_items = manual_filters.get("excluded_items")
    if isinstance(excluded_items, list):
        return [_copy_public_item(item) for item in excluded_items if isinstance(item, dict)]
    return []


def _public_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_items: list[dict[str, Any]] = []
    for item in items:
        review_items.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "domain": str(item.get("domain", "")).strip(),
                "source_country": str(item.get("source_country", "")).strip().upper(),
                "source_name": str(item.get("source_name", "")).strip(),
                "source_type": str(item.get("source_type", "")).strip() or "media",
                "region_focus": str(item.get("region_focus", "")).strip(),
                "credibility": str(item.get("credibility", "")).strip(),
                "source_note": str(item.get("source_note", "")).strip(),
                "excerpt": str(item.get("excerpt", "")).strip(),
                "themes": _headline_theme_labels(item),
                "seendate": str(item.get("seendate", "")).strip(),
            }
        )
    return review_items


def _public_source_directory_rows(
    briefing: PublicEconomicBriefing,
    *,
    active_items: list[dict[str, Any]],
    excluded_items: list[dict[str, Any]],
    feed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_counts = Counter(str(item.get("source_name", "")).strip() for item in active_items if str(item.get("source_name", "")).strip())
    excluded_counts = Counter(str(item.get("source_name", "")).strip() for item in excluded_items if str(item.get("source_name", "")).strip())
    status_by_name = {
        str(row.get("name", "")).strip(): row
        for row in feed_rows
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    }
    configured_by_name = {
        str(source.get("name", "")).strip(): source
        for source in PUBLIC_SOURCE_DIRECTORY
        if str(source.get("name", "")).strip()
    }
    ordered_names = list(dict.fromkeys([*configured_by_name.keys(), *status_by_name.keys(), *active_counts.keys(), *excluded_counts.keys()]))
    rows: list[dict[str, Any]] = []
    for name in ordered_names:
        source = configured_by_name.get(name, {})
        status = status_by_name.get(name, {})
        rows.append(
            {
                "name": name,
                "domain": str(status.get("domain") or source.get("domain") or "").strip().lower(),
                "source_country": str(status.get("source_country") or source.get("source_country") or "").strip().upper(),
                "source_type": str(status.get("source_type") or source.get("source_type") or "media").strip(),
                "region_focus": str(status.get("region_focus") or source.get("region_focus") or "").strip(),
                "credibility": str(status.get("credibility") or source.get("credibility") or "").strip(),
                "note": str(status.get("note") or source.get("note") or "").strip(),
                "kind": str(status.get("kind") or source.get("kind") or "rss").strip(),
                "status": str(status.get("status") or ("configured" if source else "observed")).strip(),
                "matched_items": int(status.get("matched_items", 0) or 0),
                "visible_count": int(active_counts.get(name, 0)),
                "excluded_count": int(excluded_counts.get(name, 0)),
                "message": str(status.get("message", "")).strip(),
            }
        )
    rows.sort(key=lambda row: (row["source_type"] != "official", -row["visible_count"], row["name"]))
    return rows


def build_public_source_panel(briefing: PublicEconomicBriefing) -> dict[str, Any]:
    all_items = _all_public_briefing_items(briefing)
    active_items = [_copy_public_item(item) for item in briefing.items_json if isinstance(item, dict)]
    excluded_items = _excluded_public_briefing_items(briefing)
    active_domain_counts = Counter(dict(_top_domains(active_items, limit=50)))
    excluded_domain_counts = Counter(dict(_top_domains(excluded_items, limit=50)))
    active_country_counts = Counter(dict(_top_source_countries(active_items, limit=20)))
    excluded_country_counts = Counter(dict(_top_source_countries(excluded_items, limit=20)))
    all_domains = sorted(set(active_domain_counts) | set(excluded_domain_counts))
    all_countries = sorted(set(active_country_counts) | set(excluded_country_counts))
    public_news = briefing.raw_json.get("public_news", {}) if isinstance(briefing.raw_json, dict) else {}
    source_payload = public_news.get("sources", {}) if isinstance(public_news, dict) else {}
    rss_payload = source_payload.get("rss", {}) if isinstance(source_payload, dict) else {}
    official_payload = source_payload.get("official", {}) if isinstance(source_payload, dict) else {}
    gdelt_payload = source_payload.get("gdelt", {}) if isinstance(source_payload, dict) else {}
    feed_rows = []
    for feed in [
        *(rss_payload.get("feeds", []) if isinstance(rss_payload, dict) else []),
        *(official_payload.get("feeds", []) if isinstance(official_payload, dict) else []),
    ]:
        if not isinstance(feed, dict):
            continue
        feed_rows.append(
            {
                "name": str(feed.get("name", "")).strip(),
                "status": str(feed.get("status", "")).strip() or "unknown",
                "matched_items": int(feed.get("matched_items", 0) or 0),
                "message": str(feed.get("message", "")).strip(),
                "domain": str(feed.get("domain", "")).strip(),
                "source_country": str(feed.get("source_country", "")).strip().upper(),
                "source_type": str(feed.get("source_type", "")).strip() or "media",
                "region_focus": str(feed.get("region_focus", "")).strip(),
                "credibility": str(feed.get("credibility", "")).strip(),
                "note": str(feed.get("note", "")).strip(),
                "kind": str(feed.get("kind", "")).strip() or "rss",
            }
        )
    ok_feed_count = sum(1 for feed in feed_rows if feed.get("status") == "ok")
    gdelt_items = gdelt_payload.get("items", []) if isinstance(gdelt_payload, dict) else []
    type_active_counts = Counter(str(item.get("source_type", "")).strip() or "media" for item in active_items)
    type_excluded_counts = Counter(str(item.get("source_type", "")).strip() or "media" for item in excluded_items)
    type_names = sorted(set(type_active_counts) | set(type_excluded_counts))
    region_active_counts = Counter(
        str(item.get("region_focus", "")).strip() or "Global" for item in active_items
    )
    region_excluded_counts = Counter(
        str(item.get("region_focus", "")).strip() or "Global" for item in excluded_items
    )
    region_names = sorted(set(region_active_counts) | set(region_excluded_counts))
    source_directory = _public_source_directory_rows(
        briefing,
        active_items=active_items,
        excluded_items=excluded_items,
        feed_rows=feed_rows,
    )
    return {
        "overview": [
            {"label": "Visible headlines", "value": str(len(active_items))},
            {"label": "Filtered headlines", "value": str(len(excluded_items))},
            {
                "label": "Unique domains",
                "value": str(len({str(item.get("domain", "")).strip().lower() for item in all_items if str(item.get("domain", "")).strip()})),
            },
            {"label": "Feed health", "value": f"{ok_feed_count}/{len(feed_rows) or len(PUBLIC_SOURCE_DIRECTORY)} ok"},
        ],
        "domains": [
            {
                "domain": domain,
                "active_count": int(active_domain_counts.get(domain, 0)),
                "excluded_count": int(excluded_domain_counts.get(domain, 0)),
            }
            for domain in all_domains[:8]
        ],
        "countries": [
            {
                "country": country,
                "active_count": int(active_country_counts.get(country, 0)),
                "excluded_count": int(excluded_country_counts.get(country, 0)),
            }
            for country in all_countries[:8]
        ],
        "type_breakdown": [
            {
                "type": type_name or "unknown",
                "active_count": int(type_active_counts.get(type_name, 0)),
                "excluded_count": int(type_excluded_counts.get(type_name, 0)),
            }
            for type_name in type_names
        ],
        "region_breakdown": [
            {
                "region": region_name or "Global",
                "active_count": int(region_active_counts.get(region_name, 0)),
                "excluded_count": int(region_excluded_counts.get(region_name, 0)),
            }
            for region_name in region_names[:12]
        ],
        "available_filters": {
            "source_types": [type_name or "unknown" for type_name in type_names],
            "countries": all_countries[:12],
            "regions": region_names[:12],
            "priority_views": [
                {"slug": "all", "label": "All Sources"},
                {"slug": "official", "label": "Official First"},
                {"slug": "us", "label": "United States"},
                {"slug": "cn", "label": "China"},
                {"slug": "developed", "label": "Developed Markets"},
            ],
        },
        "feeds": feed_rows,
        "source_directory": source_directory,
        "gdelt": {
            "status": str(gdelt_payload.get("status", "")).strip() or "unknown",
            "item_count": len(gdelt_items) if isinstance(gdelt_items, list) else 0,
        },
        "notes": [
            "Official source coverage includes government and central-bank releases alongside media headlines.",
            f"Official-page parsers allow up to {PUBLIC_OFFICIAL_LOOKBACK_DAYS} day(s) of lookback when same-day official releases are sparse.",
        ],
    }


def _rebuild_public_briefing_summary(
    briefing: PublicEconomicBriefing,
    *,
    active_items: list[dict[str, Any]],
) -> None:
    raw_json = json.loads(json.dumps(briefing.raw_json if isinstance(briefing.raw_json, dict) else {}))
    public_news = raw_json.get("public_news", {}) if isinstance(raw_json, dict) else {}
    fred_snapshots = raw_json.get("fred", []) if isinstance(raw_json.get("fred"), list) else []
    public_news["items"] = [_copy_public_item(item) for item in active_items]
    public_news.setdefault("all_items", _all_public_briefing_items(briefing))
    raw_json["public_news"] = public_news
    briefing.raw_json = raw_json
    briefing.items_json = [_copy_public_item(item) for item in active_items]
    briefing.headline_count = len(active_items)
    briefing.summary_markdown = build_structured_economic_briefing(
        title=briefing.title,
        report_date=briefing.briefing_date,
        timezone_name=briefing.timezone_name,
        headlines=briefing.items_json,
        fred_snapshots=fred_snapshots if isinstance(fred_snapshots, list) else [],
        query_text=briefing.query_text,
        template_version=briefing.template_version or PUBLIC_TEMPLATE_VERSION,
    )


def moderate_public_briefing_item(
    db: Session,
    settings: Settings,
    briefing: PublicEconomicBriefing,
    *,
    action: str,
    item_url: str = "",
    item_title: str = "",
    actor_email: str = "",
) -> PublicEconomicBriefing:
    normalized_action = action.strip().lower()
    if normalized_action not in {"exclude", "restore"}:
        raise ValueError("Unsupported moderation action.")
    url_value = item_url.strip()
    title_value = item_title.strip()
    if not url_value and not title_value:
        raise ValueError("A headline URL or title is required for moderation.")

    def matches(item: dict[str, Any]) -> bool:
        url_match = url_value and str(item.get("url", "")).strip().lower() == url_value.lower()
        title_match = title_value and str(item.get("title", "")).strip() == title_value
        return bool(url_match or title_match)

    all_items = _all_public_briefing_items(briefing)
    excluded_items = _excluded_public_briefing_items(briefing)
    active_items = [_copy_public_item(item) for item in briefing.items_json if isinstance(item, dict)]

    raw_json = json.loads(json.dumps(briefing.raw_json if isinstance(briefing.raw_json, dict) else {}))
    manual_filters = raw_json.get("manual_filters", {}) if isinstance(raw_json.get("manual_filters"), dict) else {}
    history = manual_filters.get("history", []) if isinstance(manual_filters.get("history"), list) else []

    if normalized_action == "exclude":
        target = next((item for item in all_items if matches(item)), None)
        if not target:
            raise FileNotFoundError("Public headline not found for exclusion.")
        target_id = _public_item_identity(target)
        if any(_public_item_identity(item) == target_id for item in excluded_items):
            return briefing
        excluded_items.append(_copy_public_item(target))
        active_items = [item for item in active_items if _public_item_identity(item) != target_id]
    else:
        target = next((item for item in excluded_items if matches(item)), None)
        if not target:
            raise FileNotFoundError("Excluded public headline not found for restore.")
        target_id = _public_item_identity(target)
        excluded_items = [item for item in excluded_items if _public_item_identity(item) != target_id]
        if not any(_public_item_identity(item) == target_id for item in active_items):
            active_items.append(_copy_public_item(target))

    active_items = _sorted_public_items(active_items, timezone_name=briefing.timezone_name or settings.public_digest_timezone)
    excluded_items = _sorted_public_items(excluded_items, timezone_name=briefing.timezone_name or settings.public_digest_timezone)
    manual_filters["excluded_items"] = excluded_items
    history.append(
        {
            "action": normalized_action,
            "url": url_value,
            "title": title_value,
            "actor_email": actor_email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    manual_filters["history"] = history[-50:]
    raw_json["manual_filters"] = manual_filters
    briefing.raw_json = raw_json
    _rebuild_public_briefing_summary(briefing, active_items=active_items)
    db.add(briefing)
    db.flush()
    return briefing


def serialize_public_briefing_detail(
    db: Session,
    briefing: PublicEconomicBriefing,
    *,
    public_base_url: str = "",
) -> dict[str, Any]:
    payload = serialize_public_briefing(briefing, public_base_url=public_base_url)
    payload["news_clusters"] = build_public_news_clusters(briefing.items_json)
    payload["recommended_reading"] = build_public_recommended_reading(
        db,
        briefing,
        public_base_url=public_base_url,
    )
    payload["source_panel"] = build_public_source_panel(briefing)
    payload["review_items"] = _public_review_items(briefing.items_json)
    payload["excluded_items"] = _public_review_items(_excluded_public_briefing_items(briefing))
    manual_filters = briefing.raw_json.get("manual_filters", {}) if isinstance(briefing.raw_json, dict) else {}
    payload["moderation"] = {
        "active_count": len(briefing.items_json),
        "excluded_count": len(payload["excluded_items"]),
        "last_action_at": (
            manual_filters.get("history", [])[-1].get("timestamp")
            if isinstance(manual_filters.get("history"), list) and manual_filters.get("history")
            else None
        ),
    }
    return payload


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


def build_literature_citation(entry: LiteratureEntry) -> str:
    authors = [str(name).strip() for name in entry.authors_json if str(name).strip()]
    author_text = ", ".join(authors[:4]) if authors else "Unknown author"
    if len(authors) > 4:
        author_text = f"{author_text}, et al."
    year_text = str(entry.publication_year or "n.d.")
    venue_text = str(entry.venue or "").strip()
    doi_text = str(entry.doi or "").strip()
    parts = [f"{author_text} ({year_text}).", str(entry.title or "Untitled").strip() + "."]
    if venue_text:
        parts.append(f"{venue_text}.")
    if doi_text:
        parts.append(f"DOI: {doi_text}.")
    return " ".join(part for part in parts if part).strip()


def _extract_pdf_urls_from_html(html_text: str, *, base_url: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, html_text, flags=re.IGNORECASE):
            candidate = urljoin(base_url, match.strip())
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    href_matches = re.findall(r'href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE)
    for href in href_matches:
        resolved = urljoin(base_url, href.strip())
        lowered = resolved.lower()
        if not resolved or resolved in candidates:
            continue
        if lowered.endswith(".pdf") or "/pdf" in lowered or "download" in lowered and "pdf" in lowered:
            candidates.append(resolved)
    return candidates


def _download_pdf_candidate(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=60)
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type", "")).lower()
    content = response.content or b""
    if "application/pdf" in content_type or content.startswith(b"%PDF"):
        return content, response.url or url
    if "html" in content_type or b"<html" in content[:256].lower():
        for nested_url in _extract_pdf_urls_from_html(content.decode("utf-8", errors="ignore"), base_url=response.url or url):
            nested_response = requests.get(nested_url, headers=DEFAULT_HEADERS, timeout=60)
            nested_response.raise_for_status()
            nested_type = str(nested_response.headers.get("Content-Type", "")).lower()
            nested_content = nested_response.content or b""
            if "application/pdf" in nested_type or nested_content.startswith(b"%PDF"):
                return nested_content, nested_response.url or nested_url
        raise ValueError("Landing page did not expose a downloadable PDF link.")
    raise ValueError(f"URL did not return a PDF. Content-Type: {content_type or 'unknown'}")


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


def import_literature_pdf_asset(
    db: Session,
    settings: Settings,
    *,
    user: User,
    workspace: Workspace,
    literature_entry_id: str,
) -> dict[str, Any]:
    entry = db.get(LiteratureEntry, literature_entry_id)
    if not entry or entry.owner_user_id != user.id or entry.workspace_id != workspace.id:
        raise FileNotFoundError("Literature entry not found.")

    existing_asset_id = str((entry.raw_json or {}).get("_workspace_pdf_asset_id") or "").strip()
    if existing_asset_id:
        existing_asset = db.get(DataAsset, existing_asset_id)
        if existing_asset and existing_asset.owner_user_id == user.id and existing_asset.workspace_id == workspace.id:
            return {
                "entry": serialize_literature_entry(entry),
                "asset": serialize_asset(existing_asset),
                "download_url": f"/api/assets/{existing_asset.id}/download",
                "source_url": existing_asset.source_url or entry.pdf_url or entry.landing_page_url,
                "imported": False,
            }

    candidate_urls: list[str] = []
    for url_value in [entry.pdf_url, entry.landing_page_url]:
        candidate = str(url_value or "").strip()
        if candidate and candidate not in candidate_urls:
            candidate_urls.append(candidate)
    if not candidate_urls:
        raise ValueError("This literature entry does not expose a downloadable open-access PDF.")

    pdf_content = b""
    resolved_source_url = ""
    last_error = ""
    for candidate_url in candidate_urls:
        try:
            pdf_content, resolved_source_url = _download_pdf_candidate(candidate_url)
            if pdf_content:
                break
        except Exception as exc:
            last_error = str(exc)

    if not pdf_content:
        raise ValueError(last_error or "Open-access PDF download failed.")

    filename_stem = slugify(entry.title or "openalex-paper", max_length=80) or "openalex-paper"
    if entry.publication_year:
        filename_stem = f"{filename_stem}-{entry.publication_year}"
    asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=f"{filename_stem}.pdf",
        content=pdf_content,
        content_type="application/pdf",
        description=f"Imported from Paper Library: {entry.title}",
        source_url=resolved_source_url,
    )
    asset.metadata_json = {
        **asset.metadata_json,
        "literature_entry_id": entry.id,
        "openalex_id": entry.openalex_id,
        "literature_title": entry.title,
        "import_source": "paper_library",
    }
    entry.raw_json = {
        **(entry.raw_json or {}),
        "_workspace_pdf_asset_id": asset.id,
        "_workspace_pdf_asset_title": asset.title,
    }
    db.flush()
    return {
        "entry": serialize_literature_entry(entry),
        "asset": serialize_asset(asset),
        "download_url": f"/api/assets/{asset.id}/download",
        "source_url": resolved_source_url,
        "imported": True,
    }


def import_literature_pdf_assets(
    db: Session,
    settings: Settings,
    *,
    user: User,
    workspace: Workspace,
    literature_entry_ids: list[str] | None = None,
) -> dict[str, Any]:
    entries = list_literature_entries(db, user=user, workspace=workspace)
    requested_ids = {str(item).strip() for item in (literature_entry_ids or []) if str(item).strip()}
    if requested_ids:
        entries = [entry for entry in entries if entry.id in requested_ids]
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for entry in entries:
        if not (str(entry.pdf_url or "").strip() or str(entry.landing_page_url or "").strip()):
            skipped.append({"entry_id": entry.id, "title": entry.title, "reason": "No open-access source URL."})
            continue
        try:
            result = import_literature_pdf_asset(
                db,
                settings,
                user=user,
                workspace=workspace,
                literature_entry_id=entry.id,
            )
            imported.append(
                {
                    "entry_id": entry.id,
                    "title": entry.title,
                    "asset_id": result["asset"]["id"],
                    "imported": bool(result["imported"]),
                }
            )
        except Exception as exc:
            failed.append({"entry_id": entry.id, "title": entry.title, "reason": str(exc)})
    return {
        "requested_count": len(entries),
        "imported_count": len(imported),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
    }


def import_literature_knowledge_record(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    literature_entry_id: str,
) -> dict[str, Any]:
    entry = db.get(LiteratureEntry, literature_entry_id)
    if not entry or entry.owner_user_id != user.id or entry.workspace_id != workspace.id:
        raise FileNotFoundError("Literature entry not found.")

    existing_record_id = str((entry.raw_json or {}).get("_workspace_knowledge_record_id") or "").strip()
    if existing_record_id:
        from .entities import KnowledgeRecord

        existing_record = db.get(KnowledgeRecord, existing_record_id)
        if existing_record and existing_record.owner_user_id == user.id and existing_record.workspace_id == workspace.id:
            return {
                "entry": serialize_literature_entry(entry),
                "record": {
                    "id": existing_record.id,
                    "title": existing_record.title,
                    "created_at": existing_record.created_at.isoformat(),
                },
                "imported": False,
            }

    citation_text = build_literature_citation(entry)
    authors = [str(name).strip() for name in entry.authors_json if str(name).strip()]
    note_lines = [
        f"# {entry.title}",
        "",
        "## Citation",
        "",
        citation_text,
        "",
        "## Abstract",
        "",
        entry.abstract or "No abstract available.",
        "",
        "## Metadata",
        "",
        f"- OpenAlex ID: {entry.openalex_id}",
        f"- Publication year: {entry.publication_year or 'n/a'}",
        f"- Venue: {entry.venue or 'n/a'}",
        f"- DOI: {entry.doi or 'n/a'}",
        f"- Cited by count: {entry.cited_by_count}",
        f"- Authors: {', '.join(authors) if authors else 'n/a'}",
        f"- Landing page: {entry.landing_page_url or 'n/a'}",
        f"- Open-access PDF: {entry.pdf_url or 'n/a'}",
    ]
    if entry.keywords_json:
        note_lines.extend(["", "## Keywords", "", ", ".join(str(keyword).strip() for keyword in entry.keywords_json if str(keyword).strip())])

    record = create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Paper Note: {entry.title}",
        content="\n".join(note_lines).strip(),
        tags=["paper-library", "literature", "openalex"],
        metadata={
            "source_type": "paper_library",
            "literature_entry_id": entry.id,
            "openalex_id": entry.openalex_id,
            "citation_text": citation_text,
            "doi": entry.doi,
            "publication_year": entry.publication_year,
            "venue": entry.venue,
            "authors": authors,
            "pdf_url": entry.pdf_url,
            "landing_page_url": entry.landing_page_url,
        },
    )
    entry.raw_json = {
        **(entry.raw_json or {}),
        "_workspace_knowledge_record_id": record.id,
        "_workspace_knowledge_record_title": record.title,
    }
    db.flush()
    return {
        "entry": serialize_literature_entry(entry),
        "record": {
            "id": record.id,
            "title": record.title,
            "created_at": record.created_at.isoformat(),
        },
        "imported": True,
    }


def import_literature_knowledge_records(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    literature_entry_ids: list[str] | None = None,
) -> dict[str, Any]:
    entries = list_literature_entries(db, user=user, workspace=workspace)
    requested_ids = {str(item).strip() for item in (literature_entry_ids or []) if str(item).strip()}
    if requested_ids:
        entries = [entry for entry in entries if entry.id in requested_ids]
    imported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for entry in entries:
        try:
            result = import_literature_knowledge_record(
                db,
                user=user,
                workspace=workspace,
                literature_entry_id=entry.id,
            )
            imported.append(
                {
                    "entry_id": entry.id,
                    "title": entry.title,
                    "record_id": result["record"]["id"],
                    "imported": bool(result["imported"]),
                }
            )
        except Exception as exc:
            failed.append({"entry_id": entry.id, "title": entry.title, "reason": str(exc)})
    return {
        "requested_count": len(entries),
        "imported_count": len(imported),
        "failed_count": len(failed),
        "imported": imported,
        "failed": failed,
    }


def fetch_gdelt_hotspots(
    settings: Settings,
    *,
    query_text: str = "",
    max_records: int | None = None,
) -> dict[str, Any]:
    query = _normalize_gdelt_query(query_text.strip() or settings.gdelt_query)
    try:
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
    except requests.RequestException as exc:
        return {"status": "error", "query": query, "items": [], "message": str(exc)}
    if response.status_code == 429:
        return {"status": "rate_limited", "query": query, "items": [], "message": response.text}
    if response.status_code >= 400:
        return {"status": "error", "query": query, "items": [], "message": response.text}
    try:
        payload = response.json()
    except ValueError as exc:
        return {"status": "error", "query": query, "items": [], "message": str(exc)}
    items = []
    for article in payload.get("articles", [])[: max_records or settings.gdelt_max_records]:
        items.append(
            {
                "title": article.get("title", ""),
                "seendate": article.get("seendate", ""),
                "domain": article.get("domain", ""),
                "source_country": article.get("sourcecountry", ""),
                "language": article.get("language", ""),
                "source_type": "media",
                "region_focus": "Global",
                "credibility": "news aggregation",
                "source_note": "GDELT article feed",
                "source_name": article.get("domain", ""),
                "url": article.get("url", ""),
                "excerpt": truncate_text(article.get("socialimage", "") or article.get("title", ""), 160),
            }
        )
    return {"status": "ok", "query": query, "items": items}


def _normalize_gdelt_query(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    if " OR " in normalized and not (normalized.startswith("(") and normalized.endswith(")")):
        return f"({normalized})"
    return normalized


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("&nbsp;", " ").strip()


def _decode_response_text(response: requests.Response) -> str:
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.text


def _normalize_source_href(base_url: str, href: str) -> str:
    raw_href = str(href or "").strip()
    if not raw_href:
        return ""
    if raw_href.startswith("//"):
        return f"https:{raw_href}"
    return urljoin(base_url, raw_href)


def _extract_date_from_url(href: str) -> str:
    raw_href = str(href or "").strip()
    match = re.search(r"/(\d{6})/(\d{2})/", raw_href)
    if match:
        year_month = match.group(1)
        day = match.group(2)
        return f"{year_month[:4]}-{year_month[4:6]}-{day}"
    match = re.search(r"/(\d{4})/(\d{4})/", raw_href)
    if match:
        year = match.group(1)
        month_day = match.group(2)
        return f"{year}-{month_day[:2]}-{month_day[2:4]}"
    return ""


def _coerce_source_item(
    source: dict[str, Any],
    *,
    title: str,
    link: str,
    pub_date: str,
    excerpt: str = "",
    lookback_days: int = 0,
) -> dict[str, Any]:
    return {
        "title": title.strip(),
        "seendate": pub_date.strip(),
        "domain": (urlparse(link).netloc or str(source.get("domain", ""))).lower(),
        "source_country": str(source.get("source_country", "")).strip().upper(),
        "language": str(source.get("language", "")).strip(),
        "source_name": str(source.get("name", "")).strip(),
        "source_type": str(source.get("source_type", "")).strip() or "media",
        "region_focus": str(source.get("region_focus", "")).strip(),
        "credibility": str(source.get("credibility", "")).strip(),
        "source_note": str(source.get("note", "")).strip(),
        "url": link.strip(),
        "excerpt": truncate_text(excerpt or title, 220),
        "allowed_lookback_days": int(max(0, lookback_days)),
    }


def _query_terms(query_text: str) -> list[str]:
    normalized = (
        query_text.replace("(", " ")
        .replace(")", " ")
        .replace('"', " ")
        .replace("'", " ")
        .replace(",", " ")
    )
    terms = [part.strip().lower() for part in normalized.split("OR")]
    return [term for term in terms if term]


def _keyword_present(text: str, keyword: str) -> bool:
    phrase = keyword.strip().lower()
    if not phrase:
        return False
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"\b"
    return re.search(pattern, text) is not None


def _parse_news_datetime(raw_value: str, *, timezone_name: str) -> datetime | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo(timezone_name))
        except ValueError:
            pass
    try:
        if raw.endswith("Z") and "T" in raw:
            parsed = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo(timezone_name))
    except ValueError:
        pass
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo(timezone_name))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y"):
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=ZoneInfo(timezone_name))
            return parsed.astimezone(ZoneInfo(timezone_name))
        except ValueError:
            continue
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo(timezone_name))
    except (TypeError, ValueError, OverflowError):
        return None


def _is_local_day_within_window(
    raw_value: str,
    *,
    timezone_name: str,
    target_date: datetime.date,
    lookback_days: int = 0,
) -> bool:
    parsed = _parse_news_datetime(raw_value, timezone_name=timezone_name)
    if parsed is None:
        return False
    earliest = target_date - timedelta(days=max(0, lookback_days))
    return earliest <= parsed.date() <= target_date


def _is_same_local_day(raw_value: str, *, timezone_name: str, target_date: datetime.date) -> bool:
    parsed = _parse_news_datetime(raw_value, timezone_name=timezone_name)
    if parsed is None:
        return False
    return parsed.date() == target_date


def _is_relevant_public_news(item: dict[str, Any], *, query_text: str) -> bool:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("excerpt", "")),
        ]
    ).lower()
    keywords = set(PUBLIC_NEWS_KEYWORDS)
    keywords.update(_query_terms(query_text))
    return any(_keyword_present(haystack, keyword) for keyword in keywords)


def _iter_feed_entries(root: ElementTree.Element) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for node in root.findall(".//item"):
        entries.append(
            {
                "title": (node.findtext("title") or "").strip(),
                "link": (node.findtext("link") or "").strip(),
                "pub_date": (node.findtext("pubDate") or node.findtext("date") or "").strip(),
                "description": _strip_html(node.findtext("description") or ""),
            }
        )
    for node in root.findall(".//{*}entry"):
        link_node = node.find("{*}link[@rel='alternate']") or node.find("{*}link")
        entries.append(
            {
                "title": (node.findtext("{*}title") or "").strip(),
                "link": (link_node.attrib.get("href", "") if link_node is not None else "").strip(),
                "pub_date": (
                    node.findtext("{*}updated")
                    or node.findtext("{*}published")
                    or node.findtext("{*}date")
                    or ""
                ).strip(),
                "description": _strip_html(node.findtext("{*}summary") or node.findtext("{*}content") or ""),
            }
        )
    return entries


def fetch_rss_hotspots(
    settings: Settings,
    *,
    query_text: str = "",
    max_records: int | None = None,
    now: datetime | None = None,
    feeds: list[dict[str, Any]] | None = None,
    lookback_days: int = 0,
) -> dict[str, Any]:
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    target_date = local_now.date()
    items: list[dict[str, Any]] = []
    feed_status: list[dict[str, Any]] = []
    limit = max(4, max_records or settings.gdelt_max_records)
    for feed in feeds or PUBLIC_MEDIA_RSS_FEEDS:
        try:
            response = requests.get(feed["url"], headers=DEFAULT_HEADERS, timeout=20)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            feed_status.append(
                {
                    "name": feed["name"],
                    "status": "error",
                    "message": str(exc),
                    "matched_items": 0,
                    "domain": feed.get("domain", ""),
                    "source_country": feed.get("source_country", ""),
                    "source_type": feed.get("source_type", "media"),
                    "region_focus": feed.get("region_focus", ""),
                    "credibility": feed.get("credibility", ""),
                    "note": feed.get("note", ""),
                    "kind": "rss",
                }
            )
            continue
        matched_count = 0
        for entry in _iter_feed_entries(root):
            title = entry["title"]
            link = entry["link"]
            pub_date = entry["pub_date"]
            description = entry["description"]
            if not title or not link:
                continue
            if not _is_local_day_within_window(
                pub_date,
                timezone_name=settings.public_digest_timezone,
                target_date=target_date,
                lookback_days=lookback_days,
            ):
                continue
            item = _coerce_source_item(
                feed,
                title=title,
                link=link,
                pub_date=pub_date,
                excerpt=description or title,
                lookback_days=lookback_days,
            )
            if not _is_relevant_public_news(item, query_text=query_text):
                continue
            items.append(item)
            matched_count += 1
            if matched_count >= limit:
                break
        feed_status.append(
            {
                "name": feed["name"],
                "status": "ok",
                "matched_items": matched_count,
                "message": "",
                "domain": feed.get("domain", ""),
                "source_country": feed.get("source_country", ""),
                "source_type": feed.get("source_type", "media"),
                "region_focus": feed.get("region_focus", ""),
                "credibility": feed.get("credibility", ""),
                "note": feed.get("note", ""),
                "kind": "rss",
            }
        )
    return {"status": "ok", "query": query_text.strip() or settings.gdelt_query, "items": items, "feeds": feed_status}


def _parse_treasury_press_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<time datetime="(?P<date>[^"]+)"[^>]*>.*?</time>\s*<div class="news-title"><a href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        flags=re.S,
    )
    for match in pattern.finditer(html):
        title = _strip_html(match.group("title"))
        link = _normalize_source_href(source["url"], match.group("href"))
        items.append(
            _coerce_source_item(
                source,
                title=title,
                link=link,
                pub_date=match.group("date"),
                excerpt=title,
                lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
            )
        )
    return items


def _parse_bea_current_release_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r'(?P<date>\d{4}-\d{2}-\d{2}).{0,500}?href="(?P<href>/news/[^"#?]+)"[^>]*>(?P<title>.*?)</a>',
        flags=re.S,
    )
    seen: set[str] = set()
    for match in pattern.finditer(html):
        title = _strip_html(match.group("title"))
        if not title or title.lower() in {"economy at a glance", "archive", "news releases"}:
            continue
        link = _normalize_source_href(source["url"], match.group("href"))
        if link in seen:
            continue
        seen.add(link)
        items.append(
            _coerce_source_item(
                source,
                title=title,
                link=link,
                pub_date=match.group("date"),
                excerpt=title,
                lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
            )
        )
    return items


def _parse_state_council_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r'href="(?P<href>//english\.www\.gov\.cn/news/\d{6}/\d{2}/content_[^"]+\.html)"[^>]*>(?P<title>[^<]+)</a>',
        flags=re.S,
    )
    seen: set[str] = set()
    for match in pattern.finditer(html):
        link = _normalize_source_href(source["url"], match.group("href"))
        if link in seen:
            continue
        seen.add(link)
        title = _strip_html(match.group("title"))
        pub_date = _extract_date_from_url(link)
        items.append(
            _coerce_source_item(
                source,
                title=title,
                link=link,
                pub_date=pub_date,
                excerpt=title,
                lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
            )
        )
    return items


def _parse_safe_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<a href="(?P<href>/en/\d{4}/\d{4}/\d+\.html)"[^>]*title="(?P<title>[^"]+)"[^>]*>.*?</a>\s*</dt>\s*<dd>(?P<date>\d{4}-\d{2}-\d{2})</dd>',
        flags=re.S,
    )
    for match in pattern.finditer(html):
        items.append(
            _coerce_source_item(
                source,
                title=_strip_html(match.group("title")),
                link=_normalize_source_href(source["url"], match.group("href")),
                pub_date=match.group("date"),
                excerpt=_strip_html(match.group("title")),
                lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
            )
        )
    return items


def _parse_bank_of_canada_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<span class="pressdate">(?P<date>[^<]+)</span>\s*(?:<h5[^>]*>)?\s*<a[^>]+href="(?P<href>https://www\.bankofcanada\.ca/\d{4}/\d{2}/[^"]+/?)"[^>]*>(?P<title>[^<]+)</a>',
        flags=re.S,
    )
    seen: set[str] = set()
    for match in pattern.finditer(html):
        link = _normalize_source_href(source["url"], match.group("href"))
        if link in seen:
            continue
        seen.add(link)
        title = _strip_html(match.group("title"))
        items.append(
            _coerce_source_item(
                source,
                title=title,
                link=link,
                pub_date=match.group("date"),
                excerpt=title,
                lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
            )
        )
    return items


def _parse_mof_japan_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    section_pattern = re.compile(
        r'<a name="a\d{8}"></a><h3 class="heading-lv3">(?P<date>[^<]+)</h3><div class="information-more-block">(?P<body>.*?)(?=<a name="a\d{8}"></a><h3 class="heading-lv3">|$)',
        flags=re.S,
    )
    item_pattern = re.compile(
        r'<li class="information-item"><a href="(?P<href>[^"]+)"[^>]*class="information-item-inner">.*?<p>(?P<title>.*?)</p>',
        flags=re.S,
    )
    seen: set[str] = set()
    for section in section_pattern.finditer(html):
        pub_date = _strip_html(section.group("date"))
        body = section.group("body")
        for match in item_pattern.finditer(body):
            link = _normalize_source_href(source["url"], match.group("href"))
            if link in seen:
                continue
            seen.add(link)
            title = _strip_html(match.group("title"))
            items.append(
                _coerce_source_item(
                    source,
                    title=title,
                    link=link,
                    pub_date=pub_date,
                    excerpt=title,
                    lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
                )
            )
    return items


def _parse_official_page_items(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    parser_name = str(source.get("parser", "")).strip()
    if parser_name == "treasury_press":
        return _parse_treasury_press_items(source, html)
    if parser_name == "bea_current_releases":
        return _parse_bea_current_release_items(source, html)
    if parser_name == "state_council":
        return _parse_state_council_items(source, html)
    if parser_name == "safe_updates":
        return _parse_safe_items(source, html)
    if parser_name == "bank_of_canada":
        return _parse_bank_of_canada_items(source, html)
    if parser_name == "mof_japan":
        return _parse_mof_japan_items(source, html)
    return []


def fetch_official_hotspots(
    settings: Settings,
    *,
    query_text: str = "",
    max_records: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    target_date = local_now.date()
    limit = max(4, max_records or settings.gdelt_max_records)
    rss_payload = fetch_rss_hotspots(
        settings,
        query_text=query_text,
        max_records=max_records,
        now=now,
        feeds=PUBLIC_OFFICIAL_RSS_FEEDS,
        lookback_days=PUBLIC_OFFICIAL_LOOKBACK_DAYS,
    )
    items: list[dict[str, Any]] = list(rss_payload.get("items", []))
    feed_status: list[dict[str, Any]] = list(rss_payload.get("feeds", []))
    for source in PUBLIC_OFFICIAL_PAGE_SOURCES:
        try:
            response = requests.get(source["url"], headers=DEFAULT_HEADERS, timeout=25)
            response.raise_for_status()
            html = _decode_response_text(response)
        except requests.RequestException as exc:
            feed_status.append(
                {
                    "name": source["name"],
                    "status": "error",
                    "matched_items": 0,
                    "message": str(exc),
                    "domain": source.get("domain", ""),
                    "source_country": source.get("source_country", ""),
                    "source_type": source.get("source_type", "official"),
                    "region_focus": source.get("region_focus", ""),
                    "credibility": source.get("credibility", ""),
                    "note": source.get("note", ""),
                    "kind": source.get("kind", "html"),
                }
            )
            continue
        matched_count = 0
        for item in _parse_official_page_items(source, html):
            if not item.get("title") or not item.get("url"):
                continue
            if not _is_local_day_within_window(
                str(item.get("seendate", "")),
                timezone_name=settings.public_digest_timezone,
                target_date=target_date,
                lookback_days=int(item.get("allowed_lookback_days", PUBLIC_OFFICIAL_LOOKBACK_DAYS) or 0),
            ):
                continue
            if not _is_relevant_public_news(item, query_text=query_text):
                continue
            items.append(item)
            matched_count += 1
            if matched_count >= limit:
                break
        feed_status.append(
            {
                "name": source["name"],
                "status": "ok",
                "matched_items": matched_count,
                "message": "",
                "domain": source.get("domain", ""),
                "source_country": source.get("source_country", ""),
                "source_type": source.get("source_type", "official"),
                "region_focus": source.get("region_focus", ""),
                "credibility": source.get("credibility", ""),
                "note": source.get("note", ""),
                "kind": source.get("kind", "html"),
            }
        )
    return {
        "status": "ok" if items else "empty",
        "query": query_text.strip() or settings.gdelt_query,
        "items": items,
        "feeds": feed_status,
        "lookback_days": PUBLIC_OFFICIAL_LOOKBACK_DAYS,
    }


def _public_item_sort_key(item: dict[str, Any], *, timezone_name: str) -> tuple[int, str]:
    parsed = _parse_news_datetime(str(item.get("seendate", "")), timezone_name=timezone_name)
    if parsed is None:
        return (0, str(item.get("title", "")))
    return (int(parsed.timestamp()), str(item.get("title", "")))


def _merge_public_news_items(
    settings: Settings,
    *,
    query_text: str,
    now: datetime | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    gdelt_payload = fetch_gdelt_hotspots(settings, query_text=query_text, max_records=max_records)
    rss_payload = fetch_rss_hotspots(settings, query_text=query_text, max_records=max_records, now=now)
    official_payload = fetch_official_hotspots(settings, query_text=query_text, max_records=max_records, now=now)
    local_now = _current_local_time(settings.public_digest_timezone, now=now)
    target_date = local_now.date()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in [
        *(gdelt_payload.get("items") or []),
        *(rss_payload.get("items") or []),
        *(official_payload.get("items") or []),
    ]:
        title = str(candidate.get("title", "")).strip()
        url = str(candidate.get("url", "")).strip()
        if not title or not url:
            continue
        lookback_days = int(candidate.get("allowed_lookback_days", 0) or 0)
        if candidate.get("seendate") and not _is_local_day_within_window(
            str(candidate.get("seendate", "")),
            timezone_name=settings.public_digest_timezone,
            target_date=target_date,
            lookback_days=lookback_days,
        ):
            continue
        if not _is_relevant_public_news(candidate, query_text=query_text):
            continue
        dedupe_key = url.lower()
        fallback_key = title.lower()
        if dedupe_key in seen or fallback_key in seen:
            continue
        seen.add(dedupe_key)
        seen.add(fallback_key)
        merged.append(candidate)
    merged.sort(
        key=lambda item: _public_item_sort_key(item, timezone_name=settings.public_digest_timezone),
        reverse=True,
    )
    limit = max(6, max_records or settings.gdelt_max_records)
    return {
        "status": "ok" if merged else "empty",
        "query": query_text,
        "items": merged[:limit],
        "sources": {
            "gdelt": gdelt_payload,
            "rss": rss_payload,
            "official": official_payload,
        },
    }


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


def _public_briefing_needs_schema_refresh(briefing: PublicEconomicBriefing | None) -> bool:
    if not briefing:
        return False
    public_news = briefing.raw_json.get("public_news", {}) if isinstance(briefing.raw_json, dict) else {}
    sources = public_news.get("sources", {}) if isinstance(public_news, dict) else {}
    return (briefing.template_version or "") != PUBLIC_TEMPLATE_VERSION or not isinstance(
        sources.get("official"), dict
    )


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


def get_or_build_latest_public_briefing(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> PublicEconomicBriefing | None:
    briefing = ensure_public_daily_briefing(db, settings, now=now)
    if briefing:
        return briefing
    latest = get_latest_public_briefing(db)
    local_today = _current_local_time(settings.public_digest_timezone, now=now).date().isoformat()
    if latest and latest.briefing_date == local_today and not _public_briefing_needs_schema_refresh(latest):
        return latest
    return generate_public_daily_briefing(db, settings, now=now, force=True)


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
    if existing and not force and existing.headline_count > 0 and not _public_briefing_needs_schema_refresh(existing):
        return existing

    query_text = settings.public_digest_query or settings.gdelt_query
    headlines_payload = _merge_public_news_items(
        settings,
        query_text=query_text,
        now=now,
        max_records=max(8, settings.gdelt_max_records),
    )
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
        "public_news": {**headlines_payload, "items": annotated_items, "all_items": annotated_items},
        "fred": fred_snapshots,
        "manual_filters": {"excluded_items": [], "history": []},
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
    needs_schema_refresh = _public_briefing_needs_schema_refresh(existing)
    if existing and not force and existing.headline_count > 0 and not needs_schema_refresh:
        return existing
    # If the stored public briefing is on an older schema/template, rebuild it
    # immediately so new source coverage and UI fields appear without waiting
    # for the next scheduled digest window.
    if not force and not needs_schema_refresh and not _public_digest_is_due(settings, now=now):
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
        "available_pages": _public_summary_pages(public_base_url),
        "selected_days": window_days,
        "days": window_days,
        "window": "rolling",
        "title": f"Public Economic Summary ({window_days}-day window)",
        "subtitle": "Rolling public multi-day view built from recent daily briefings.",
        "report_count": len(briefings),
        "total_headlines": total_headlines,
        "top_themes": top_themes,
        "top_domains": top_domains,
        "latest_fred": latest_fred,
        "markdown": "\n".join(markdown_lines),
        "featured_briefings": [
            serialize_public_briefing(item, public_base_url=public_base_url)
            for item in briefings[:5]
        ],
        "latest_briefing": serialize_public_briefing(briefings[0], public_base_url=public_base_url)
        if briefings
        else None,
    }


def build_named_public_summary(
    db: Session,
    *,
    window: str,
    now: datetime | None = None,
    public_base_url: str = "",
) -> dict[str, Any]:
    normalized_window = window.strip().lower()
    config = PUBLIC_SUMMARY_WINDOWS.get(normalized_window)
    if not config:
        raise ValueError("Unknown public summary window.")
    payload = build_public_briefing_summary(
        db,
        days=config["days"],
        now=now,
        public_base_url=public_base_url,
    )
    payload.update(
        {
            "window": normalized_window,
            "title": config["title"],
            "subtitle": config["subtitle"],
            "detail_path": f"/summaries/{normalized_window}",
            "share_url": _build_public_summary_url(normalized_window, public_base_url),
        }
    )
    return payload


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
