"""Tests for database cleanup script."""
import sqlite3
import tempfile
from pathlib import Path


def test_dedup_removes_session_id_duplicates():
    """Test that cleanup deduplicates pages with session IDs in URLs."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

    from oenb_scraper.database import init_db, start_crawl_run, store_page
    from analysis.cleanup_db import dedup_pages

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://test.at/", "Test/1.0")

        body = b"<html><body>Same content</body></html>"
        store_page(conn, run_id, "https://example.com/page;jsessionid=AAA?lang=DE&chart=1", "https://example.com/page", 200, "text/html", body)
        store_page(conn, run_id, "https://example.com/page;jsessionid=BBB?lang=DE&chart=1", "https://example.com/page", 200, "text/html", body)
        store_page(conn, run_id, "https://example.com/other.html", "https://example.com/other.html", 200, "text/html", body)
        conn.close()

        removed = dedup_pages(db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        conn.close()

        assert removed == 1
        assert count == 2  # one deduped + "other.html"
