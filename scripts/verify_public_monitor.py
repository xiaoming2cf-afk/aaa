from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def configure_test_environment(temp_root: Path) -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["APP_SECRET"] = "verify-public-monitor-secret"
    os.environ["ENCRYPTION_KEY"] = "verify-public-monitor-encryption"
    os.environ["CRON_SECRET"] = "verify-public-monitor-cron"
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'platform.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str((temp_root / "storage").resolve())
    os.environ["RESEARCH_AGENT_REPORTS_DIR"] = str((temp_root / "reports").resolve())
    os.environ["ASSET_STORAGE_BACKEND"] = "local"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ["PUBLIC_DIGEST_ENABLED"] = "true"
    os.environ["PUBLIC_DIGEST_TIMEZONE"] = "Asia/Shanghai"
    os.environ["PUBLIC_DIGEST_LOCAL_TIME"] = "00:00"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_public_items() -> list[dict[str, object]]:
    return [
        {
            "title": "Fed signals slower path for rate cuts",
            "url": "https://example.com/fed-rate-path",
            "domain": "example.com",
            "source_country": "US",
            "source_name": "Example Macro Desk",
            "excerpt": "The Federal Reserve indicated a slower pace of easing amid sticky inflation.",
            "themes": ["monetary policy", "inflation"],
            "primary_theme": "monetary policy",
            "seendate": "2026-03-30T08:30:00+08:00",
        },
        {
            "title": "Oil rises as supply risks return to focus",
            "url": "https://energy.example.org/oil-supply-risks",
            "domain": "energy.example.org",
            "source_country": "GB",
            "source_name": "Energy Example",
            "excerpt": "Crude prices moved higher after renewed concern around physical supply constraints.",
            "themes": ["energy", "markets"],
            "primary_theme": "energy",
            "seendate": "2026-03-30T07:45:00+08:00",
        },
        {
            "title": "Exports rebound as regional demand stabilizes",
            "url": "https://trade.example.net/exports-rebound",
            "domain": "trade.example.net",
            "source_country": "SG",
            "source_name": "Trade Example",
            "excerpt": "Regional trade data showed a recovery in manufactured exports during March.",
            "themes": ["trade", "growth"],
            "primary_theme": "trade",
            "seendate": "2026-03-30T06:15:00+08:00",
        },
    ]


def insert_public_briefing() -> str:
    from research_agent.db import session_scope
    from research_agent.entities import PublicEconomicBriefing

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    items = build_public_items()
    with session_scope() as db:
        briefing = PublicEconomicBriefing(
            slug=f"global-economic-daily-{today}",
            title=f"Global Economic Daily | {today}",
            briefing_date=today,
            timezone_name="Asia/Shanghai",
            summary_markdown="# Global Economic Daily\n\n- Fed signals slower path for rate cuts\n- Oil rises as supply risks return to focus\n- Exports rebound as regional demand stabilizes",
            query_text="global macro headlines",
            template_version="daily-macro-v1",
            headline_count=len(items),
            items_json=items,
            raw_json={
                "public_news": {
                    "items": items,
                    "all_items": items,
                    "sources": {
                        "rss": {
                            "feeds": [
                                {"name": "Example Macro Desk", "status": "ok", "matched_items": 1, "message": ""},
                                {"name": "Energy Example", "status": "ok", "matched_items": 1, "message": ""},
                                {"name": "Trade Example", "status": "ok", "matched_items": 1, "message": ""},
                            ]
                        },
                        "gdelt": {
                            "status": "ok",
                            "items": [],
                        },
                    },
                },
                "fred": [],
                "manual_filters": {"excluded_items": [], "history": []},
            },
        )
        db.add(briefing)
        db.flush()
        return briefing.slug


def assert_overview_value(panel: dict, label: str, expected: str) -> None:
    row = next((item for item in panel.get("overview", []) if item.get("label") == label), None)
    if not row:
        raise AssertionError(f"Missing overview row: {label}")
    if str(row.get("value")) != expected:
        raise AssertionError(f"Unexpected overview value for {label}: {row.get('value')} != {expected}")


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="erp-public-monitor-verify-"))
    configure_test_environment(temp_root)

    from research_agent.webapp import create_app

    client = TestClient(create_app())
    try:
        register = client.post(
            "/api/auth/register",
            json={"full_name": "Public Reviewer", "email": "reviewer@example.com", "password": "StrongPass123!"},
        )
        register.raise_for_status()
        token = register.json()["session_token"]
        slug = insert_public_briefing()

        latest = client.get("/api/public/briefings/latest")
        latest.raise_for_status()
        latest_payload = latest.json()["briefing"]
        if latest_payload["slug"] != slug:
            raise AssertionError("Latest public briefing did not return the injected test briefing")
        if len(latest_payload.get("review_items", [])) != 3:
            raise AssertionError("Initial public review queue should expose all three items")
        if latest_payload.get("excluded_items"):
            raise AssertionError("Initial excluded list should be empty")
        if len(latest_payload.get("source_panel", {}).get("feeds", [])) != 3:
            raise AssertionError("Source panel did not return the expected feed rows")
        assert_overview_value(latest_payload["source_panel"], "Visible headlines", "3")
        assert_overview_value(latest_payload["source_panel"], "Filtered headlines", "0")

        public_page = client.get("/public-monitor")
        public_page.raise_for_status()
        if "Source Panel" not in public_page.text:
            raise AssertionError("Public monitor page is missing the source panel section")
        if "Manual Review Queue" not in public_page.text:
            raise AssertionError("Public monitor page is missing the manual review section")

        exclude = client.post(
            f"/api/public/briefings/{slug}/moderation",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json={"action": "exclude", "url": "https://energy.example.org/oil-supply-risks", "title": ""},
        )
        exclude.raise_for_status()
        excluded_payload = exclude.json()["briefing"]
        if excluded_payload["headline_count"] != 2:
            raise AssertionError("Headline count did not update after exclusion")
        if len(excluded_payload.get("review_items", [])) != 2:
            raise AssertionError("Review queue size did not shrink after exclusion")
        if len(excluded_payload.get("excluded_items", [])) != 1:
            raise AssertionError("Excluded item list did not grow after exclusion")
        if excluded_payload.get("moderation", {}).get("excluded_count") != 1:
            raise AssertionError("Moderation summary did not track the excluded count")
        assert_overview_value(excluded_payload["source_panel"], "Visible headlines", "2")
        assert_overview_value(excluded_payload["source_panel"], "Filtered headlines", "1")

        persisted = client.get(f"/api/public/briefings/{slug}")
        persisted.raise_for_status()
        persisted_payload = persisted.json()["briefing"]
        if any(item.get("url") == "https://energy.example.org/oil-supply-risks" for item in persisted_payload.get("items", [])):
            raise AssertionError("Excluded headline remained visible in the briefing payload")

        restore = client.post(
            f"/api/public/briefings/{slug}/moderation",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json={"action": "restore", "url": "https://energy.example.org/oil-supply-risks", "title": ""},
        )
        restore.raise_for_status()
        restored_payload = restore.json()["briefing"]
        if restored_payload["headline_count"] != 3:
            raise AssertionError("Headline count did not restore after re-adding the filtered item")
        if len(restored_payload.get("review_items", [])) != 3:
            raise AssertionError("Review queue did not restore to the full set")
        if restored_payload.get("excluded_items"):
            raise AssertionError("Excluded list should be empty after restore")
        if restored_payload.get("moderation", {}).get("last_action_at") is None:
            raise AssertionError("Moderation summary should record the last action timestamp")
        assert_overview_value(restored_payload["source_panel"], "Visible headlines", "3")
        assert_overview_value(restored_payload["source_panel"], "Filtered headlines", "0")

        print("Public monitor verification checks passed.")
        print(f"Briefing slug: {slug}")
        print("Moderation actions verified: exclude, restore")
    finally:
        client.close()


if __name__ == "__main__":
    main()
