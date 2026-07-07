import sys
from pathlib import Path

from scrapy.http import HtmlResponse, Request

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db
from oenb_scraper.isaweb_store import store_isaweb_page_context
from oenb_scraper.frontier import upsert_frontier_url
from oenb_scraper.spiders.oenb_spider import OenbSpider


def test_start_requests_uses_due_frontier_urls_when_enabled(tmp_path: Path):
    db_path = tmp_path / "crawler.db"
    conn = init_db(db_path)
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/en/Statistics/Standardized-Tables.html",
        priority=80,
        revisit_after="2026-03-18T10:00:00Z",
    )

    spider = OenbSpider(
        use_frontier=True,
        frontier_db_path=str(db_path),
        frontier_now="2026-03-18T10:00:00Z",
    )

    requests = list(spider.start_requests())

    assert [request.url for request in requests] == [
        "https://www.oenb.at/en/Statistics/Standardized-Tables.html",
    ]


def test_start_requests_can_filter_frontier_urls_by_kind(tmp_path: Path):
    db_path = tmp_path / "crawler.db"
    conn = init_db(db_path)
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/en/Statistics/Standardized-Tables.html",
        priority=80,
        resource_kind="page_document",
        revisit_after="2026-03-18T10:00:00Z",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        priority=90,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )

    spider = OenbSpider(
        use_frontier=True,
        frontier_db_path=str(db_path),
        frontier_now="2026-03-18T10:00:00Z",
        frontier_kinds="isaweb_entry",
    )

    requests = list(spider.start_requests())

    assert [request.url for request in requests] == [
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
    ]


def test_start_requests_in_isaweb_focus_skips_non_target_isaweb_frontier_urls(tmp_path: Path):
    db_path = tmp_path / "crawler.db"
    conn = init_db(db_path)
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/dynabfrage?lang=EN",
        priority=95,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        priority=90,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )

    spider = OenbSpider(
        use_frontier=True,
        frontier_db_path=str(db_path),
        frontier_now="2026-03-18T10:00:00Z",
        frontier_kinds="isaweb_entry",
        isaweb_focus=True,
    )

    requests = list(spider.start_requests())

    assert [request.url for request in requests] == [
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
    ]


def test_start_requests_in_isaweb_focus_prioritizes_open_report_contexts(tmp_path: Path):
    db_path = tmp_path / "crawler.db"
    conn = init_db(db_path)
    store_isaweb_page_context(
        conn,
        source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates.html",
        target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4",
        link_text="Table",
        relation_kind="isaweb_entry",
        fallback_lang="EN",
    )
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/createChart?lang=EN&report=10.4",
        priority=80,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )

    spider = OenbSpider(
        use_frontier=True,
        frontier_db_path=str(db_path),
        frontier_now="2026-03-18T10:00:00Z",
        frontier_kinds="isaweb_entry",
        frontier_limit=5,
        isaweb_focus=True,
    )

    requests = list(spider.start_requests())
    request_urls = [request.url for request in requests]

    assert request_urls[0] == "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"
    assert "https://www.oenb.at/isawebstat/createChart?lang=EN&report=10.4" in request_urls


def test_frontier_seed_requests_use_positive_priority(tmp_path: Path):
    db_path = tmp_path / "crawler.db"
    conn = init_db(db_path)
    upsert_frontier_url(
        conn,
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        priority=90,
        resource_kind="isaweb_entry",
        revisit_after="2026-03-18T10:00:00Z",
    )

    spider = OenbSpider(
        use_frontier=True,
        frontier_db_path=str(db_path),
        frontier_now="2026-03-18T10:00:00Z",
        frontier_kinds="isaweb_entry",
        isaweb_focus=True,
    )

    requests = list(spider.start_requests())

    assert requests[0].priority > 0


def test_parse_emits_request_for_internal_machine_readable_asset():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <a href="/downloads/leitzins.csv">Leitzins CSV</a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = [output.url for output in outputs if isinstance(output, Request)]

    assert "https://www.oenb.at/downloads/leitzins.csv" in request_urls


def test_parse_records_pdf_as_item_but_does_not_fetch():
    """PDFs are recorded as download items (so we know they exist) but not fetched."""
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <h2>Statistics</h2>
        <a href="/dam/jcr:note/explanatory-note.pdf">Explanatory note PDF</a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = [output.url for output in outputs if isinstance(output, Request)]
    item_urls = [output["url"] for output in outputs if not isinstance(output, Request) and "url" in output]

    # PDF is catalogued as a download item
    assert "https://www.oenb.at/dam/jcr:note/explanatory-note.pdf" in item_urls
    # But NOT fetched via HTTP request
    assert "https://www.oenb.at/dam/jcr:note/explanatory-note.pdf" not in request_urls


def test_parse_does_not_emit_request_for_generic_homepage_pdf():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <a href="/dam/jcr:annual/annual-report.pdf">Annual report PDF</a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/"),
    )

    outputs = list(spider.parse(response))
    request_urls = [output.url for output in outputs if isinstance(output, Request)]

    assert "https://www.oenb.at/dam/jcr:annual/annual-report.pdf" not in request_urls


def test_statistics_section_uses_real_statistics_seed_and_filter():
    spider = OenbSpider(section="statistics")

    assert spider.start_urls == ["https://www.oenb.at/en/Statistics/Standardized-Tables.html"]
    assert spider._is_internal_link("https://www.oenb.at/en/Statistics/Standardized-Tables.html")
    assert not spider._is_internal_link("https://www.oenb.at/en/Research.html")


def test_section_heading_computed_once_per_page():
    """The heading scan is document-level work — it must run once per page,
    not once per link (quadratic on large archive pages)."""
    spider = OenbSpider()
    calls = {"count": 0}
    original = spider._page_section_heading

    def counting(response):
        calls["count"] += 1
        return original(response)

    spider._page_section_heading = counting

    links = "\n".join(
        f'<a href="/dam/file{i}.pdf">Download {i}</a>' for i in range(50)
    )
    response = HtmlResponse(
        url="https://www.oenb.at/Publikationen/report.html",
        body=f"<html><body><h2>Publikationen</h2>{links}</body></html>".encode(),
        encoding="utf-8",
    )
    list(spider.parse(response))
    assert calls["count"] == 1
