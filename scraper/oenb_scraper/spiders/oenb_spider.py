import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

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
        ".doc", ".docx", ".ppt", ".pptx", ".json",
        # IWG additions
        ".txt", ".odt", ".rtf", ".epub",      # Text/Docs
        ".geojson", ".kml", ".gml",            # Geo
        ".rdf", ".ttl", ".ods"                 # Structured data
    }

    # Patterns for Shiny apps
    SHINY_PATTERNS = [
        r"shinyapps\.io",
        r"/shiny/",
        r"shiny\.oenb\.at",
    ]

    def parse(self, response):
        """Parse a page for downloads and follow links."""
        # Skip non-text responses (images, etc.)
        if not hasattr(response, 'text'):
            return

        page_url = response.url
        page_section = self._extract_section(page_url)
        page_language = self._extract_language(page_url)
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
                    language=page_language,
                    sources=self._extract_sources(link, response),
                )

            # Check if it's a Shiny app - fetch the page to extract sources
            elif self._is_shiny_app(full_url):
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_shiny_app,
                    meta={
                        "shiny_url": full_url,
                        "title": link_text,
                        "found_on_page": page_url,
                        "page_section": page_section,
                        "section_heading": self._find_section_heading(link, response),
                        "page_date": page_date,
                        "language": page_language,
                    },
                    dont_filter=True,  # Allow fetching external domains
                )

            # Follow internal links
            elif self._is_internal_link(full_url):
                yield response.follow(full_url, callback=self.parse)

        # Also check iframes for embedded Shiny apps
        for iframe in response.css("iframe[src]"):
            src = iframe.attrib.get("src", "")
            if self._is_shiny_app(src):
                yield scrapy.Request(
                    src,
                    callback=self.parse_shiny_app,
                    meta={
                        "shiny_url": src,
                        "title": "Embedded Shiny App",
                        "found_on_page": page_url,
                        "page_section": page_section,
                        "section_heading": "",
                        "page_date": page_date,
                        "language": page_language,
                    },
                    dont_filter=True,
                )

    def parse_shiny_app(self, response):
        """Parse a Shiny app page to extract sources."""
        meta = response.meta

        # Extract sources from the Shiny app page
        sources = self._extract_sources_from_shiny(response)

        yield self._create_shiny_item(
            url=meta["shiny_url"],
            title=meta["title"],
            found_on_page=meta["found_on_page"],
            page_section=meta["page_section"],
            section_heading=meta["section_heading"],
            page_date=meta["page_date"],
            language=meta["language"],
            sources=sources,
        )

    def _extract_sources_from_shiny(self, response) -> list[str]:
        """Extract sources from Shiny app HTML.

        Looks for footer links with explicit source prefixes.
        """
        sources = []

        # Look for footer links with source info
        footer_links = response.css(".footer-link::text, .source-link::text, footer a::text").getall()
        for text in footer_links:
            text = text.strip()
            # Extract source name from patterns like "Datenquelle: ECB Data Portal"
            for prefix in ["Datenquelle:", "Quelle:", "Source:", "Geodaten:", "Data:"]:
                if prefix in text:
                    source = text.split(prefix, 1)[1].strip()
                    if source and source not in sources:
                        sources.append(source)
                    break

        # Also try the standard extraction on page text
        if not sources:
            sources = self._extract_sources(None, response)

        return sources

    # Query parameter patterns that indicate downloads
    DOWNLOAD_QUERY_FORMATS = {"csv", "xlsx", "xls", "xml", "json", "pdf", "zip"}

    def _is_download(self, url: str) -> bool:
        """Check if URL points to a downloadable file.

        Checks both:
        - File extension in path (e.g., /file.csv)
        - Format query parameter (e.g., ?format=CSV)
        """
        parsed = urlparse(url.lower())
        path = parsed.path

        # Check file extension
        if any(path.endswith(ext) for ext in self.DOWNLOAD_EXTENSIONS):
            return True

        # Check query parameters for format indicators
        query_params = parse_qs(parsed.query)
        format_param = query_params.get("format", [])
        if format_param and format_param[0].lower() in self.DOWNLOAD_QUERY_FORMATS:
            return True

        # Check for download/export in path with format param
        if any(kw in path for kw in ["download", "export"]) and format_param:
            return True

        return False

    def _is_shiny_app(self, url: str) -> bool:
        """Check if URL is a Shiny app."""
        return any(re.search(pattern, url, re.I) for pattern in self.SHINY_PATTERNS)

    def _is_internal_link(self, url: str) -> bool:
        """Check if URL is internal to oenb.at and uses http(s)."""
        parsed = urlparse(url)
        # Only follow http/https links
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return False
        return parsed.netloc in self.allowed_domains or parsed.netloc == ""

    def _extract_language(self, url: str) -> str:
        """Extract language from URL path (de or en)."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0].lower() == "en":
            return "en"
        return "de"

    def _extract_section(self, url: str) -> str:
        """Extract page section from URL path, skipping language prefix."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        # Skip 'en' language prefix if present
        if parts and parts[0].lower() == "en":
            parts = parts[1:]
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

    # Known data sources (German and English variants)
    KNOWN_SOURCES = {
        "OeNB", "Oesterreichische Nationalbank", "Oesterreichischen Nationalbank",
        "Statistik Austria", "Statistics Austria",
        "EZB", "ECB", "Europäische Zentralbank", "European Central Bank",
        "Eurostat",
        "IWF", "IMF", "Internationaler Währungsfonds", "International Monetary Fund",
        "BIS", "Bank for International Settlements",
        "Weltbank", "World Bank",
        "OECD",
        "FMA", "Finanzmarktaufsicht",
        "BMF", "Bundesministerium für Finanzen",
        "Wifo", "WIFO",
        "IHS",
        "WKO", "Wirtschaftskammer",
        "AMS",
        "Hauptverband",
    }

    def _extract_sources(self, link, response) -> list[str]:
        """Extract source attribution near the link.

        Looks for patterns like:
        - "Quelle: OeNB, Statistik Austria"
        - "Source: OeNB"
        - "Quellen: OeNB; Eurostat"
        """
        sources = []

        # Get surrounding text context
        # Try parent elements up to 3 levels
        context_text = ""
        if link is not None:
            parent = link
            for _ in range(3):
                parent = parent.xpath("..")
                if parent:
                    # Get all text in parent element
                    texts = parent.css("::text").getall()
                    context_text = " ".join(t.strip() for t in texts if t.strip())
                    if context_text:
                        break

        # Also check the page for source patterns near figures/tables
        page_text = response.text if hasattr(response, 'text') else ""

        # Patterns to match source attributions (German and English)
        # Capture until end of line, sentence, or HTML tag
        source_patterns = [
            r'[Qq]uelle[n]?\s*[:;]\s*([A-ZÄÖÜ][^<\n]{2,80})',
            r'[Ss]ource[s]?\s*[:;]\s*([A-Z][^<\n]{2,80})',
            r'[Dd]atenquelle[n]?\s*[:;]\s*([A-ZÄÖÜ][^<\n]{2,80})',
        ]

        # Search in context text first, then page text
        for text in [context_text, page_text[:5000]]:
            if not text:
                continue
            for pattern in source_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    # Split by common separators
                    parts = re.split(r'[,;/&]|\bund\b|\band\b', match)
                    for part in parts:
                        part = part.strip()
                        # Clean up: remove trailing punctuation and whitespace
                        part = re.sub(r'[\.\)\]\s]+$', '', part).strip()

                        # Skip if empty or too short/long
                        if not part or len(part) < 3 or len(part) > 50:
                            continue

                        # Skip if starts with lowercase, number, or parenthesis
                        if re.match(r'^[a-zäöü0-9\(\[]', part):
                            continue

                        # Skip common false positives
                        if part.lower() in {'the', 'die', 'der', 'das', 'ein', 'eine'}:
                            continue

                        # Prefer known sources (exact or partial match)
                        is_known = any(known.lower() in part.lower() for known in self.KNOWN_SOURCES)

                        if is_known or re.match(r'^[A-ZÄÖÜ][a-zäöüA-ZÄÖÜ\s\-]+$', part):
                            if part not in sources:
                                sources.append(part)

                    if sources:
                        return sources  # Return first match found

        return sources

    def _get_file_extension(self, url: str) -> str:
        """Extract file extension from URL or query parameter."""
        parsed = urlparse(url.lower())
        path = parsed.path

        # Check file extension in path
        for ext in self.DOWNLOAD_EXTENSIONS:
            if path.endswith(ext):
                return ext.lstrip(".")

        # Check format query parameter
        query_params = parse_qs(parsed.query)
        format_param = query_params.get("format", [])
        if format_param:
            fmt = format_param[0].lower()
            if fmt in self.DOWNLOAD_QUERY_FORMATS:
                return fmt

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
        item["language"] = kwargs["language"]
        item["found_in_languages"] = None  # Will be filled by pipeline
        item["sources"] = kwargs.get("sources", [])
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
        item["language"] = kwargs["language"]
        item["found_in_languages"] = None  # Will be filled by pipeline
        item["sources"] = kwargs.get("sources", [])
        return item
