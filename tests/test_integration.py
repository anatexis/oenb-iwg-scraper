"""End-to-end integration test for RAG extraction pipeline."""
import sqlite3
import tempfile
from pathlib import Path

def test_full_pipeline():
    """Test: init DB → store page → extract text → export parquet."""
    from oenb_scraper.database import init_db, start_crawl_run, store_page, finish_crawl_run
    from analysis.extract_text import run_extraction
    from analysis.export_parquet import export_to_parquet

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "export.parquet"

        # 1. Init and store
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "Test/1.0")

        html = b"""<html>
        <head><title>OeNB Statistik</title></head>
        <body>
            <nav>Menu</nav>
            <main><h1>Inflation</h1><p>Die Inflation betrug 3.5%.</p></main>
        </body>
        </html>"""

        store_page(conn, run_id,
                   "https://www.oenb.at/Statistik/inflation.html",
                   "https://www.oenb.at/Statistik/inflation.html",
                   200, "text/html", html)

        finish_crawl_run(conn, run_id)
        conn.close()

        # 2. Extract
        count = run_extraction(db_path, "v1")
        assert count == 1

        # 3. Export
        count = export_to_parquet(db_path, parquet_path)
        assert count == 1

        # 4. Verify
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        assert "Inflation" in df.iloc[0]["text_content"]
        assert df.iloc[0]["page_section"] == "Statistik"
