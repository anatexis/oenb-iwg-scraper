import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

def test_sqlite_pipeline_stores_page():
    """Test that SQLitePipeline stores response body."""
    from oenb_scraper.pipelines import SQLitePipeline
    from oenb_scraper.items import DownloadItem

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"

        pipeline = SQLitePipeline(db_path)

        spider = MagicMock()
        spider.name = "oenb"
        spider.start_urls = ["https://www.oenb.at/"]
        spider.settings = MagicMock()
        spider.settings.get = MagicMock(return_value="TestBot/1.0")

        pipeline.open_spider(spider)

        item = DownloadItem()
        item["url"] = "https://www.oenb.at/test.html"
        item["type"] = "webpage_with_data"

        response = MagicMock()
        response.url = "https://www.oenb.at/test.html"
        response.status = 200
        response.headers = {b"Content-Type": [b"text/html"]}
        response.body = b"<html><body>Test</body></html>"

        pipeline.process_item(item, spider, response=response)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT url, status_code FROM pages").fetchone()
        assert row[0] == "https://www.oenb.at/test.html"
        assert row[1] == 200
        conn.close()


def test_sqlite_pipeline_normalizes_session_ids():
    """Test that SQLitePipeline deduplicates URLs with different session IDs."""
    from oenb_scraper.pipelines import SQLitePipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        pipeline = SQLitePipeline(db_path)

        spider = MagicMock()
        spider.name = "oenb"
        spider.start_urls = ["https://www.oenb.at/"]
        spider.settings = MagicMock()
        spider.settings.get = MagicMock(return_value="TestBot/1.0")
        pipeline.open_spider(spider)

        # Simulate two responses with different session IDs but same logical URL
        for session_id in ["ABC123", "DEF456"]:
            response = MagicMock()
            response.url = f"https://www.oenb.at/isawebstat/createChart;jsessionid={session_id}?lang=DE&chart=10.4.1"
            response.status = 200
            response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
            response.body = b"<html><body>Chart data</body></html>"

            request = MagicMock()
            request.url = response.url

            pipeline.response_received(response, request, spider)

        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        assert count == 1, f"Expected 1 page but got {count} (session ID dedup failed)"

        url = conn.execute("SELECT url FROM pages").fetchone()[0]
        assert "jsessionid" not in url, f"Session ID not removed from stored URL: {url}"
        conn.close()


def test_sqlite_pipeline_skips_unchanged_pages():
    """Test that SQLitePipeline skips pages with unchanged body_hash."""
    from oenb_scraper.pipelines import SQLitePipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        pipeline = SQLitePipeline(db_path)

        spider = MagicMock()
        spider.name = "oenb"
        spider.start_urls = ["https://www.oenb.at/"]
        spider.settings = MagicMock()
        spider.settings.get = MagicMock(return_value="TestBot/1.0")
        pipeline.open_spider(spider)

        url = "https://www.oenb.at/test.html"
        body = b"<html><body>Same content</body></html>"

        # First request: should store
        response1 = MagicMock()
        response1.url = url
        response1.status = 200
        response1.headers = {b"Content-Type": b"text/html"}
        response1.body = body
        request1 = MagicMock()
        request1.url = url
        pipeline.response_received(response1, request1, spider)

        # Record the fetched_at from first insert
        conn = sqlite3.connect(db_path)
        first_fetched_at = conn.execute("SELECT fetched_at FROM pages WHERE url = ?", (url,)).fetchone()[0]
        conn.close()

        # Small delay to ensure fetched_at timestamp changes
        time.sleep(0.05)

        # Simulate a second crawl run by clearing stored_urls
        # (as if spider restarted) but keeping the DB
        pipeline.stored_urls.clear()

        # Second request with same body: should update fetched_at but not create duplicate
        response2 = MagicMock()
        response2.url = url
        response2.status = 200
        response2.headers = {b"Content-Type": b"text/html"}
        response2.body = body
        request2 = MagicMock()
        request2.url = url
        pipeline.response_received(response2, request2, spider)

        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        assert count == 1, f"Expected 1 page but got {count} (should upsert, not duplicate)"

        second_fetched_at = conn.execute("SELECT fetched_at FROM pages WHERE url = ?", (url,)).fetchone()[0]
        assert second_fetched_at > first_fetched_at, (
            f"fetched_at should be updated on re-crawl: first={first_fetched_at}, second={second_fetched_at}"
        )
        conn.close()
