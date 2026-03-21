import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

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


def test_sqlite_pipeline_stores_resource_links():
    """Test that SQLitePipeline persists found_on_page -> resource link relations."""
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

        item = {
            "url": "https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11",
            "found_on_page": "https://www.oenb.at/Statistik/start.html",
            "title": "Leitzins",
            "section_heading": "Zinssätze",
            "resource_kind": "isaweb_entry",
        }

        pipeline.process_item(item, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT source_url, normalized_target_url, link_text, section_heading, resource_kind, embed_type
            FROM resource_links
            """
        ).fetchone()
        conn.close()

        assert row[0] == "https://www.oenb.at/Statistik/start.html"
        assert row[1] == "https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11"
        assert row[2] == "Leitzins"
        assert row[3] == "Zinssätze"
        assert row[4] == "isaweb_entry"
        assert row[5] == "item"


def test_sqlite_pipeline_materializes_isaweb_dataset_from_item_url():
    """Test that SQLitePipeline stores canonical ISAweb datasets from crawl items."""
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

        item = {
            "url": (
                "https://www.oenb.at/isawebstat/dynabfrage/showResult"
                "?hierid=11&lang=EN&pos=VDBFKBSC217000&dval1=AT&freq=M"
            ),
            "found_on_page": "https://www.oenb.at/en/Statistics/Standardized-Tables.html",
            "title": "Base rates",
            "section_heading": "Interest rates",
            "resource_kind": "isaweb_entry",
            "language": "en",
        }

        pipeline.process_item(item, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT hierid, lang, freq, title, source_url
            FROM isaweb_datasets
            """
        ).fetchone()
        dimension_rows = conn.execute(
            """
            SELECT dimension_key, dimension_value
            FROM isaweb_dimensions
            ORDER BY dimension_key, dimension_value
            """
        ).fetchall()
        conn.close()

        assert row == (
            11,
            "EN",
            "M",
            "Base rates",
            "https://www.oenb.at/isawebstat/dynabfrage/showResult?dval1=AT&freq=M&hierid=11&lang=EN&pos=VDBFKBSC217000",
        )
        assert dimension_rows == [
            ("dval1", "AT"),
            ("pos", "VDBFKBSC217000"),
        ]


def test_sqlite_pipeline_materializes_isaweb_page_context_from_report_item():
    """Test that SQLitePipeline stores page->ISAweb hierarchy context for report links."""
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

        content_response = MagicMock()
        content_response.url = "https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1"
        content_response.status = 200
        content_response.headers = {b"Content-Type": b"application/xml; charset=utf-8"}
        content_response.body = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <content>
          <header>
            <prepared>2026-03-19T10:23:04Z</prepared>
          </header>
          <content>
            <element id=\"3\" parent=\"0\"><text lang=\"EN\">Financial institutions</text></element>
            <element id=\"31\" parent=\"3\"><text lang=\"EN\">Banks</text></element>
            <element id=\"321\" parent=\"31\"><text lang=\"EN\">Number of Banks</text></element>
          </content>
        </content>
        """

        content_request = MagicMock()
        content_request.url = content_response.url
        pipeline.response_received(content_response, content_request, spider)

        item = {
            "url": "https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            "found_on_page": "https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html",
            "title": "Number of Banks",
            "section_heading": "Financial institutions",
            "resource_kind": "isaweb_entry",
            "language": "en",
        }

        pipeline.process_item(item, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT source_url, hierid, lang, section_id, family_id, family_label
            FROM isaweb_page_contexts
            """
        ).fetchone()
        frontier_row = conn.execute(
            """
            SELECT resource_kind
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isadataservice/content?hierid=321&lang=EN",),
        ).fetchone()
        conn.close()

        assert row["source_url"] == "https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html"
        assert row["hierid"] == 321
        assert row["lang"] == "EN"
        assert row["section_id"] == 3
        assert row["family_id"] == 31
        assert row["family_label"] == "Banks"
        assert frontier_row["resource_kind"] == "isaweb_content"


def test_sqlite_pipeline_updates_frontier_for_pages_and_resources():
    """Test that SQLitePipeline persists crawled pages and discovered resources into the frontier."""
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

        page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables.html"

        response = MagicMock()
        response.url = page_url
        response.status = 200
        response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
        response.body = b"<html><body>Statistics</body></html>"

        request = MagicMock()
        request.url = page_url

        pipeline.response_received(response, request, spider)
        pipeline.process_item(
            {
                "url": "https://www.oenb.at/downloads/leitzins.csv",
                "found_on_page": page_url,
                "title": "Leitzins CSV",
                "resource_kind": "asset_document",
                "language": "en",
            },
            spider,
        )
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT url, resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            ORDER BY url
            """
        ).fetchall()
        conn.close()

        rows_by_url = {row["url"]: row for row in rows}

        assert rows_by_url[page_url]["resource_kind"] == "page_document"
        assert rows_by_url[page_url]["last_crawled_at"] is not None
        assert rows_by_url[page_url]["revisit_after"] is not None

        assert rows_by_url["https://www.oenb.at/downloads/leitzins.csv"]["resource_kind"] == "asset_document"
        assert rows_by_url["https://www.oenb.at/downloads/leitzins.csv"]["last_crawled_at"] is None


def test_sqlite_pipeline_materializes_asset_document_from_csv_response():
    """Test that SQLitePipeline stores extracted asset content and version rows."""
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

        response = MagicMock()
        response.url = "https://www.oenb.at/downloads/leitzins.csv"
        response.status = 200
        response.headers = {b"Content-Type": b"text/csv; charset=utf-8"}
        response.body = b"period;value\n2026-01;2.50\n2026-02;2.75\n"

        request = MagicMock()
        request.url = response.url

        pipeline.response_received(response, request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        asset_row = conn.execute(
            """
            SELECT asset_type, extraction_status, text_content
            FROM asset_documents
            """
        ).fetchone()
        version_count = conn.execute("SELECT COUNT(*) AS count FROM resource_versions").fetchone()["count"]
        frontier_row = conn.execute(
            """
            SELECT resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/downloads/leitzins.csv",),
        ).fetchone()
        conn.close()

        assert asset_row["asset_type"] == "csv"
        assert asset_row["extraction_status"] == "text_extracted"
        assert "2026-02" in asset_row["text_content"]
        assert version_count == 1
        assert frontier_row["resource_kind"] == "asset_document"
        assert frontier_row["last_crawled_at"] is not None
        assert frontier_row["revisit_after"] is not None


def test_sqlite_pipeline_materializes_isaweb_observations_from_xml_response():
    """Test that SQLitePipeline stores ISAweb observation data from XML webservice responses."""
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

        response = MagicMock()
        response.url = "https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBKISDANZTAU&pos=VDBKISDANZTEU&freq=H&starttime=200501"
        response.status = 200
        response.headers = {b"Content-Type": b"application/xml; charset=utf-8"}
        response.body = b"""
        <OeNBData>
          <data>
            <dataSet pos=\"VDBKISDANZTAU\" posTitle=\"number of foreign subsidiaries\" attr1=\"AT\" attr2=\"BS0100510\" attr3=\"Z5\" attr4=\"Z0Z\" attr1Dim=\"PRODUZENT\" attr2Dim=\"BANKENSEKTOR\" attr3Dim=\"REGION\" attr4Dim=\"WAEHRUNG\" freq=\"H\" unitMult=\"0\" unitText=\"in ones\">
              <values>
                <obs value=\"90.0\" periode=\"2005-B1\"/>
                <obs value=\"90.0\" periode=\"2005-B2\"/>
              </values>
            </dataSet>
            <dataSet pos=\"VDBKISDANZTEU\" posTitle=\"number of foreign subsidiaries hereof in the EU\" attr1=\"AT\" attr2=\"BS0100510\" attr3=\"Z5\" attr4=\"Z0Z\" attr1Dim=\"PRODUZENT\" attr2Dim=\"BANKENSEKTOR\" attr3Dim=\"REGION\" attr4Dim=\"WAEHRUNG\" freq=\"H\" unitMult=\"0\" unitText=\"in ones\">
              <values>
                <obs value=\"45.0\" periode=\"2005-B1\"/>
              </values>
            </dataSet>
          </data>
        </OeNBData>
        """

        request = MagicMock()
        request.url = response.url

        pipeline.response_received(response, request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        dataset_count = conn.execute("SELECT COUNT(*) AS count FROM isaweb_datasets").fetchone()["count"]
        observation_count = conn.execute("SELECT COUNT(*) AS count FROM isaweb_observations").fetchone()["count"]
        frontier_row = conn.execute(
            """
            SELECT resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isadataservice/data?freq=H&hierid=321&lang=EN&pos=VDBKISDANZTAU&pos=VDBKISDANZTEU&starttime=200501",),
        ).fetchone()
        conn.close()

        assert dataset_count == 2
        assert observation_count == 3
        assert frontier_row["resource_kind"] == "isaweb_dataset"
        assert frontier_row["last_crawled_at"] is not None
        assert frontier_row["revisit_after"] is not None


def test_sqlite_pipeline_materializes_isaweb_metadata_from_meta_response():
    """Test that SQLitePipeline stores ISAweb metadata and release events from meta XML responses."""
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

        response = MagicMock()
        response.url = "https://www.oenb.at/isadataservice/meta?lang=EN&hierid=11&pos=VDBFKBSC217000"
        response.status = 200
        response.headers = {b"Content-Type": b"application/xml; charset=utf-8"}
        response.body = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <metainfo>
          <header>
            <prepared>2026-03-19T10:12:54Z</prepared>
            <sender id=\"AT2\">
              <name>Oesterreichische Nationalbank</name>
            </sender>
            <last_update>2026-03-19T10:12:54Z</last_update>
          </header>
          <meta>
            <title>Loans to euro area residents - total</title>
            <region>-</region>
            <unit>Euro</unit>
            <comment>Collected within the framework of the balance sheet report to the ECB loans to euro area residents total.</comment>
            <classification>European System of National Accounts</classification>
            <breaks>-</breaks>
            <frequency>month</frequency>
            <data_available>
              <data>Jan. 98 - Feb. 26</data>
              <data>1998 - 2025</data>
            </data_available>
            <last_update>2026-03-13 08:02:12</last_update>
            <source>OeNB</source>
            <lag>-</lag>
            <releases>
              <release><release_date>Week 16/2026</release_date><reference>March 2026</reference><revision></revision></release>
              <release><release_date>Week 20/2026</release_date><reference>April 2026</reference><revision></revision></release>
            </releases>
          </meta>
        </metainfo>
        """

        request = MagicMock()
        request.url = response.url

        pipeline.response_received(response, request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        metadata_row = conn.execute(
            """
            SELECT hierid, lang, pos, title, unit, frequency
            FROM isaweb_metadata
            """
        ).fetchone()
        release_count = conn.execute("SELECT COUNT(*) AS count FROM release_events").fetchone()["count"]
        frontier_row = conn.execute(
            """
            SELECT resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isadataservice/meta?hierid=11&lang=EN&pos=VDBFKBSC217000",),
        ).fetchone()
        conn.close()

        assert metadata_row["hierid"] == 11
        assert metadata_row["lang"] == "EN"
        assert metadata_row["pos"] == "VDBFKBSC217000"
        assert metadata_row["title"] == "Loans to euro area residents - total"
        assert metadata_row["unit"] == "Euro"
        assert metadata_row["frequency"] == "month"
        assert release_count == 2
        assert frontier_row["resource_kind"] == "dataset_metadata"
        assert frontier_row["last_crawled_at"] is not None
        assert frontier_row["revisit_after"] is not None


def test_sqlite_pipeline_materializes_isaweb_content_from_content_response():
    """Test that SQLitePipeline stores ISAweb hierarchy content from content XML responses."""
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

        response = MagicMock()
        response.url = "https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1"
        response.status = 200
        response.headers = {b"Content-Type": b"application/xml; charset=utf-8"}
        response.body = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <content>
          <header>
            <prepared>2026-03-19T10:23:04Z</prepared>
          </header>
          <content>
            <element id=\"3\" parent=\"0\"><text lang=\"EN\">Financial institutions</text></element>
            <element id=\"31\" parent=\"3\"><text lang=\"EN\">Banks</text></element>
            <element id=\"321\" parent=\"31\"><text lang=\"EN\">Number of Banks</text></element>
          </content>
        </content>
        """

        request = MagicMock()
        request.url = response.url

        pipeline.response_received(response, request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT node_id, section_id, family_id
            FROM isaweb_content_nodes
            WHERE node_id = 321 AND lang = 'EN'
            """
        ).fetchone()
        frontier_row = conn.execute(
            """
            SELECT last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1",),
        ).fetchone()
        conn.close()

        assert row["node_id"] == 321
        assert row["section_id"] == 3
        assert row["family_id"] == 31


def test_sqlite_pipeline_materializes_isaweb_dataset_from_report_html_response():
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

        html = b"""
        <html lang="en">
          <head><title>DATA - SDDS-CGD, Guarantees&lt;sup&gt;1&lt;/sup&gt;</title></head>
          <body>
            <input type="hidden" id="metaDataUrl" data-url="/isawebstat/showMetadatenStAbfrage?lang=EN&amp;report=14.8">
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th><span>Q1 25</span></th>
                  <th><span>Q2 25</span></th>
                </tr>
                <tr>
                  <th><span></span></th>
                  <th colspan="2"><span>EUR million</span></th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row"><span>Government Liabilities (Guarantees)</span></th>
                  <td><span>68,804</span></td>
                  <td><span>69,548</span></td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td class="footer quelle" colspan="3">
                    <span>Source: <a href="http://www.bmf.gv.at">Federal Ministry of Finance</a>.</span>
                  </td>
                </tr>
                <tr>
                  <td class="footer footnote" colspan="3">
                    <sup>1</sup> Government liabilities explanatory note.
                  </td>
                </tr>
              </tfoot>
            </table>
          </body>
        </html>
        """

        response = MagicMock()
        response.url = "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8"
        response.status = 200
        response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
        response.body = html

        request = MagicMock()
        request.url = response.url

        pipeline.response_received(response, request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        dataset = conn.execute(
            "SELECT hierid, lang, freq, title, source_url FROM isaweb_datasets"
        ).fetchone()
        metadata = conn.execute(
            "SELECT pos, title, unit, comment, source FROM isaweb_metadata"
        ).fetchone()
        observations = conn.execute(
            "SELECT period, value, unit, series_label FROM isaweb_observations ORDER BY period"
        ).fetchall()
        frontier_row = conn.execute(
            """
            SELECT resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",),
        ).fetchone()
        conn.close()

        assert dataset["hierid"] == 14
        assert dataset["lang"] == "EN"
        assert dataset["freq"] == "Q"
        assert dataset["title"] == "SDDS-CGD, Guarantees<sup>1</sup>"
        assert dataset["source_url"] == "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8"

        assert metadata["pos"] == "REPORT:14.8"
        assert metadata["title"] == "SDDS-CGD, Guarantees<sup>1</sup>"
        assert metadata["unit"] == "EUR million"
        assert metadata["comment"] == "Government liabilities explanatory note."
        assert metadata["source"] == "Federal Ministry of Finance"

        assert [(row["period"], row["value"], row["unit"], row["series_label"]) for row in observations] == [
            ("Q1 25", "68,804", "EUR million", "Government Liabilities (Guarantees)"),
            ("Q2 25", "69,548", "EUR million", "Government Liabilities (Guarantees)"),
        ]
        assert frontier_row["resource_kind"] == "isaweb_dataset"
        assert frontier_row["last_crawled_at"] is not None
        assert frontier_row["revisit_after"] is not None


def test_sqlite_pipeline_materializes_release_events_from_release_html_response():
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

        report_response = MagicMock()
        report_response.url = "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6"
        report_response.status = 200
        report_response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
        report_response.body = b"""
        <html lang="en">
          <head><title>DATA - Residential property price index (RPPI)</title></head>
          <body>
            <table class="popup resultTable" id="dataTable">
              <caption>
                <span class="title">Residential property price index (RPPI)</span>
              </caption>
              <thead>
                <tr>
                  <th></th>
                  <th><span>2024</span></th>
                  <th><span>2025</span></th>
                </tr>
                <tr>
                  <th><span></span></th>
                  <th colspan="2"><span>Index</span></th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row"><span>Austria - Residential Property Price Index 2000=100 hedonic regr model</span></th>
                  <td><span>257.8</span></td>
                  <td><span>266.9</span></td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td class="footer quelle" colspan="3">
                    <span>Source: <a href="https://www.oenb.at">OeNB</a>.</span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </body>
        </html>
        """
        report_request = MagicMock()
        report_request.url = report_response.url
        pipeline.response_received(report_response, report_request, spider)

        release_response = MagicMock()
        release_response.url = "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6"
        release_response.status = 200
        release_response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
        release_response.body = b"""
        <html lang="en">
          <head><title>DATA - Publication schedule - Residential property price index (RPPI)</title></head>
          <body>
            <table class="popup resultTable" id="releasetable">
              <caption>
                <span class="title">Residential property price index (RPPI)</span>
              </caption>
              <thead>
                <tr>
                  <th>release strategy</th>
                  <th>release date</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="txt1 alignLeft"></td>
                  <td class="txt3 alignLeft"><b>as available</b><br/></td>
                </tr>
                <tr>
                  <td class="txt1 alignLeft">final</td>
                  <td class="txt3 alignLeft"><b>19.03.2026</b><br/>February 2026 provisional</td>
                </tr>
              </tbody>
            </table>
          </body>
        </html>
        """
        release_request = MagicMock()
        release_request.url = release_response.url
        pipeline.response_received(release_response, release_request, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        metadata = conn.execute(
            """
            SELECT pos, title, source
            FROM isaweb_metadata
            WHERE pos = 'REPORT:6.6'
            """
        ).fetchone()
        releases = conn.execute(
            """
            SELECT release_date_text, reference_text, revision_text
            FROM release_events
            WHERE pos = 'REPORT:6.6'
            ORDER BY id
            """
        ).fetchall()
        frontier_row = conn.execute(
            """
            SELECT resource_kind, last_crawled_at, revisit_after
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",),
        ).fetchone()
        conn.close()

        assert metadata["pos"] == "REPORT:6.6"
        assert metadata["title"] == "Residential property price index (RPPI)"
        assert metadata["source"] == "OeNB"
        assert [(row["release_date_text"], row["reference_text"], row["revision_text"]) for row in releases] == [
            ("as available", None, None),
            ("19.03.2026", "February 2026 provisional", "final"),
        ]
        assert frontier_row["resource_kind"] == "release_event"
        assert frontier_row["last_crawled_at"] is not None
        assert frontier_row["revisit_after"] is not None


def test_sqlite_pipeline_promotes_release_links_before_frontier_upsert():
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

        item = {
            "url": "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",
            "found_on_page": "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/residential-property-price-index.html",
            "title": "Publication schedule",
            "resource_kind": "isaweb_entry",
            "language": "en",
        }

        pipeline.process_item(item, spider)
        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        frontier_row = conn.execute(
            """
            SELECT resource_kind, priority
            FROM frontier_urls
            WHERE url = ?
            """,
            ("https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",),
        ).fetchone()
        conn.close()

        assert frontier_row["resource_kind"] == "release_event"
        assert frontier_row["priority"] == 90
