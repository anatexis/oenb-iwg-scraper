"""Tests for OeNB spider URL handling."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.spiders.oenb_spider import OenbSpider


class TestDownloadDetection:
    """Test file download detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_pdf_as_download(self):
        assert self.spider._is_download("https://example.com/file.pdf")

    def test_detects_xlsx_as_download(self):
        assert self.spider._is_download("https://example.com/data.xlsx")

    def test_detects_csv_as_download(self):
        assert self.spider._is_download("https://example.com/export.csv")

    def test_detects_xml_as_download(self):
        assert self.spider._is_download("https://example.com/data.xml")

    def test_detects_zip_as_download(self):
        assert self.spider._is_download("https://example.com/archive.zip")

    def test_html_is_not_download(self):
        assert not self.spider._is_download("https://example.com/page.html")

    def test_no_extension_is_not_download(self):
        assert not self.spider._is_download("https://example.com/page")

    def test_image_is_not_download(self):
        assert not self.spider._is_download("https://example.com/logo.png")

    def test_detects_csv_query_format(self):
        """Should detect downloads with ?format=CSV query parameter."""
        assert self.spider._is_download("https://www.oenb.at/oearb/zinssatzwechselkurse/download-daily?format=CSV")

    def test_detects_xlsx_query_format(self):
        """Should detect downloads with ?format=xlsx query parameter."""
        assert self.spider._is_download("https://example.com/export?format=xlsx")

    def test_detects_download_path_with_format(self):
        """Should detect download paths with format parameter."""
        assert self.spider._is_download("https://example.com/download?format=json")

    def test_rejects_invalid_format_param(self):
        """Should not detect download for invalid format values."""
        assert not self.spider._is_download("https://example.com/page?format=html")

    def test_detects_txt_as_download(self):
        assert self.spider._is_download("https://example.com/file.txt")

    def test_detects_odt_as_download(self):
        assert self.spider._is_download("https://example.com/doc.odt")

    def test_detects_geojson_as_download(self):
        assert self.spider._is_download("https://example.com/map.geojson")

    def test_detects_rdf_as_download(self):
        assert self.spider._is_download("https://example.com/data.rdf")

    def test_detects_ttl_as_download(self):
        assert self.spider._is_download("https://example.com/data.ttl")


class TestShinyAppDetection:
    """Test Shiny app URL detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_shinyapps_io(self):
        assert self.spider._is_shiny_app("https://myapp.shinyapps.io/dashboard")

    def test_detects_shiny_subdomain(self):
        assert self.spider._is_shiny_app("https://shiny.oenb.at/app")


class TestShinySourceExtraction:
    """Test source extraction from Shiny app pages."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_extracts_datenquelle_from_footer(self):
        """Should extract sources from footer links like 'Datenquelle: ECB Data Portal'."""
        response = MockResponse("")
        response.css = lambda q: MockSelector(["Datenquelle: ECB Data Portal", "Geodaten: Natural Earth"])
        sources = self.spider._extract_sources_from_shiny(response)
        assert "ECB Data Portal" in sources
        assert "Natural Earth" in sources

    def test_extracts_source_prefix(self):
        """Should extract sources with Source: prefix."""
        response = MockResponse("")
        response.css = lambda q: MockSelector(["Source: World Bank Data"])
        sources = self.spider._extract_sources_from_shiny(response)
        assert "World Bank Data" in sources

    def test_requires_prefix_for_sources(self):
        """Should only extract sources with explicit prefixes, not random text."""
        response = MockResponse("")
        response.css = lambda q: MockSelector(["Home", "About", "OeNB", "Statistics"])
        sources = self.spider._extract_sources_from_shiny(response)
        assert sources == []  # No prefixes like "Datenquelle:" = no sources

    def test_detects_shiny_path(self):
        assert self.spider._is_shiny_app("https://example.com/shiny/app")

    def test_regular_url_is_not_shiny(self):
        assert not self.spider._is_shiny_app("https://www.oenb.at/page.html")


class TestInternalLinkDetection:
    """Test internal vs external link detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_oenb_at_is_internal(self):
        assert self.spider._is_internal_link("https://www.oenb.at/page")

    def test_relative_url_is_internal(self):
        assert self.spider._is_internal_link("/Statistik/data.html")

    def test_external_domain_is_not_internal(self):
        assert not self.spider._is_internal_link("https://google.com/search")

    def test_mailto_is_not_internal(self):
        """mailto: links should NOT be followed."""
        assert not self.spider._is_internal_link("mailto:info@oenb.at")

    def test_javascript_is_not_internal(self):
        """javascript: links should NOT be followed."""
        assert not self.spider._is_internal_link("javascript:void(0)")

    def test_tel_is_not_internal(self):
        """tel: links should NOT be followed."""
        assert not self.spider._is_internal_link("tel:+43123456")


class TestLanguageExtraction:
    """Test language extraction from URL."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_german_page_returns_de(self):
        assert self.spider._extract_language("https://www.oenb.at/Statistik/data") == "de"

    def test_english_page_returns_en(self):
        assert self.spider._extract_language("https://www.oenb.at/en/Statistics/data") == "en"

    def test_root_returns_de(self):
        assert self.spider._extract_language("https://www.oenb.at/") == "de"

    def test_english_root_returns_en(self):
        assert self.spider._extract_language("https://www.oenb.at/en/") == "en"


class TestSectionExtraction:
    """Test page section extraction from URL."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_extracts_first_path_segment(self):
        assert self.spider._extract_section("https://www.oenb.at/Statistik/data") == "Statistik"

    def test_extracts_geldpolitik(self):
        assert self.spider._extract_section("https://www.oenb.at/Geldpolitik/ziele") == "Geldpolitik"

    def test_root_returns_startseite(self):
        assert self.spider._extract_section("https://www.oenb.at/") == "Startseite"

    def test_english_section_skips_en_prefix(self):
        """Section should be 'Calendar' not 'en' for English pages."""
        assert self.spider._extract_section("https://www.oenb.at/en/Calendar/2020") == "Calendar"

    def test_english_root_returns_startseite(self):
        assert self.spider._extract_section("https://www.oenb.at/en/") == "Startseite"


class TestFileExtensionExtraction:
    """Test file extension extraction."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_extracts_pdf_extension(self):
        assert self.spider._get_file_extension("https://example.com/report.pdf") == "pdf"

    def test_extracts_xlsx_extension(self):
        assert self.spider._get_file_extension("https://example.com/data.xlsx") == "xlsx"

    def test_unknown_for_non_download(self):
        assert self.spider._get_file_extension("https://example.com/page.html") == "unknown"

    def test_handles_uppercase(self):
        assert self.spider._get_file_extension("https://example.com/FILE.PDF") == "pdf"

    def test_extracts_csv_from_query_param(self):
        """Should extract file type from ?format=CSV query parameter."""
        assert self.spider._get_file_extension("https://www.oenb.at/oearb/download?format=CSV") == "csv"

    def test_extracts_xlsx_from_query_param(self):
        """Should extract file type from ?format=xlsx query parameter."""
        assert self.spider._get_file_extension("https://example.com/export?format=xlsx") == "xlsx"


class MockSelector:
    """Mock Scrapy selector for testing."""

    def __init__(self, texts=None):
        self._texts = texts or []
        self._parent = None

    def xpath(self, query):
        if self._parent:
            return self._parent
        return MockSelector()

    def css(self, query):
        return MockSelector(self._texts)

    def getall(self):
        return self._texts

    def set_parent(self, parent):
        self._parent = parent


class MockResponse:
    """Mock Scrapy response for testing."""

    def __init__(self, text=""):
        self.text = text


class TestSourceExtraction:
    """Test source extraction from page content."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_extracts_single_source_german(self):
        response = MockResponse("Quelle: OeNB")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources

    def test_extracts_multiple_sources_comma(self):
        response = MockResponse("Quelle: OeNB, Statistik Austria, Eurostat")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources
        assert "Statistik Austria" in sources
        assert "Eurostat" in sources

    def test_extracts_multiple_sources_semicolon(self):
        response = MockResponse("Quelle: OeNB; EZB; IWF")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources
        assert "EZB" in sources
        assert "IWF" in sources

    def test_extracts_sources_with_und(self):
        response = MockResponse("Quelle: OeNB und Statistik Austria")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources
        assert "Statistik Austria" in sources

    def test_extracts_english_source(self):
        response = MockResponse("Source: European Central Bank")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "European Central Bank" in sources

    def test_extracts_datenquelle(self):
        response = MockResponse("Datenquelle: Statistik Austria")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "Statistik Austria" in sources

    def test_extracts_quellen_plural(self):
        response = MockResponse("Quellen: OeNB, EZB")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources
        assert "EZB" in sources

    def test_returns_empty_list_when_no_source(self):
        response = MockResponse("This is some text without source information.")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert sources == []

    def test_cleans_trailing_punctuation(self):
        response = MockResponse("Quelle: OeNB.")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "OeNB" in sources
        assert "OeNB." not in sources

    def test_ignores_very_short_sources(self):
        response = MockResponse("Quelle: A, OeNB")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "A" not in sources  # Too short (< 3 chars)
        assert "OeNB" in sources

    def test_ignores_very_long_sources(self):
        long_text = "A" * 60
        response = MockResponse(f"Quelle: {long_text}, OeNB")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert long_text not in sources  # Too long (> 50 chars)
        assert "OeNB" in sources

    def test_handles_mixed_separators(self):
        response = MockResponse("Quelle: OeNB, Statistik Austria und EZB; IWF")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert len(sources) >= 3  # At least OeNB, Statistik Austria, EZB

    def test_rejects_lowercase_starting_text(self):
        """Should not capture text starting with lowercase like 'the secured'."""
        response = MockResponse("Source: (1) the secured, unsecured interbank money market")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "the secured" not in sources
        assert "(1) the secured" not in sources
        assert sources == []  # No valid sources in this text

    def test_rejects_numbered_items(self):
        """Should not capture items starting with numbers."""
        response = MockResponse("Quelle: 1. Statistik, 2. Analyse")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        # Should reject these as they look like list items, not sources
        assert "1" not in sources
        assert "2" not in sources

    def test_recognizes_known_sources(self):
        """Should recognize common Austrian data sources."""
        response = MockResponse("Quelle: Statistik Austria, Eurostat und WIFO")
        link = MockSelector()
        sources = self.spider._extract_sources(link, response)
        assert "Statistik Austria" in sources
        assert "Eurostat" in sources
        assert "WIFO" in sources


class TestTableDetection:
    """Test HTML table detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_substantial_table(self):
        """Table with 3+ rows should be detected."""
        html = """
        <table>
            <tr><th>A</th><th>B</th></tr>
            <tr><td>1</td><td>2</td></tr>
            <tr><td>3</td><td>4</td></tr>
            <tr><td>5</td><td>6</td></tr>
        </table>
        """
        assert self.spider._count_data_tables(html) == 1

    def test_ignores_small_table(self):
        """Table with less than 3 rows should be ignored."""
        html = "<table><tr><td>X</td></tr></table>"
        assert self.spider._count_data_tables(html) == 0

    def test_ignores_layout_table(self):
        """Tables with layout classes should be ignored."""
        html = '<table class="layout"><tr><td>X</td><td>Y</td></tr><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>'
        assert self.spider._count_data_tables(html) == 0


class MockRequest:
    """Mock Scrapy request for testing."""

    def __init__(self, url, meta=None):
        self.url = url
        self.meta = meta or {}


class MockHttpResponse:
    """Mock HTTP response for testing FailedUrlLogger."""

    def __init__(self, url, status):
        self.url = url
        self.status = status


class MockStats:
    """Mock Scrapy stats collector."""

    def __init__(self, stats=None):
        self._stats = stats or {}

    def get_stats(self):
        return self._stats


class MockCrawler:
    """Mock Scrapy crawler."""

    def __init__(self, stats=None):
        self.stats = MockStats(stats)


class MockSpiderForLogger:
    """Mock spider for FailedUrlLogger tests."""

    def __init__(self, stats=None):
        self.crawler = MockCrawler(stats)

    class logger:
        @staticmethod
        def info(msg):
            pass


class TestFailedUrlLogger:
    """Test failed URL logging extension."""

    def test_initializes_with_empty_list(self, tmp_path):
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)

        assert logger.failed_urls == []
        assert logger.output_path == output_path

    def test_captures_failed_request(self, tmp_path):
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)
        spider = MockSpiderForLogger()

        request = MockRequest("https://example.com/broken", {"reason": "503 Error"})
        logger.request_failed(request, spider)

        assert len(logger.failed_urls) == 1
        assert logger.failed_urls[0]["url"] == "https://example.com/broken"
        assert "503 Error" in logger.failed_urls[0]["reason"]

    def test_captures_multiple_failures(self, tmp_path):
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)
        spider = MockSpiderForLogger()

        urls = [
            "https://example.com/error1",
            "https://example.com/error2",
            "https://example.com/error3",
        ]

        for url in urls:
            logger.request_failed(MockRequest(url), spider)

        assert len(logger.failed_urls) == 3

    def test_writes_json_on_spider_close(self, tmp_path):
        import json
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)

        stats = {
            "downloader/response_status_count/200": 100,
            "downloader/response_status_count/404": 5,
            "downloader/response_status_count/503": 10,
        }
        spider = MockSpiderForLogger(stats)

        # Add some failed URLs
        logger.request_failed(MockRequest("https://example.com/fail1"), spider)
        logger.request_failed(MockRequest("https://example.com/fail2"), spider)

        # Close spider
        logger.spider_closed(spider, "finished")

        # Check output file
        assert output_path.exists()
        data = json.loads(output_path.read_text())

        assert data["summary"]["total_dropped_requests"] == 2
        assert data["summary"]["http_error_counts"]["404"] == 5
        assert data["summary"]["http_error_counts"]["503"] == 10
        assert "200" not in data["summary"]["http_error_counts"]  # Success codes excluded
        assert data["summary"]["spider_close_reason"] == "finished"
        assert len(data["dropped_requests"]) == 2

    def test_excludes_success_status_codes(self, tmp_path):
        import json
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)

        stats = {
            "downloader/response_status_count/200": 500,
            "downloader/response_status_count/301": 50,
            "downloader/response_status_count/404": 3,
        }
        spider = MockSpiderForLogger(stats)

        logger.spider_closed(spider, "finished")

        data = json.loads(output_path.read_text())

        # Only 4xx and 5xx should be in http_error_counts
        assert "200" not in data["summary"]["http_error_counts"]
        assert "301" not in data["summary"]["http_error_counts"]
        assert data["summary"]["http_error_counts"]["404"] == 3

    def test_captures_http_errors(self, tmp_path):
        from oenb_scraper.pipelines import FailedUrlLogger

        output_path = tmp_path / "failed.json"
        logger = FailedUrlLogger(output_path)
        spider = MockSpiderForLogger()

        # Simulate 404 and 500 responses
        request = MockRequest("https://example.com/page", {"referer": "https://example.com/"})
        response_404 = MockHttpResponse("https://example.com/missing", 404)
        response_500 = MockHttpResponse("https://example.com/error", 500)
        response_200 = MockHttpResponse("https://example.com/ok", 200)

        logger.response_received(response_404, request, spider)
        logger.response_received(response_500, request, spider)
        logger.response_received(response_200, request, spider)  # Should be ignored

        assert len(logger.http_errors) == 2
        assert logger.http_errors[0]["url"] == "https://example.com/missing"
        assert logger.http_errors[0]["status"] == 404
        assert logger.http_errors[1]["status"] == 500


class TestApiDetection:
    """Test API endpoint URL detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_api_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/api/data")

    def test_detects_oearb_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/oearb/zinssatzwechselkurse/download")

    def test_detects_rest_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/rest/v1/currencies")

    def test_detects_data_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/data/exchange-rates")

    def test_rejects_normal_page(self):
        assert not self.spider._is_potential_api("https://www.oenb.at/Statistik/Standardisierte-Tabellen.html")


class TestInteractiveDataDetection:
    """Test interactive data portal URL detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_isawebstat(self):
        assert self.spider._is_interactive_data("https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11")

    def test_detects_dynabfrage(self):
        assert self.spider._is_interactive_data("https://www.oenb.at/dynabfrage/query")

    def test_detects_isaweb(self):
        assert self.spider._is_interactive_data("https://www.oenb.at/isaweb/report")

    def test_rejects_normal_page(self):
        assert not self.spider._is_interactive_data("https://www.oenb.at/Statistik/info.html")

    def test_rejects_download(self):
        assert not self.spider._is_interactive_data("https://www.oenb.at/file.csv")


class TestStandardizedTablesDetection:
    """Test standardized tables (data catalog) URL detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_standardized_tables(self):
        url = "https://www.oenb.at/Statistik/Standardisierte-Tabellen/zinssaetze-und-wechselkurse/Eurogeldmarkt-und-Eurosystemzinssaetze-.html"
        assert self.spider._is_standardized_tables(url)

    def test_detects_standardized_tables_root(self):
        assert self.spider._is_standardized_tables("https://www.oenb.at/Statistik/Standardisierte-Tabellen.html")

    def test_case_insensitive(self):
        assert self.spider._is_standardized_tables("https://www.oenb.at/statistik/standardisierte-tabellen/test.html")

    def test_rejects_normal_statistik_page(self):
        assert not self.spider._is_standardized_tables("https://www.oenb.at/Statistik/info.html")

    def test_rejects_interactive_data(self):
        assert not self.spider._is_standardized_tables("https://www.oenb.at/isawebstat/report")
