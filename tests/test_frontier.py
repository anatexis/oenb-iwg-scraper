import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db
from oenb_scraper.frontier import get_due_frontier_urls, upsert_frontier_url


def test_frontier_returns_due_urls(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    upsert_frontier_url(
        conn,
        "https://www.oenb.at/test.html",
        priority=50,
        revisit_after="2026-03-18T10:00:00Z",
    )

    rows = get_due_frontier_urls(conn, now="2026-03-18T10:00:00Z", limit=10)

    assert rows[0]["url"] == "https://www.oenb.at/test.html"
    assert rows[0]["priority"] == 50


def test_frontier_upsert_updates_referring_count_and_last_seen(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    upsert_frontier_url(
        conn,
        "https://www.oenb.at/statistik.html",
        priority=10,
        seen_at="2026-03-18T09:00:00Z",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/statistik.html",
        priority=30,
        seen_at="2026-03-18T10:00:00Z",
    )

    rows = get_due_frontier_urls(conn, now="2026-03-18T10:00:00Z", limit=10)

    assert rows[0]["referring_url_count"] == 2
    assert rows[0]["last_seen_at"] == "2026-03-18T10:00:00Z"
    assert rows[0]["priority"] == 30


def test_frontier_can_filter_due_urls_by_resource_kind(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        priority=80,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/en/Statistics/Standardized-Tables.html",
        priority=70,
        resource_kind="page_document",
        revisit_after="2026-03-18T10:00:00Z",
    )

    rows = get_due_frontier_urls(
        conn,
        now="2026-03-18T10:00:00Z",
        limit=10,
        resource_kinds=["isaweb_entry"],
    )

    assert [row["url"] for row in rows] == [
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
    ]


def test_frontier_upsert_preserves_higher_priority_and_resource_kind(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",
        priority=90,
        resource_kind="release_event",
        revisit_after="2026-03-18T06:00:00Z",
        seen_at="2026-03-18T05:00:00Z",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",
        priority=60,
        resource_kind="html_table",
        revisit_after="2026-03-19T06:00:00Z",
        seen_at="2026-03-18T06:00:00Z",
    )

    row = conn.execute(
        """
        SELECT priority, resource_kind, revisit_after, referring_url_count
        FROM frontier_urls
        WHERE url = ?
        """,
        ("https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",),
    ).fetchone()

    assert row["priority"] == 90
    assert row["resource_kind"] == "release_event"
    assert row["revisit_after"] == "2026-03-18T06:00:00Z"
    assert row["referring_url_count"] == 2
