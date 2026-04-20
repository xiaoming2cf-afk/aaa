from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
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
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"


class _StubResponse:
    def __init__(self, body: str, *, status_code: int = 200, encoding: str = "utf-8", json_payload=None) -> None:
        self.status_code = status_code
        self.encoding = encoding
        self.apparent_encoding = encoding
        self.content = body.encode(encoding)
        self.text = body
        self._json_payload = json_payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_payload is None:
            raise ValueError("No JSON payload configured")
        return self._json_payload


def _rss_xml(title: str, link: str, pub_date: str, description: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Stub Feed</title>
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <pubDate>{pub_date}</pubDate>
      <description>{description}</description>
    </item>
  </channel>
</rss>
"""


def _build_stub_response(url: str, *args, **kwargs) -> _StubResponse:
    normalized = str(url or "").strip().lower()
    pub_date = "Mon, 30 Mar 2026 08:00:00 +0800"
    if "marketwatch.com" in normalized:
        return _StubResponse(
            _rss_xml(
                "United States inflation and markets outlook",
                "https://www.marketwatch.com/story/us-inflation-and-markets-20260330",
                pub_date,
                "Federal Reserve, inflation, and bond markets update.",
            )
        )
    if "investing.com" in normalized:
        return _StubResponse(
            _rss_xml(
                "Global macro trade and currency briefing",
                "https://www.investing.com/news/economy/global-macro-trade-20260330",
                pub_date,
                "Trade, FX, and central bank developments.",
            )
        )
    if "scmp.com" in normalized:
        return _StubResponse(
            _rss_xml(
                "China macro policy and trade signals",
                "https://www.scmp.com/economy/china-economy/article/1234567/china-policy-trade",
                pub_date,
                "China economy, trade, and policy discussion.",
            )
        )
    if "asia.nikkei.com" in normalized:
        return _StubResponse(
            _rss_xml(
                "Japan markets and foreign exchange watch",
                "https://asia.nikkei.com/Economy/Japan-markets-fx-watch-20260330",
                pub_date,
                "Japan markets, yen, and central bank coverage.",
            )
        )
    if "federalreserve.gov/feeds/press_all.xml" in normalized:
        return _StubResponse(
            _rss_xml(
                "Federal Reserve policy statement on inflation",
                "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260330a.htm",
                pub_date,
                "Official central bank release about inflation and rates.",
            )
        )
    if "ecb.europa.eu/rss/press.xml" in normalized:
        return _StubResponse(
            _rss_xml(
                "ECB press note on euro area inflation",
                "https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr260330.en.html",
                pub_date,
                "Euro area inflation and monetary policy guidance.",
            )
        )
    if "bankofengland.co.uk/rss/news" in normalized:
        return _StubResponse(
            _rss_xml(
                "Bank of England market update",
                "https://www.bankofengland.co.uk/news/2026/march/market-update",
                pub_date,
                "Official markets and growth update.",
            )
        )
    if "stats.gov.cn/english/pressrelease/rss.xml" in normalized:
        return _StubResponse(
            _rss_xml(
                "China NBS release on industrial production and inflation",
                "https://www.stats.gov.cn/english/PressRelease/202603/t20260330_1234567.html",
                pub_date,
                "Official China statistics release on inflation and activity.",
            )
        )
    if "home.treasury.gov/news/press-releases" in normalized:
        return _StubResponse(
            """
<html><body>
  <time datetime="2026-03-30">March 30, 2026</time>
  <div class="news-title">
    <a href="/news/press-releases/jy0001">United States Treasury markets and trade update</a>
  </div>
</body></html>
"""
        )
    if "bea.gov/news/current-releases" in normalized:
        return _StubResponse(
            """
<html><body>
  <section>
    <p>2026-03-30</p>
    <a href="/news/2026/gdp-and-inflation-release">United States GDP and inflation release</a>
  </section>
</body></html>
"""
        )
    if "english.www.gov.cn/news/latestnews/index.htm" in normalized:
        return _StubResponse(
            """
<html><body>
  <a href="//english.www.gov.cn/news/260330/30/content_1234567.htm">China State Council trade and markets update</a>
</body></html>
"""
        )
    if "safe.gov.cn/en/" in normalized:
        return _StubResponse(
            """
<html><body>
  <dl>
    <dt><a href="/en/2026/2026/1357.html" title="China foreign exchange and markets update">SAFE update</a></dt>
    <dd>2026-03-30</dd>
  </dl>
</body></html>
"""
        )
    if "bankofcanada.ca/press/press-releases" in normalized:
        return _StubResponse(
            """
<html><body>
  <span class="pressdate">March 30, 2026</span>
  <a href="https://www.bankofcanada.ca/2026/03/policy-update/">Canada policy update on inflation and growth</a>
</body></html>
"""
        )
    if "mof.go.jp/english/public_relations/whats_new/202603.html" in normalized:
        return _StubResponse(
            '<html><body><a name="a20260330"></a><h3 class="heading-lv3">March 30, 2026</h3><div class="information-more-block"><li class="information-item"><a href="/english/public_relations/whats_new/202603/item_01.html" class="information-item-inner"><p>Japan Ministry of Finance trade and markets update</p></a></li></div></body></html>'
        )
    if "api.gdeltproject.org/api/v2/doc/doc" in normalized:
        return _StubResponse(
            "{}",
            json_payload={
                "articles": [
                    {
                        "title": "Global economy and inflation snapshot",
                        "seendate": "20260330010000",
                        "domain": "example.com",
                        "sourcecountry": "US",
                        "language": "English",
                        "url": "https://example.com/gdelt/global-economy-inflation-snapshot",
                        "socialimage": "Markets and inflation update",
                    }
                ]
            },
        )
    return _StubResponse(
        _rss_xml(
            "Global macro economy and central bank update",
            "https://example.com/public-source/global-macro-update-20260330",
            pub_date,
            "Inflation, trade, markets, and policy briefing.",
        )
    )


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

    with patch("research_agent.platform_research.requests.get", side_effect=_build_stub_response):
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
