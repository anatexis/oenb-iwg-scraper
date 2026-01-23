import sqlite3
import tempfile
from pathlib import Path

def test_export_to_parquet():
    """Test exporting page_content to Parquet."""
    from analysis.export_parquet import export_to_parquet
    from oenb_scraper.database import init_db

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "export.parquet"

        conn = init_db(db_path)

        conn.execute("INSERT INTO pages (id, url, status_code) VALUES (1, 'https://test.at/', 200)")
        conn.execute("""INSERT INTO page_content
                        (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
                        VALUES (1, 'Test Title', 'Test content', 'Statistik', 'de', '2026-01-22', 'v1')""")
        conn.commit()
        conn.close()

        export_to_parquet(db_path, parquet_path)

        import pandas as pd
        df = pd.read_parquet(parquet_path)
        assert len(df) == 1
        assert df.iloc[0]["title"] == "Test Title"
        assert df.iloc[0]["url"] == "https://test.at/"
