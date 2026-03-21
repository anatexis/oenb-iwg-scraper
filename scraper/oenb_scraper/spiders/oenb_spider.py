import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import scrapy

from oenb_scraper.database import init_db
from oenb_scraper.frontier import get_due_frontier_urls, get_open_isaweb_report_urls
from oenb_scraper.isaweb_discovery import classify_isaweb_url
from oenb_scraper.isaweb_resolver import extract_isaweb_urls_from_html, resolve_dataset_request_from_html
from oenb_scraper.isaweb_service import extract_dataset_request, extract_hierarchy_reference
from oenb_scraper.items import DownloadItem
from oenb_scraper.items import LEGACY_TYPE_TO_RESOURCE_KIND
from oenb_scraper.resource_classifier import classify_url
from oenb_scraper.scope import CrawlScope
from oenb_scraper.source_extraction import SourceMetadata, extract_source_metadata, extract_source_names
from oenb_scraper.urlnorm import normalize_url


def _merge_source_metadata(target: SourceMetadata, incoming: SourceMetadata, fallback_method: str | None = None) -> None:
    for source in incoming.sources:
        if source not in target.sources:
            target.sources.append(source)
    for entry in incoming.source_links:
        if entry not in target.source_links:
            target.source_links.append(entry)
    for raw_text in incoming.source_text_raw:
        if raw_text not in target.source_text_raw:
            target.source_text_raw.append(raw_text)
    for institution in incoming.reporting_institutions:
        if institution not in target.reporting_institutions:
            target.reporting_institutions.append(institution)

    if not target.source_extraction_method:
        target.source_extraction_method = incoming.source_extraction_method or fallback_method


class OenbSpider(scrapy.Spider):
    name = "oenb"
    allowed_domains = ["oenb.at", "www.oenb.at", "finanzbildung.oenb.at"]
    start_urls = [
        "https://www.oenb.at/",
        "https://www.oenb.at/Service/Sitemap.html",
        "https://finanzbildung.oenb.at/",
    ]

    def __init__(
        self,
        section=None,
        use_frontier=False,
        frontier_db_path=None,
        frontier_now=None,
        frontier_limit=100,
        frontier_kinds=None,
        isaweb_focus=False,
        *args,
        **kwargs,
    ):
        """Initialize spider with optional section filter.

        Args:
            section: URL path prefix to limit crawl (e.g., 'Statistik' or 'Statistik.html')
        """
        super().__init__(*args, **kwargs)
        self.crawl_scope = CrawlScope(
            primary_hosts={"oenb.at", "www.oenb.at", "finanzbildung.oenb.at", "shiny.oenb.at"},
            secondary_host_suffixes={"shinyapps.io"},
        )
        self.section_filter = None
        self.use_frontier = self._as_bool(use_frontier)
        self.frontier_db_path = frontier_db_path
        self.frontier_now = frontier_now
        self.frontier_limit = int(frontier_limit)
        self.frontier_kinds = self._parse_frontier_kinds(frontier_kinds)
        self.isaweb_focus = self._as_bool(isaweb_focus)
        if section:
            # Normalize: remove .html, ensure starts with /
            section = section.replace(".html", "").strip("/")
            self.section_filter = f"/{section}"
            self.start_urls = self._section_start_urls(section)
            self.logger.info(f"Section filter active: only crawling URLs under {self.section_filter}")

    def start_requests(self):
        frontier_urls = self._get_frontier_seed_urls()
        if frontier_urls:
            for url in frontier_urls:
                yield scrapy.Request(
                    url,
                    callback=self._callback_for_url(url),
                    priority=100,
                )
            return

        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)

    def _section_start_urls(self, section: str) -> list[str]:
        normalized = section.lower()
        if normalized == "statistics":
            return ["https://www.oenb.at/en/Statistics/Standardized-Tables.html"]
        return [f"https://www.oenb.at/{section}.html"]

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
        page_source_metadata = self._extract_source_metadata(response)
        seen_isaweb_urls: set[str] = set()
        normalized_page_url = normalize_url(page_url)

        resolved_dataset_request = resolve_dataset_request_from_html(
            page_url,
            response.text,
            fallback_lang=page_language,
        )
        if resolved_dataset_request is not None:
            yield scrapy.Request(resolved_dataset_request.content_url, callback=self.parse_isaweb_content)
            yield scrapy.Request(resolved_dataset_request.data_url, callback=self.parse_isaweb_data)
            yield scrapy.Request(resolved_dataset_request.meta_url, callback=self.parse_isaweb_meta)
        else:
            page_hierarchy_reference = extract_hierarchy_reference(page_url, fallback_lang=page_language)
            if page_hierarchy_reference is not None:
                yield scrapy.Request(page_hierarchy_reference.content_url, callback=self.parse_isaweb_content)

        # Find all links on the page
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            full_url = urljoin(page_url, href)
            link_text = link.css("::text").get() or ""
            link_text = link_text.strip()
            item_title = self._get_meaningful_title(link_text, full_url)
            section_heading = self._find_section_heading(link, response)

            # Check if it's a download
            if self._is_download(full_url):
                yield self._create_item(
                    "download",
                    url=full_url,
                    title=item_title,
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=section_heading,
                    page_date=page_date,
                    language=page_language,
                    sources=page_source_metadata.sources,
                    source_links=page_source_metadata.source_links,
                    source_text_raw=page_source_metadata.source_text_raw,
                    reporting_institutions=page_source_metadata.reporting_institutions,
                    source_extraction_method=page_source_metadata.source_extraction_method,
                )
                if not self.isaweb_focus and self._should_fetch_asset(
                    full_url,
                    title=item_title,
                    page_section=page_section,
                    section_heading=section_heading,
                ):
                    yield scrapy.Request(full_url, callback=self.parse_asset_document)

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
                    sources=page_source_metadata.sources,
                    source_links=page_source_metadata.source_links,
                    source_text_raw=page_source_metadata.source_text_raw,
                    reporting_institutions=page_source_metadata.reporting_institutions,
                    source_extraction_method=page_source_metadata.source_extraction_method,
                )
                # Also follow the link to crawl for downloads
                if self._should_follow_link(full_url):
                    yield response.follow(full_url, callback=self.parse)

            # Check if it's an interactive data portal
            elif self._is_interactive_data(full_url):
                seen_isaweb_urls.add(normalize_url(full_url))
                yield self._create_item(
                    "interactive_data",
                    url=full_url,
                    title=self._get_meaningful_title(link_text, full_url),
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                    language=page_language,
                    sources=page_source_metadata.sources,
                    source_links=page_source_metadata.source_links,
                    source_text_raw=page_source_metadata.source_text_raw,
                    reporting_institutions=page_source_metadata.reporting_institutions,
                    source_extraction_method=page_source_metadata.source_extraction_method,
                )
                dataset_request = extract_dataset_request(full_url, fallback_lang=page_language)
                if dataset_request is not None:
                    yield scrapy.Request(dataset_request.content_url, callback=self.parse_isaweb_content)
                    yield scrapy.Request(dataset_request.data_url, callback=self.parse_isaweb_data)
                    yield scrapy.Request(dataset_request.meta_url, callback=self.parse_isaweb_meta)
                else:
                    hierarchy_reference = extract_hierarchy_reference(full_url, fallback_lang=page_language)
                    if hierarchy_reference is not None:
                        yield scrapy.Request(hierarchy_reference.content_url, callback=self.parse_isaweb_content)
                # Also follow the link to crawl the data portal
                if self._should_follow_interactive_data_link(full_url):
                    yield response.follow(full_url, callback=self.parse)

            # Follow internal links
            elif self._should_follow_link(full_url):
                yield response.follow(full_url, callback=self.parse)

        for embedded_url in extract_isaweb_urls_from_html(page_url, response.text):
            normalized_embedded_url = normalize_url(embedded_url)
            if normalized_embedded_url in seen_isaweb_urls or normalized_embedded_url == normalized_page_url:
                continue
            seen_isaweb_urls.add(normalized_embedded_url)

            dataset_request = extract_dataset_request(embedded_url, fallback_lang=page_language)
            if dataset_request is not None:
                yield scrapy.Request(dataset_request.content_url, callback=self.parse_isaweb_content)
                yield scrapy.Request(dataset_request.data_url, callback=self.parse_isaweb_data)
                yield scrapy.Request(dataset_request.meta_url, callback=self.parse_isaweb_meta)
            else:
                hierarchy_reference = extract_hierarchy_reference(embedded_url, fallback_lang=page_language)
                if hierarchy_reference is not None:
                    yield scrapy.Request(hierarchy_reference.content_url, callback=self.parse_isaweb_content)

            if self._is_interactive_data(embedded_url):
                yield self._create_item(
                    "interactive_data",
                    url=embedded_url,
                    title=self._get_meaningful_title("", embedded_url),
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading="",
                    page_date=page_date,
                    language=page_language,
                    sources=page_source_metadata.sources,
                    source_links=page_source_metadata.source_links,
                    source_text_raw=page_source_metadata.source_text_raw,
                    reporting_institutions=page_source_metadata.reporting_institutions,
                    source_extraction_method=page_source_metadata.source_extraction_method,
                )

            if self._is_interactive_data(embedded_url) and self._should_follow_interactive_data_link(embedded_url):
                yield response.follow(embedded_url, callback=self.parse)

        # Also check iframes for embedded Shiny apps
        for iframe in response.css("iframe[src]"):
            src = iframe.attrib.get("src", "")
            if not self.isaweb_focus and self._is_shiny_app(src):
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
                sources=page_source_metadata.sources,
                source_links=page_source_metadata.source_links,
                source_text_raw=page_source_metadata.source_text_raw,
                reporting_institutions=page_source_metadata.reporting_institutions,
                source_extraction_method=page_source_metadata.source_extraction_method,
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
                sources=page_source_metadata.sources,
                source_links=page_source_metadata.source_links,
                source_text_raw=page_source_metadata.source_text_raw,
                reporting_institutions=page_source_metadata.reporting_institutions,
                source_extraction_method=page_source_metadata.source_extraction_method,
            )

    def parse_shiny_app(self, response):
        """Parse a Shiny app page to extract sources."""
        meta = response.meta

        source_metadata = self._extract_source_metadata(response)

        yield self._create_item(
            "shiny_app",
            url=meta["shiny_url"],
            title=meta["title"],
            found_on_page=meta["found_on_page"],
            page_section=meta["page_section"],
            section_heading=meta["section_heading"],
            page_date=meta["page_date"],
            language=meta["language"],
            sources=source_metadata.sources,
            source_links=source_metadata.source_links,
            source_text_raw=source_metadata.source_text_raw,
            reporting_institutions=source_metadata.reporting_institutions,
            source_extraction_method=source_metadata.source_extraction_method,
        )

    def parse_asset_document(self, response):
        """Asset responses are handled in the pipeline; no page parsing here."""
        return

    def parse_isaweb_data(self, response):
        """ISAweb data responses are handled in the pipeline; no HTML parsing here."""
        return

    def parse_isaweb_content(self, response):
        """ISAweb content responses are handled in the pipeline; no HTML parsing here."""
        return

    def parse_isaweb_meta(self, response):
        """ISAweb meta responses are handled in the pipeline; no HTML parsing here."""
        return

    def _extract_source_metadata(self, response) -> SourceMetadata:
        """Extract structured source metadata from a response."""
        if not hasattr(response, "text"):
            return SourceMetadata()

        metadata = extract_source_metadata(response.text)

        # Legacy Shiny footer patterns often surface as plain text selectors.
        if hasattr(response, "css"):
            try:
                footer_links = response.css(".footer-link::text, .source-link::text, footer a::text").getall()
            except (TypeError, AttributeError):
                footer_links = []
            for text in footer_links:
                _merge_source_metadata(metadata, extract_source_metadata(text.strip()), fallback_method="footer-text")

        return metadata

    def _extract_sources_from_shiny(self, response) -> list[str]:
        """Extract sources from Shiny app HTML.

        Combines:
        1. Footer link text extraction (original approach)
        2. Improved general source extraction
        """
        metadata = self._extract_source_metadata(response)
        return metadata.sources

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
    FETCHABLE_ASSET_SUBTYPES = {"csv", "xlsx", "xls", "xml", "json", "zip", "geojson", "txt", "rdf", "ttl", "ods", "kml", "gml"}
    DEEP_DOCUMENT_SUBTYPES = {"pdf", "docx", "pptx", "doc", "ppt"}
    DOCUMENT_PRIORITY_KEYWORDS = {
        "statistics", "statistik", "standardized", "standardisierte",
        "table", "tabelle", "explanatory", "erläuter", "metadata", "method",
        "methodik", "release", "publication", "publikation", "inflation",
        "interest", "zins", "wechselkurs", "exchange", "financial", "bank",
        "preise", "competitiveness", "leitzins", "isaweb",
    }

    def _is_download(self, url: str) -> bool:
        """Check if URL points to a downloadable file.

        Checks both:
        - File extension in path (e.g., /file.csv)
        - Format query parameter (e.g., ?format=CSV)
        """
        return classify_url(url).kind == "asset_document"

    def _is_shiny_app(self, url: str) -> bool:
        """Check if URL is a Shiny app."""
        return classify_url(url).kind == "shiny_app"

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
        return classify_url(url).kind == "isaweb_entry"

    def _is_standardized_tables(self, url: str) -> bool:
        """Check if URL is a standardized tables page (data catalog).

        Detects URLs like /Statistik/Standardisierte-Tabellen/ which are
        structured data catalog pages with links to tables, explanations, and charts.
        """
        return classify_url(url).kind == "standardized_table_topic"

    def _is_internal_link(self, url: str) -> bool:
        """Check if URL is internal to oenb.at, uses http(s), and matches section filter."""
        if not self._is_in_scope_http_link(url):
            return False
        # Apply section filter if set
        parsed = urlparse(url)
        if self.section_filter:
            if not self._path_matches_section_filter(parsed.path):
                return False
        return True

    def _is_in_scope_http_link(self, url: str) -> bool:
        """Check URL scheme and host scope without applying the section filter."""
        parsed = urlparse(url)
        # Only follow http/https links
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return False
        if parsed.netloc and self.crawl_scope.classify_host(parsed.netloc) == "out_of_scope":
            return False
        return True

    def _should_follow_link(self, url: str) -> bool:
        if not self._is_internal_link(url):
            return False
        if not self.isaweb_focus:
            return True
        return self._is_isaweb_focus_target(url)

    def _should_follow_interactive_data_link(self, url: str) -> bool:
        if self._should_follow_link(url):
            return True
        if self.isaweb_focus:
            return False
        classified = classify_url(url)
        return (
            self._is_in_scope_http_link(url)
            and classified.kind == "isaweb_entry"
            and classified.subtype in {"report", "chart", "release"}
        )

    def _is_isaweb_focus_target(self, url: str) -> bool:
        path = urlparse(url).path.lower().rstrip("/")
        if "/isadataservice/" in path:
            return True
        return any(marker in path for marker in ("createreport", "createchart"))

    def _path_matches_section_filter(self, path: str) -> bool:
        path = (path or "").lower()
        section = (self.section_filter or "").lower()
        if path.startswith(section):
            return True
        if path.startswith("/en/"):
            localized_path = path[3:]
            return localized_path.startswith(section)
        return False

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

    def _get_frontier_seed_urls(self) -> list[str]:
        if not self.use_frontier or not self.frontier_db_path:
            return []

        db_path = Path(self.frontier_db_path)
        conn = init_db(db_path)
        try:
            prioritized_urls: list[str] = []
            if self.isaweb_focus:
                prioritized_urls = get_open_isaweb_report_urls(conn, limit=self.frontier_limit)
            rows = get_due_frontier_urls(
                conn,
                now=self.frontier_now,
                limit=self.frontier_limit,
                resource_kinds=self.frontier_kinds,
            )
        finally:
            conn.close()

        urls = prioritized_urls + [row["url"] for row in rows]
        if self.isaweb_focus:
            urls = [url for url in urls if self._is_isaweb_focus_target(url)]
        deduped_urls: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            deduped_urls.append(url)
            if len(deduped_urls) >= self.frontier_limit:
                break
        return deduped_urls

    def _parse_frontier_kinds(self, value) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            values = [str(entry).strip() for entry in value if str(entry).strip()]
            return values or None
        values = [entry.strip() for entry in str(value).split(",") if entry.strip()]
        return values or None

    def _callback_for_url(self, url: str):
        if classify_url(url).kind == "asset_document":
            return self.parse_asset_document
        if "/isadataservice/content" in urlparse(url).path.lower():
            return self.parse_isaweb_content
        if "/isadataservice/data" in urlparse(url).path.lower():
            return self.parse_isaweb_data
        if "/isadataservice/meta" in urlparse(url).path.lower():
            return self.parse_isaweb_meta
        return self.parse

    def _find_section_heading(self, link, response) -> str:
        """Find the nearest heading above the link."""
        # Try to find preceding h1, h2, h3
        for heading in ["h1", "h2", "h3"]:
            headings = response.css(f"{heading}::text").getall()
            if headings:
                return headings[-1].strip()
        return ""

    def _as_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _extract_sources(self, link, response) -> list[str]:
        """Extract source attribution from the page.

        Uses a multi-strategy approach:
        1. CSS selectors for known source elements
        2. Text pattern matching as fallback

        Args:
            link: The link element (kept for backwards compatibility, not used)
            response: The Scrapy response object
        """
        return self._extract_source_metadata(response).sources

    def _parse_source_text(self, text: str) -> list[str]:
        """Parse source text and extract clean source names.

        Handles text like:
        - "Quelle: OeNB" -> ["OeNB"]
        - "OeNB, Statistik Austria" -> ["OeNB", "Statistik Austria"]
        - "Quelle: EZB" -> ["EZB"]
        """
        return extract_source_names(text)

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

    def _should_fetch_asset(
        self,
        url: str,
        *,
        title: str = "",
        page_section: str = "",
        section_heading: str = "",
    ) -> bool:
        classified = classify_url(url)
        if classified.kind != "asset_document":
            return False
        if not self._is_internal_link(url):
            return False
        if classified.subtype in self.FETCHABLE_ASSET_SUBTYPES:
            return True
        if classified.subtype not in self.DEEP_DOCUMENT_SUBTYPES:
            return False
        context = " ".join(part for part in [title, page_section, section_heading, url] if part).lower()
        return any(keyword in context for keyword in self.DOCUMENT_PRIORITY_KEYWORDS)

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
        item["url"] = normalize_url(kwargs["url"])
        item["type"] = item_type
        item["file_type"] = defaults.get("file_type") or self._get_file_extension(kwargs["url"])
        item["file_size_bytes"] = None
        item["title"] = kwargs.get("title", "")
        item["found_on_page"] = normalize_url(kwargs.get("found_on_page", kwargs["url"]))
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
        item["source_links"] = kwargs.get("source_links", [])
        item["source_text_raw"] = kwargs.get("source_text_raw", [])
        item["reporting_institutions"] = kwargs.get("reporting_institutions", [])
        item["source_extraction_method"] = kwargs.get("source_extraction_method")
        item["source_urls"] = [entry["url"] for entry in item["source_links"]]
        item["resource_kind"] = LEGACY_TYPE_TO_RESOURCE_KIND.get(item_type)
        if item_type == "interactive_data":
            isaweb_info = classify_isaweb_url(item["url"])
            if isaweb_info and isaweb_info.kind == "release":
                item["resource_kind"] = "release_event"

        # Type-specific extra fields
        if item_type == "webpage_with_data":
            item["has_html_tables"] = True
            item["table_count"] = kwargs.get("table_count", 0)

        return item
