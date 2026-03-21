import sys
from pathlib import Path

from scrapy.http import HtmlResponse, Request

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.spiders.oenb_spider import OenbSpider


def test_parse_emits_direct_isaweb_data_request_for_parseable_link():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <a href="/isawebstat/dynabfrage/showResult?lang=EN&hierid=11&pos=VDBFKBSC217000&dval1=AT&freq=M">
          Base rates
        </a>
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
    request_urls = sorted(
        output.url
        for output in outputs
        if isinstance(output, Request)
    )

    assert "https://www.oenb.at/isadataservice/content?hierid=11&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/data?dval1=AT&freq=M&hierid=11&lang=EN&pos=VDBFKBSC217000" in request_urls
    assert "https://www.oenb.at/isadataservice/meta?hierid=11&lang=EN&pos=VDBFKBSC217000" in request_urls


def test_parse_chart_page_emits_service_requests_from_resolved_positions():
    spider = OenbSpider()
    html = """
    <html>
      <head><title>DATA Chart - Selected balance sheet items of the Oesterreichische Nationalbank - assets</title></head>
      <body>
        <input type="hidden" name="chartOld" value="1.1.1.1">
        <input type="hidden" name="selectedPosList" value="VDBFKBSC217000_2_2041_15_1187,VDBFKBSC317000_2_2041_15_1187">
        <a href="/isawebstat/stabfrage/createReport?report=1.1.1&amp;lang=EN" title="back to report"></a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isadataservice/content?hierid=11&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/data?hierid=11&lang=EN&pos=VDBFKBSC217000&pos=VDBFKBSC317000" in request_urls
    assert "https://www.oenb.at/isadataservice/meta?hierid=11&lang=EN&pos=VDBFKBSC217000&pos=VDBFKBSC317000" in request_urls


def test_parse_report_link_emits_content_request_without_positions():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <a href="/isawebstat/stabfrage/createReport?report=3.21.1&amp;lang=EN">
          Number of Banks
        </a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isadataservice/content?hierid=321&lang=EN" in request_urls


def test_statistics_section_follows_linked_isaweb_report_pages():
    spider = OenbSpider(section="statistics")
    html = """
    <html>
      <body>
        <a href="/isawebstat/stabfrage/createReport?report=2.1&amp;lang=EN">
          Base and reference rates
        </a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Base-and-Reference-Rates.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Base-and-Reference-Rates.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isawebstat/stabfrage/createReport?report=2.1&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/content?hierid=2&lang=EN" in request_urls


def test_statistics_section_follows_report_10_4_for_html_materialization():
    spider = OenbSpider(section="statistics")
    html = """
    <html>
      <body>
        <a href="/isawebstat/stabfrage/createReport?report=10.4&amp;lang=EN">
          Key interest rates
        </a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isawebstat/stabfrage/createReport?report=10.4&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/content?hierid=10&lang=EN" in request_urls


def test_parse_script_embedded_report_reference_emits_content_request():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <script>
          const reportUrl = "/isawebstat/stabfrage/createReport?report=3.21.1&amp;lang=EN";
        </script>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isadataservice/content?hierid=321&lang=EN" in request_urls


def test_parse_report_page_ignores_static_and_self_embedded_isaweb_items():
    spider = OenbSpider()
    html = """
    <html>
      <body>
        <script>
          const reportUrl = "/isawebstat/stabfrage/createReport?report=14.8&amp;lang=EN";
          const cssUrl = "/isawebstat/css/oenb.css";
          const jsUrl = "/isawebstat/js/oenb.js";
        </script>
        <table>
          <tr><th>Period</th><th>Value</th></tr>
          <tr><td>Q1 25</td><td>68,804</td></tr>
          <tr><td>Q2 25</td><td>69,548</td></tr>
        </table>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))
    interactive_urls = sorted(
        output["url"]
        for output in outputs
        if not isinstance(output, Request) and output["type"] == "interactive_data"
    )

    assert "https://www.oenb.at/isadataservice/content?hierid=14&lang=EN" in request_urls
    assert interactive_urls == []


def test_isaweb_focus_mode_only_follows_isaweb_targets():
    spider = OenbSpider(isaweb_focus=True)
    html = """
    <html>
      <body>
        <a href="/en/Research.html">Research</a>
        <a href="/dam/jcr:test/report.pdf">Report PDF</a>
        <a href="/isawebstat/stabfrage/createReport?report=14.8&amp;lang=EN">Guarantees</a>
        <script>
          const contentUrl = "/isadataservice/content?hierid=14&amp;lang=EN";
        </script>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.7",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.7"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/en/Research.html" not in request_urls
    assert "https://www.oenb.at/dam/jcr:test/report.pdf" not in request_urls
    assert "https://www.oenb.at/isawebstat/stabfrage/createReport?report=14.8&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/content?hierid=14&lang=EN" in request_urls


def test_isaweb_focus_mode_does_not_follow_dynabfrage_landing():
    spider = OenbSpider(isaweb_focus=True)
    html = """
    <html>
      <body>
        <a href="/isawebstat/dynabfrage?lang=EN">User-defined query</a>
      </body>
    </html>
    """

    response = HtmlResponse(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8"),
    )

    outputs = list(spider.parse(response))
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isawebstat/dynabfrage?lang=EN" not in request_urls


def test_isaweb_focus_mode_materializes_show_result_without_following_it():
    spider = OenbSpider(isaweb_focus=True)
    html = """
    <html>
      <body>
        <a href="/isawebstat/dynabfrage/showResult?lang=EN&amp;hierid=11&amp;pos=VDBFKBSC217000&amp;dval1=AT&amp;freq=M">
          Base rates
        </a>
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
    request_urls = sorted(output.url for output in outputs if isinstance(output, Request))

    assert "https://www.oenb.at/isawebstat/dynabfrage/showResult?lang=EN&hierid=11&pos=VDBFKBSC217000&dval1=AT&freq=M" not in request_urls
    assert "https://www.oenb.at/isadataservice/content?hierid=11&lang=EN" in request_urls
    assert "https://www.oenb.at/isadataservice/data?dval1=AT&freq=M&hierid=11&lang=EN&pos=VDBFKBSC217000" in request_urls
    assert "https://www.oenb.at/isadataservice/meta?hierid=11&lang=EN&pos=VDBFKBSC217000" in request_urls
