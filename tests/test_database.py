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
