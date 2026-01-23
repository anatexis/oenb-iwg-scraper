import sqlite3
import sys
import tempfile
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
