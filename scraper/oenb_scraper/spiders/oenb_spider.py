import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import scrapy

from oenb_scraper.items import DownloadItem


class OenbSpider(scrapy.Spider):
    name = "oenb"
    allowed_domains = ["oenb.at", "www.oenb.at", "finanzbildung.oenb.at"]
    start_urls = [
        "https://www.oenb.at/",
        "https://www.oenb.at/Service/Sitemap.html",
        "https://finanzbildung.oenb.at/",
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

    # URL patterns that indicate potential API endpoints
    API_PATTERNS = [
        "/api/",
        "/rest/",
        "/oearb/",
        "/data/",
    ]

    # URL patterns for interactive data portals
    INTERACTIVE_DATA_PATTERNS = [
        "/isawebstat/",
        "/dynabfrage/",
        "/isaweb/",
        "/statistik/interaktiv",
    ]

    # URL patterns for standardized tables (data catalog pages)
    STANDARDIZED_TABLES_PATTERNS = [
        "/statistik/standardisierte-tabellen",
    ]

    # Generic link texts that don't make good titles (lowercase)
    GENERIC_LINK_TEXTS = {
        "zur navigation", "zum inhalt", "skip to content", "skip to navigation",
        "zum hauptinhalt", "skip to main content", "navigation überspringen",
    }

    def _get_meaningful_title(self, link_text: str, url: str) -> str:
        """Get a meaningful title: use link text if good, otherwise extract from URL.

        Args:
            link_text: The text of the link (may be generic like "Zur Navigation")
            url: The URL to extract a title from if link_text is generic

        Returns:
            A meaningful title string
        """
        # If link text is meaningful, use it
        if link_text and link_text.lower() not in self.GENERIC_LINK_TEXTS:
            return link_text

        # Extract title from URL path
        parsed = urlparse(url)
        path = parsed.path

        # Get the last path segment (filename)
        segments = [s for s in path.split("/") if s]
        if not segments:
            return link_text or ""

        filename = segments[-1]

        # Remove common extensions
        for ext in [".html", ".htm", ".php", ".aspx"]:
            if filename.lower().endswith(ext):
                filename = filename[:-len(ext)]
                break

        # Replace hyphens/underscores with spaces and clean up
        title = filename.replace("-", " ").replace("_", " ")

        # Remove multiple spaces
        title = " ".join(title.split())

        return title if title else link_text or ""

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
                yield self._create_item(
                    "download",
                    url=full_url,
                    title=self._get_meaningful_title(link_text, full_url),
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
                        "title": self._get_meaningful_title(link_text, full_url),
                        "found_on_page": page_url,
                        "page_section": page_section,
                        "section_heading": self._find_section_heading(link, response),
                        "page_date": page_date,
                        "language": page_language,
                    },
                    dont_filter=True,  # Allow fetching external domains
                )

            # Check if it's a standardized tables page (data catalog)
            elif self._is_standardized_tables(full_url):
                yield self._create_item(
                    "standardized_tables",
                    url=full_url,
                    title=self._get_meaningful_title(link_text, full_url),
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                    language=page_language,
                )
                # Also follow the link to crawl for downloads
                if self._is_internal_link(full_url):
                    yield response.follow(full_url, callback=self.parse)

            # Check if it's an interactive data portal
            elif self._is_interactive_data(full_url):
                yield self._create_item(
                    "interactive_data",
                    url=full_url,
                    title=self._get_meaningful_title(link_text, full_url),
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                    language=page_language,
                )
                # Also follow the link to crawl the data portal
                if self._is_internal_link(full_url):
                    yield response.follow(full_url, callback=self.parse)

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

        # Check for data tables on this page
        table_count = self._count_data_tables(response.text)
        if table_count > 0:
            yield self._create_item(
                "webpage_with_data",
                url=page_url,
                title=response.css("title::text").get() or "",
                page_section=page_section,
                page_date=page_date,
                language=page_language,
                table_count=table_count,
            )

        # Check for embedded data platforms (iframes with data apps)
        if self._has_embedded_data_platform(response):
            yield self._create_item(
                "interactive_data",
                url=page_url,
                title=response.css("title::text").get() or "",
                page_section=page_section,
                page_date=page_date,
                language=page_language,
            )

    def parse_shiny_app(self, response):
        """Parse a Shiny app page to extract sources."""
        meta = response.meta

        # Extract sources from the Shiny app page
        sources = self._extract_sources_from_shiny(response)

        yield self._create_item(
            "shiny_app",
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

        Combines:
        1. Footer link text extraction (original approach)
        2. Improved general source extraction
        """
        sources = []

        # Strategy 1: Look for footer links with source info (original approach)
        if hasattr(response, 'css'):
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

        # Strategy 2: Use improved general extraction
        if not sources:
            sources = self._extract_sources(None, response)

        return sources

    def _count_data_tables(self, html: str) -> int:
        """Count substantial data tables in HTML.

        A substantial table has at least 3 rows and is not a layout table.
        """
        from scrapy.selector import Selector
        selector = Selector(text=html)

        count = 0
        layout_classes = ["layout", "nav", "menu", "navigation"]

        for table in selector.css("table"):
            # Skip layout tables
            table_classes = table.xpath("@class").get() or ""
            if any(c in table_classes for c in layout_classes):
                continue

            # Count rows
            rows = table.css("tr")
            if len(rows) >= 3:
                count += 1

        return count

    # Patterns indicating embedded data platforms
    EMBEDDED_DATA_INDICATORS = [
        "iFrameContainer",          # Common iframe container ID
        "transparenzplattform",     # Sparzinsen transparency platform
        "data-app",                 # Generic data app containers
        "chart-container",          # Chart containers
        "highcharts-container",     # Highcharts
        "plotly",                   # Plotly charts
    ]

    def _has_embedded_data_platform(self, response) -> bool:
        """Check if page has an embedded data platform (iframe with data app).

        Detects pages like Sparzinsen that load data via iframes.
        """
        if not hasattr(response, 'text'):
            return False

        html = response.text.lower()

        # Check for iframe container patterns
        for indicator in self.EMBEDDED_DATA_INDICATORS:
            if indicator.lower() in html:
                # Verify it's not just a mention in text but actually a container/element
                # Look for id="..." or class="..." patterns
                if f'id="{indicator.lower()}"' in html or f"id='{indicator.lower()}'" in html:
                    return True
                if f'class="{indicator.lower()}"' in html or f"class='{indicator.lower()}'" in html:
                    return True
                # Also check for partial class matches (class="... indicator ...")
                if f' {indicator.lower()}' in html or f'"{indicator.lower()} ' in html:
                    return True

        # Check for iframes pointing to data apps
        for iframe in response.css("iframe[src]"):
            src = iframe.attrib.get("src", "").lower()
            # Check if iframe src looks like a data application
            if any(pattern in src for pattern in ["chart", "report", "data", "statistik", "dashboard"]):
                return True

        return False

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

    def _is_potential_api(self, url: str) -> bool:
        """Check if URL matches any API endpoint pattern.

        Detects URLs containing patterns like /api/, /rest/, /oearb/, /data/
        which may indicate data APIs or endpoints.
        """
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.API_PATTERNS)

    def _is_interactive_data(self, url: str) -> bool:
        """Check if URL is an interactive data portal.

        Detects URLs like /isawebstat/, /dynabfrage/ which are
        interactive statistics/data query interfaces.
        """
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.INTERACTIVE_DATA_PATTERNS)

    def _is_standardized_tables(self, url: str) -> bool:
        """Check if URL is a standardized tables page (data catalog).

        Detects URLs like /Statistik/Standardisierte-Tabellen/ which are
        structured data catalog pages with links to tables, explanations, and charts.
        """
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.STANDARDIZED_TABLES_PATTERNS)

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

    # CSS selectors for source elements (in priority order)
    SOURCE_CSS_SELECTORS = [
        # Specific classes from OeNB pages
        ".footer.quelle",              # isawebstat tables
        ".highcharts-data-source",     # Highcharts/Shiny apps
        "td.quelle",                   # Table cells with quelle class
        ".quelle",                     # Generic quelle class
        ".source",                     # English variant
        ".data-source",                # Common pattern
        # Table footers
        "tfoot td",                    # Any table footer cell
        "table caption",               # Table captions sometimes have sources
        # Figure captions
        "figcaption",
        ".chart-source",
        ".figure-source",
    ]

    def _extract_sources(self, link, response) -> list[str]:
        """Extract source attribution from the page.

        Uses a multi-strategy approach:
        1. CSS selectors for known source elements
        2. Text pattern matching as fallback

        Args:
            link: The link element (kept for backwards compatibility, not used)
            response: The Scrapy response object
        """
        # Strategy 1: CSS selectors for structured source elements
        sources = self._extract_sources_from_selectors(response)
        if sources:
            return sources

        # Strategy 2: Text patterns in the entire page
        sources = self._extract_sources_from_text(response)

        return sources

    def _extract_sources_from_selectors(self, response) -> list[str]:
        """Extract sources from known CSS selectors."""
        sources = []

        # Check if response has css method (may not exist in tests)
        if not hasattr(response, 'css'):
            return sources

        for selector in self.SOURCE_CSS_SELECTORS:
            try:
                elements = response.css(selector)
                # Handle case where css() returns non-iterable (e.g., in tests)
                if not hasattr(elements, '__iter__'):
                    continue
                for elem in elements:
                    # Get all text content
                    if hasattr(elem, 'css'):
                        text = " ".join(elem.css("::text").getall()).strip()
                    else:
                        continue
                    if not text:
                        continue

                    # Check if this looks like a source attribution
                    extracted = self._parse_source_text(text)
                    for src in extracted:
                        if src not in sources:
                            sources.append(src)

                if sources:
                    return sources  # Return as soon as we find sources
            except (TypeError, AttributeError):
                # Skip if selector doesn't work with this response
                continue

        return sources

    def _extract_sources_from_text(self, response) -> list[str]:
        """Extract sources using text pattern matching."""
        sources = []

        if not hasattr(response, 'text'):
            return sources

        page_text = response.text

        # Patterns to match source attributions (German and English)
        source_patterns = [
            r'[Qq]uelle[n]?\s*[:;]\s*([^<\n\.]{2,80})',
            r'[Ss]ource[s]?\s*[:;]\s*([^<\n\.]{2,80})',
            r'[Dd]atenquelle[n]?\s*[:;]\s*([^<\n\.]{2,80})',
            r'[Dd]ata\s+[Ss]ource[s]?\s*[:;]\s*([^<\n\.]{2,80})',
        ]

        for pattern in source_patterns:
            matches = re.findall(pattern, page_text)
            for match in matches:
                extracted = self._parse_source_text(match)
                for src in extracted:
                    if src not in sources:
                        sources.append(src)

        return sources

    def _parse_source_text(self, text: str) -> list[str]:
        """Parse source text and extract clean source names.

        Handles text like:
        - "Quelle: OeNB" -> ["OeNB"]
        - "OeNB, Statistik Austria" -> ["OeNB", "Statistik Austria"]
        - "Quelle: EZB" -> ["EZB"]
        """
        sources = []

        # Remove "Quelle:", "Source:", etc. prefix
        text = re.sub(r'^[Qq]uelle[n]?\s*[:;]\s*', '', text)
        text = re.sub(r'^[Ss]ource[s]?\s*[:;]\s*', '', text)
        text = re.sub(r'^[Dd]atenquelle[n]?\s*[:;]\s*', '', text)

        # Split by common separators
        parts = re.split(r'[,;/&]|\bund\b|\band\b', text)

        for part in parts:
            part = part.strip()
            # Clean up: remove trailing punctuation, whitespace, HTML remnants
            part = re.sub(r'[\.\)\]\s<>]+$', '', part).strip()
            part = re.sub(r'^[\(\[<>]+', '', part).strip()

            # Skip if empty or too short/long
            if not part or len(part) < 2 or len(part) > 50:
                continue

            # Skip common false positives
            skip_words = {'the', 'die', 'der', 'das', 'ein', 'eine', 'und', 'and', 'or', 'oder'}
            if part.lower() in skip_words:
                continue

            # Skip if looks like a URL or path
            if '/' in part or 'http' in part.lower():
                continue

            # Accept if it's a known source
            is_known = any(known.lower() in part.lower() for known in self.KNOWN_SOURCES)
            if is_known:
                sources.append(part)
                continue

            # Accept if it starts with uppercase and looks like a name/org
            if re.match(r'^[A-ZÄÖÜ]', part):
                # Additional validation: should have mostly letters
                letter_ratio = len(re.findall(r'[a-zA-ZäöüÄÖÜß]', part)) / len(part)
                if letter_ratio > 0.7:
                    sources.append(part)

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

    # Type-specific defaults for item creation
    _ITEM_TYPE_DEFAULTS = {
        "download": {
            "file_type": None,  # Computed from URL
            "machine_readable": None,
        },
        "shiny_app": {
            "file_type": "shiny",
            "machine_readable": True,
        },
        "webpage_with_data": {
            "file_type": "html",
            "machine_readable": True,
            "has_tables": True,
            "has_html_tables": True,
        },
        "interactive_data": {
            "file_type": "portal",
            "machine_readable": True,
        },
        "standardized_tables": {
            "file_type": "catalog",
            "machine_readable": True,
        },
    }

    def _create_item(self, item_type: str, **kwargs) -> DownloadItem:
        """Create a DownloadItem of the specified type.

        Args:
            item_type: One of 'download', 'shiny_app', 'webpage_with_data',
                      'interactive_data', 'standardized_tables'
            **kwargs: Item fields (url, title, found_on_page, page_section, etc.)
        """
        defaults = self._ITEM_TYPE_DEFAULTS.get(item_type, {})

        item = DownloadItem()
        item["url"] = kwargs["url"]
        item["type"] = item_type
        item["file_type"] = defaults.get("file_type") or self._get_file_extension(kwargs["url"])
        item["file_size_bytes"] = None
        item["title"] = kwargs.get("title", "")
        item["found_on_page"] = kwargs.get("found_on_page", kwargs["url"])
        # Extract section from item URL (not from where found)
        item["page_section"] = self._extract_section(kwargs["url"])
        item["section_heading"] = kwargs.get("section_heading", "")
        item["page_date"] = kwargs.get("page_date")
        item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
        item["machine_readable"] = defaults.get("machine_readable")
        item["has_tables"] = defaults.get("has_tables")
        item["language"] = kwargs.get("language", "de")
        item["found_in_languages"] = None
        item["sources"] = kwargs.get("sources", [])

        # Type-specific extra fields
        if item_type == "webpage_with_data":
            item["has_html_tables"] = True
            item["table_count"] = kwargs.get("table_count", 0)

        return item
