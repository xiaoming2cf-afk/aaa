from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-public-sources-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-public-sources-encryption"
    os.environ["CRON_SECRET"] = "verify-public-sources-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ["PUBLIC_DIGEST_ENABLED"] = "true"
    os.environ["PUBLIC_DIGEST_TIMEZONE"] = "Asia/Shanghai"
    os.environ["PUBLIC_DIGEST_LOCAL_TIME"] = "00:00"
    os.environ["PUBLIC_DIGEST_QUERY"] = "global macro economy inflation markets trade foreign exchange china united states central bank"


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-public-sources-verify-"))
    configure_test_environment(temp_root)

    from research_agent.config import get_settings
    from research_agent.platform_research import (
        PUBLIC_OFFICIAL_PAGE_SOURCES,
        PUBLIC_OFFICIAL_RSS_FEEDS,
        PUBLIC_SOURCE_DIRECTORY,
        _merge_public_news_items,
        fetch_official_hotspots,
        fetch_rss_hotspots,
    )

    settings = get_settings()
    pinned_now = datetime(2026, 3, 30, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    query_text = settings.public_digest_query

    official_payload = fetch_official_hotspots(settings, query_text=query_text, now=pinned_now, max_records=12)
    media_payload = fetch_rss_hotspots(settings, query_text=query_text, now=pinned_now, max_records=12)
    merged_payload = _merge_public_news_items(settings, query_text=query_text, now=pinned_now, max_records=20)

    official_items = official_payload.get("items", [])
    if not official_items:
        raise AssertionError("Official-source fetch returned no items for the pinned verification window.")
    official_countries = {str(item.get("source_country", "")).strip().upper() for item in official_items}
    if "CN" not in official_countries:
        raise AssertionError("Official-source fetch did not return any China official items.")
    if "US" not in official_countries:
        raise AssertionError("Official-source fetch did not return any United States official items.")
    if "JP" not in official_countries:
        raise AssertionError("Official-source fetch did not return any Japan official items.")

    official_status_rows = official_payload.get("feeds", [])
    expected_official_sources = len(PUBLIC_OFFICIAL_RSS_FEEDS) + len(PUBLIC_OFFICIAL_PAGE_SOURCES)
    if len(official_status_rows) != expected_official_sources:
        raise AssertionError(
            f"Official-source status rows mismatch: {len(official_status_rows)} != {expected_official_sources}"
        )

    media_items = media_payload.get("items", [])
    if not media_items:
        raise AssertionError("Media-source fetch returned no items for the pinned verification window.")

    merged_items = merged_payload.get("items", [])
    if not merged_items:
        raise AssertionError("Merged public-news payload returned no items.")
    if not any(str(item.get("source_type", "")).strip() == "official" for item in merged_items):
        raise AssertionError("Merged public-news payload contains no official-source items.")
    if not any(str(item.get("source_type", "")).strip() == "media" for item in merged_items):
        raise AssertionError("Merged public-news payload contains no media-source items.")

    configured_official_count = sum(
        1 for source in PUBLIC_SOURCE_DIRECTORY if str(source.get("source_type", "")).strip() == "official"
    )
    if configured_official_count < 6:
        raise AssertionError("Configured official-source directory is unexpectedly small.")

    print("Public official-source verification checks passed.")
    print(f"Official items: {len(official_items)}")
    print(f"Media items: {len(media_items)}")
    print(f"Merged items: {len(merged_items)}")
    print(f"Official countries: {sorted(country for country in official_countries if country)}")


if __name__ == "__main__":
    main()
