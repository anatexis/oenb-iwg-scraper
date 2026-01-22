import hashlib
import json
from datetime import datetime
from pathlib import Path

import scrapy.exceptions
from scrapy import signals
import requests

from oenb_scraper.pdf_analyzer import analyze_pdf


class FailedUrlLogger:
    """Extension to log failed URLs and HTTP errors to a separate file."""

    def __init__(self, output_path):
        self.output_path = Path(output_path)
        self.failed_urls = []
        self.http_errors = []

    @classmethod
    def from_crawler(cls, crawler):
        # Create timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output_path = Path(__file__).parent.parent.parent / "data" / f"{timestamp}_failed_urls.json"

        ext = cls(output_path)

        # Connect to signals
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.request_failed, signal=signals.request_dropped)
        crawler.signals.connect(ext.response_received, signal=signals.response_received)

        return ext

    def spider_opened(self, spider):
        spider.logger.info(f"FailedUrlLogger: Will write to {self.output_path}")

    def request_failed(self, request, spider):
        """Called when a request fails or is dropped."""
        self.failed_urls.append({
            "url": request.url,
            "reason": str(request.meta.get("reason", "unknown")),
            "timestamp": datetime.now().isoformat(),
        })

    def response_received(self, response, request, spider):
        """Called for every response - capture HTTP errors (4xx, 5xx)."""
        if response.status >= 400:
            self.http_errors.append({
                "url": response.url,
                "status": response.status,
                "found_on": request.meta.get("referer", "unknown"),
                "timestamp": datetime.now().isoformat(),
            })

    def spider_closed(self, spider, reason):
        """Save all failed URLs and HTTP errors when spider closes."""
        # Collect stats about HTTP errors
        stats = spider.crawler.stats.get_stats()

        error_counts = {}
        for key, value in stats.items():
            if key.startswith("downloader/response_status_count/"):
                status_code = key.split("/")[-1]
                if status_code.startswith("4") or status_code.startswith("5"):
                    error_counts[status_code] = value

        error_summary = {
            "total_dropped_requests": len(self.failed_urls),
            "total_http_errors": len(self.http_errors),
            "http_error_counts": error_counts,
            "spider_close_reason": reason,
        }

        output = {
            "summary": error_summary,
            "dropped_requests": self.failed_urls,
            "http_errors": self.http_errors,
        }

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        spider.logger.info(
            f"FailedUrlLogger: Saved {len(self.failed_urls)} dropped requests "
            f"and {len(self.http_errors)} HTTP errors to {self.output_path}"
        )

# Cache directory for PDF analysis results
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / ".pdf_cache"


class FileSizePipeline:
    """Fetch file size via HEAD request."""

    def process_item(self, item, spider):
        if item.get("type") == "download" and item.get("file_size_bytes") is None:
            try:
                response = requests.head(item["url"], timeout=10, allow_redirects=True)
                size = response.headers.get("Content-Length")
                if size:
                    item["file_size_bytes"] = int(size)
            except Exception:
                pass  # Size remains None
        return item


class PdfAnalysisPipeline:
    """Analyze PDFs for machine readability with caching."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()

    def _cache_key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _load_cache(self) -> dict:
        cache_file = CACHE_DIR / "pdf_analysis.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        cache_file = CACHE_DIR / "pdf_analysis.json"
        cache_file.write_text(json.dumps(self.cache))

    def process_item(self, item, spider):
        if item.get("file_type") == "pdf" and item.get("machine_readable") is None:
            url = item["url"]
            key = self._cache_key(url)

            # Check cache first
            if key in self.cache:
                cached = self.cache[key]
                item["machine_readable"] = cached["machine_readable"]
                item["has_tables"] = cached["has_tables"]
                spider.logger.debug(f"PDF from cache: {url}")
            else:
                # Analyze and cache
                spider.logger.info(f"Analyzing PDF: {url}")
                result = analyze_pdf(url)
                item["machine_readable"] = result["machine_readable"]
                item["has_tables"] = result["has_tables"]

                # Save to cache
                self.cache[key] = {
                    "machine_readable": result["machine_readable"],
                    "has_tables": result["has_tables"],
                }
                self._save_cache()

                if result["error"]:
                    spider.logger.warning(f"PDF analysis error: {result['error']}")
        return item


class DeduplicationPipeline:
    """Track duplicate URLs and mark items found in multiple languages."""

    def __init__(self):
        self.seen_urls = {}  # url -> item reference

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication.

        Removes:
        - Fragment (#...)
        - Session IDs (jsessionid, PHPSESSID, etc.)
        - Sorts query parameters for consistent comparison
        """
        from urllib.parse import urldefrag, urlparse, parse_qs, urlencode

        # Remove fragment
        url = urldefrag(url)[0]

        parsed = urlparse(url)

        # Remove jsessionid from path (e.g., /page;jsessionid=ABC123)
        path = parsed.path
        if ';jsessionid=' in path:
            path = path.split(';jsessionid=')[0]
        if ';JSESSIONID=' in path:
            path = path.split(';JSESSIONID=')[0]

        # Parse and filter query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=False)

        # Remove session-related query parameters
        session_params = {'jsessionid', 'JSESSIONID', 'PHPSESSID', 'sid', 'session_id'}
        filtered_params = {k: v for k, v in query_params.items() if k not in session_params}

        # Sort parameters and rebuild query string
        sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

        # Rebuild URL
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if sorted_query:
            normalized += f"?{sorted_query}"

        return normalized

    def process_item(self, item, spider):
        url = item.get("url")
        # Normalize URL by removing fragment for deduplication
        normalized_url = self._normalize_url(url)
        # Store the clean URL in the item
        item["url"] = normalized_url
        language = item.get("language", "de")

        if normalized_url in self.seen_urls:
            # URL already seen - update the original item
            original_item = self.seen_urls[normalized_url]

            # Track link count
            original_item["link_count"] = original_item.get("link_count", 1) + 1

            # Track languages
            existing_languages = original_item.get("found_in_languages") or []
            if language not in existing_languages:
                existing_languages.append(language)
                original_item["found_in_languages"] = existing_languages

            # Merge sources from duplicate
            existing_sources = original_item.get("sources") or []
            new_sources = item.get("sources") or []
            for src in new_sources:
                if src not in existing_sources:
                    existing_sources.append(src)
            original_item["sources"] = existing_sources

            spider.logger.debug(f"Duplicate URL (count: {original_item['link_count']}): {url}")
            raise scrapy.exceptions.DropItem(f"Duplicate URL: {url}")

        # First occurrence - initialize
        item["found_in_languages"] = [language]
        item["link_count"] = 1
        self.seen_urls[normalized_url] = item
        return item


from oenb_scraper.database import init_db, start_crawl_run, finish_crawl_run, store_page


class SQLitePipeline:
    """Store pages and bodies in SQLite database."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.run_id = None

    @classmethod
    def from_crawler(cls, crawler):
        db_path = crawler.settings.get("SQLITE_DB_PATH", "data/pages.db")
        return cls(db_path)

    def open_spider(self, spider):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = init_db(self.db_path)
        user_agent = spider.settings.get("USER_AGENT", "unknown")
        self.run_id = start_crawl_run(self.conn, spider.start_urls[0] if spider.start_urls else "", user_agent)
        spider.logger.info(f"SQLitePipeline: DB at {self.db_path}, run_id={self.run_id}")

    def close_spider(self, spider):
        if self.conn and self.run_id:
            finish_crawl_run(self.conn, self.run_id)
            self.conn.close()

    def process_item(self, item, spider, response=None):
        """Store page if we have a response."""
        if response and hasattr(response, 'body'):
            store_page(
                self.conn,
                run_id=self.run_id,
                url=item.get("url", response.url),
                final_url=response.url,
                status_code=response.status,
                content_type=response.headers.get(b"Content-Type", [b""])[0].decode("utf-8", errors="ignore"),
                body=response.body,
            )
        return item
