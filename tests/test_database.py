# tests/test_database.py
import sqlite3
import tempfile
from pathlib import Path


def test_create_tables():
    """Test that init_db creates all required tables."""
    from oenb_scraper.database import init_db

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "crawl_runs" in tables
        assert "pages" in tables
        assert "page_bodies" in tables
        assert "page_content" in tables


def test_start_and_finish_crawl_run():
    """Test crawl run lifecycle."""
    from oenb_scraper.database import init_db, start_crawl_run, finish_crawl_run

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")
        assert run_id == 1

        row = conn.execute("SELECT seed_url, user_agent FROM crawl_runs WHERE id=?", (run_id,)).fetchone()
        assert row[0] == "https://www.oenb.at/"
        assert row[1] == "TestBot/1.0"

        finish_crawl_run(conn, run_id)

        row = conn.execute("SELECT finished_at FROM crawl_runs WHERE id=?", (run_id,)).fetchone()
        assert row[0] is not None

        conn.close()
