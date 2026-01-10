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


class TestShinyAppDetection:
    """Test Shiny app URL detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_shinyapps_io(self):
        assert self.spider._is_shiny_app("https://myapp.shinyapps.io/dashboard")

    def test_detects_shiny_subdomain(self):
        assert self.spider._is_shiny_app("https://shiny.oenb.at/app")

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
