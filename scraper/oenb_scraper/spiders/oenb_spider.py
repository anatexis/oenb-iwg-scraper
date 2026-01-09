import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import scrapy

from oenb_scraper.items import DownloadItem


class OenbSpider(scrapy.Spider):
    name = "oenb"
    allowed_domains = ["oenb.at", "www.oenb.at"]
    start_urls = [
        "https://www.oenb.at/",
        "https://www.oenb.at/Service/Sitemap.html",
    ]

    # File extensions to capture as downloads
    DOWNLOAD_EXTENSIONS = {
        ".pdf", ".xlsx", ".xls", ".csv", ".xml", ".zip",
        ".doc", ".docx", ".ppt", ".pptx", ".json"
    }

    # Patterns for Shiny apps
    SHINY_PATTERNS = [
        r"shinyapps\.io",
        r"/shiny/",
        r"shiny\.oenb\.at",
    ]

    def parse(self, response):
        """Parse a page for downloads and follow links."""
        page_url = response.url
        page_section = self._extract_section(page_url)
        page_date = self._extract_page_date(response)

        # Find all links on the page
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            full_url = urljoin(page_url, href)
            link_text = link.css("::text").get() or ""
            link_text = link_text.strip()

            # Check if it's a download
            if self._is_download(full_url):
                yield self._create_download_item(
                    url=full_url,
                    title=link_text,
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                )

            # Check if it's a Shiny app
            elif self._is_shiny_app(full_url):
                yield self._create_shiny_item(
                    url=full_url,
                    title=link_text,
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                )

            # Follow internal links
            elif self._is_internal_link(full_url):
                yield response.follow(full_url, callback=self.parse)

        # Also check iframes for embedded Shiny apps
        for iframe in response.css("iframe[src]"):
            src = iframe.attrib.get("src", "")
            if self._is_shiny_app(src):
                yield self._create_shiny_item(
                    url=src,
                    title="Embedded Shiny App",
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading="",
                    page_date=page_date,
                )

    def _is_download(self, url: str) -> bool:
        """Check if URL points to a downloadable file."""
        parsed = urlparse(url.lower())
        path = parsed.path
        return any(path.endswith(ext) for ext in self.DOWNLOAD_EXTENSIONS)

    def _is_shiny_app(self, url: str) -> bool:
        """Check if URL is a Shiny app."""
        return any(re.search(pattern, url, re.I) for pattern in self.SHINY_PATTERNS)

    def _is_internal_link(self, url: str) -> bool:
        """Check if URL is internal to oenb.at."""
        parsed = urlparse(url)
        return parsed.netloc in self.allowed_domains or parsed.netloc == ""

    def _extract_section(self, url: str) -> str:
        """Extract page section from URL path."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
        return "Startseite"

    def _extract_page_date(self, response) -> str | None:
        """Try to extract page date from meta tags or content."""
        # Try meta date
        date = response.css('meta[name="date"]::attr(content)').get()
        if date:
            return date

        # Try last-modified header
        last_modified = response.headers.get("Last-Modified")
        if last_modified:
            return last_modified.decode("utf-8", errors="ignore")

        return None

    def _find_section_heading(self, link, response) -> str:
        """Find the nearest heading above the link."""
        # Try to find preceding h1, h2, h3
        for heading in ["h1", "h2", "h3"]:
            headings = response.css(f"{heading}::text").getall()
            if headings:
                return headings[-1].strip()
        return ""

    def _get_file_extension(self, url: str) -> str:
        """Extract file extension from URL."""
        parsed = urlparse(url.lower())
        path = parsed.path
        for ext in self.DOWNLOAD_EXTENSIONS:
            if path.endswith(ext):
                return ext.lstrip(".")
        return "unknown"

    def _create_download_item(self, **kwargs) -> DownloadItem:
        """Create a DownloadItem for a downloadable file."""
        item = DownloadItem()
        item["url"] = kwargs["url"]
        item["type"] = "download"
        item["file_type"] = self._get_file_extension(kwargs["url"])
        item["file_size_bytes"] = None  # Will be filled by pipeline
        item["title"] = kwargs["title"]
        item["found_on_page"] = kwargs["found_on_page"]
        item["page_section"] = kwargs["page_section"]
        item["section_heading"] = kwargs["section_heading"]
        item["page_date"] = kwargs["page_date"]
        item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
        item["machine_readable"] = None  # Will be filled by pipeline for PDFs
        item["has_tables"] = None
        return item

    def _create_shiny_item(self, **kwargs) -> DownloadItem:
        """Create a DownloadItem for a Shiny app."""
        item = DownloadItem()
        item["url"] = kwargs["url"]
        item["type"] = "shiny_app"
        item["file_type"] = "shiny"
        item["file_size_bytes"] = None
        item["title"] = kwargs["title"]
        item["found_on_page"] = kwargs["found_on_page"]
        item["page_section"] = kwargs["page_section"]
        item["section_heading"] = kwargs["section_heading"]
        item["page_date"] = kwargs["page_date"]
        item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
        item["machine_readable"] = True  # Shiny apps have data
        item["has_tables"] = None
        return item
