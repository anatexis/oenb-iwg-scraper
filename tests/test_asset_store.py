import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.asset_store import store_asset_document
from oenb_scraper.database import init_db, start_crawl_run, store_page


def test_store_asset_document_persists_extracted_content():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "crawler.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")
        page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/downloads/leitzins.csv",
            final_url="https://www.oenb.at/downloads/leitzins.csv",
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )

        stored_page_id = store_asset_document(
            conn,
            page_id=page_id,
            url="https://www.oenb.at/downloads/leitzins.csv",
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )

        row = conn.execute(
            """
            SELECT asset_type, extraction_status, text_content, metadata_json
            FROM asset_documents
            WHERE page_id = ?
            """,
            (page_id,),
        ).fetchone()

        assert stored_page_id == page_id
        assert row["asset_type"] == "csv"
        assert row["extraction_status"] == "text_extracted"
        assert "2026-02" in row["text_content"]
        assert json.loads(row["metadata_json"])["row_count"] == 2
