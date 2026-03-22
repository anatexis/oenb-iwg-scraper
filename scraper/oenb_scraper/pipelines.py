import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import scrapy.exceptions
from scrapy import signals
import requests

from oenb_scraper.isaweb_discovery import classify_isaweb_url
from oenb_scraper.pdf_analyzer import analyze_pdf
from oenb_scraper.resource_classifier import classify_url
from oenb_scraper.urlnorm import normalize_url


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

    def process_item(self, item, spider):
        url = item.get("url")
        # Normalize URL by removing fragment for deduplication
        normalized_url = normalize_url(url)
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
            raise DuplicateUrlDropItem(f"Duplicate URL: {url}")

        # First occurrence - initialize
        item["found_in_languages"] = [language]
        item["link_count"] = 1
        self.seen_urls[normalized_url] = item
        return item


class DuplicateUrlDropItem(scrapy.exceptions.DropItem):
    """Expected duplicate items should not surface as crawler warnings."""

    def __init__(self, message: str):
        super().__init__(message, log_level="DEBUG")


from scrapy import signals
from oenb_scraper.asset_store import store_asset_document
from oenb_scraper.database import (
    finish_crawl_run,
    init_db,
    start_crawl_run,
    store_page,
    store_resource_link,
    store_resource_version,
)
from oenb_scraper.frontier import mark_frontier_crawled, schedule_revisit_after, upsert_frontier_url
from oenb_scraper.isaweb_service import extract_dataset_request, extract_hierarchy_reference
from oenb_scraper.isaweb_store import (
    store_isaweb_content_response,
    store_isaweb_data_response,
    store_isaweb_dataset,
    store_isaweb_meta_response,
    store_isaweb_page_context,
    store_isaweb_release_html_response,
    store_isaweb_report_html_response,
)


class SQLitePipeline:
    """Store pages and bodies in SQLite database using response_received signal."""

    RESOURCE_PRIORITIES = {
        "release_event": 90,
        "isaweb_dataset": 85,
        "isaweb_content": 83,
        "isaweb_entry": 80,
        "dataset_metadata": 78,
        "standardized_table_topic": 70,
        "html_table": 60,
        "shiny_app": 50,
        "asset_document": 40,
        "page_document": 10,
    }

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.run_id = None
        self.stored_urls = set()

    @classmethod
    def from_crawler(cls, crawler):
        db_path = crawler.settings.get("SQLITE_DB_PATH", "data/pages.db")
        pipeline = cls(db_path)
        crawler.signals.connect(pipeline.response_received, signal=signals.response_received)
        return pipeline

    def open_spider(self, spider):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = init_db(self.db_path)
        user_agent = spider.settings.get("USER_AGENT", "unknown")
        self.run_id = start_crawl_run(self.conn, spider.start_urls[0] if spider.start_urls else "", user_agent)
        spider.logger.info(f"SQLitePipeline: DB at {self.db_path}, run_id={self.run_id}")

    def close_spider(self, spider):
        if self.conn and self.run_id:
            finish_crawl_run(self.conn, self.run_id)
            spider.logger.info(f"SQLitePipeline: Stored {len(self.stored_urls)} pages")
            self.conn.close()

    def response_received(self, response, request, spider):
        """Store every HTML response in SQLite."""
        if not self.conn or not self.run_id:
            return

        # Skip /dam/ URLs — binary assets (PDFs, ZIPs) that may arrive via redirects
        # even when the spider didn't explicitly request them.
        if "/dam/" in urlparse(response.url).path:
            return

        content_type = response.headers.get(b"Content-Type", b"").decode("utf-8", errors="ignore")
        normalized_url = normalize_url(response.url)
        materialized_report_dataset = False
        materialized_release_schedule = False

        if self._is_isaweb_data_response(normalized_url, content_type):
            try:
                stored_count = store_isaweb_data_response(
                    self.conn,
                    response_url=normalized_url,
                    xml_text=response.body,
                )
                if stored_count:
                    revisit_after = schedule_revisit_after("isaweb_dataset")
                    upsert_frontier_url(
                        self.conn,
                        normalized_url,
                        priority=self._priority_for_kind("isaweb_dataset"),
                        scope_class=self._scope_class_for_url(normalized_url, spider),
                        resource_kind="isaweb_dataset",
                        revisit_after=revisit_after,
                    )
                    mark_frontier_crawled(
                        self.conn,
                        normalized_url,
                        revisit_after=revisit_after,
                    )
            except Exception as e:
                spider.logger.error(f"SQLitePipeline: Failed to materialize ISAweb XML {normalized_url}: {e}")
            return

        if self._is_isaweb_meta_response(normalized_url, content_type):
            try:
                metadata_id = store_isaweb_meta_response(
                    self.conn,
                    response_url=normalized_url,
                    xml_text=response.body,
                )
                if metadata_id:
                    revisit_after = schedule_revisit_after("dataset_metadata")
                    upsert_frontier_url(
                        self.conn,
                        normalized_url,
                        priority=self._priority_for_kind("dataset_metadata"),
                        scope_class=self._scope_class_for_url(normalized_url, spider),
                        resource_kind="dataset_metadata",
                        revisit_after=revisit_after,
                    )
                    mark_frontier_crawled(
                        self.conn,
                        normalized_url,
                        revisit_after=revisit_after,
                    )
            except Exception as e:
                spider.logger.error(f"SQLitePipeline: Failed to materialize ISAweb meta {normalized_url}: {e}")
            return

        if self._is_isaweb_content_response(normalized_url, content_type):
            try:
                stored_count = store_isaweb_content_response(
                    self.conn,
                    response_url=normalized_url,
                    xml_text=response.body,
                )
                if stored_count:
                    revisit_after = schedule_revisit_after("isaweb_content")
                    upsert_frontier_url(
                        self.conn,
                        normalized_url,
                        priority=self._priority_for_kind("isaweb_content"),
                        scope_class=self._scope_class_for_url(normalized_url, spider),
                        resource_kind="isaweb_content",
                        revisit_after=revisit_after,
                    )
                    mark_frontier_crawled(
                        self.conn,
                        normalized_url,
                        revisit_after=revisit_after,
                    )
            except Exception as e:
                spider.logger.error(f"SQLitePipeline: Failed to materialize ISAweb content {normalized_url}: {e}")
            return

        if self._is_asset_response(normalized_url, content_type):
            try:
                page_id = store_page(
                    self.conn,
                    run_id=self.run_id,
                    url=normalized_url,
                    final_url=response.url,
                    status_code=response.status,
                    content_type=content_type,
                    body=response.body,
                )
                store_asset_document(
                    self.conn,
                    page_id=page_id,
                    url=normalized_url,
                    content_type=content_type,
                    body=response.body,
                )
                store_resource_version(
                    self.conn,
                    url=normalized_url,
                    body_hash=self._body_hash(response.body),
                    status_code=response.status,
                )
                revisit_after = schedule_revisit_after("asset_document")
                upsert_frontier_url(
                    self.conn,
                    normalized_url,
                    priority=self._priority_for_kind("asset_document"),
                    scope_class=self._scope_class_for_url(normalized_url, spider),
                    resource_kind="asset_document",
                    revisit_after=revisit_after,
                )
                mark_frontier_crawled(
                    self.conn,
                    normalized_url,
                    revisit_after=revisit_after,
                )
            except Exception as e:
                spider.logger.error(f"SQLitePipeline: Failed to materialize asset {normalized_url}: {e}")
            return

        # Only store HTML pages, skip downloads/binaries
        if "text/html" not in content_type:
            return

        if self._is_isaweb_report_html_response(normalized_url, content_type):
            try:
                dataset_id = store_isaweb_report_html_response(
                    self.conn,
                    response_url=normalized_url,
                    html_text=response.body,
                )
                materialized_report_dataset = bool(dataset_id)
            except Exception as e:
                spider.logger.error(
                    f"SQLitePipeline: Failed to materialize ISAweb report HTML {normalized_url}: {e}"
                )

        if self._is_isaweb_release_html_response(normalized_url, content_type):
            try:
                metadata_id = store_isaweb_release_html_response(
                    self.conn,
                    response_url=normalized_url,
                    html_text=response.body,
                )
                materialized_release_schedule = bool(metadata_id)
            except Exception as e:
                spider.logger.error(
                    f"SQLitePipeline: Failed to materialize ISAweb release HTML {normalized_url}: {e}"
                )

        if normalized_url in self.stored_urls:
            return
        self.stored_urls.add(normalized_url)

        try:
            store_page(
                self.conn,
                run_id=self.run_id,
                url=normalized_url,           # Store normalized URL
                final_url=response.url,       # Keep original as final_url
                status_code=response.status,
                content_type=content_type,
                body=response.body,
            )
            if materialized_release_schedule:
                resource_kind = "release_event"
            elif materialized_report_dataset:
                resource_kind = "isaweb_dataset"
            else:
                resource_kind = "page_document"
            revisit_after = schedule_revisit_after(resource_kind)
            upsert_frontier_url(
                self.conn,
                normalized_url,
                priority=self._priority_for_kind(resource_kind),
                scope_class=self._scope_class_for_url(normalized_url, spider),
                resource_kind=resource_kind,
                revisit_after=revisit_after,
            )
            mark_frontier_crawled(
                self.conn,
                normalized_url,
                revisit_after=revisit_after,
            )
        except Exception as e:
            spider.logger.error(f"SQLitePipeline: Failed to store {normalized_url}: {e}")

    def process_item(self, item, spider):
        """Persist item-level resource links when DB storage is enabled."""
        if self.conn:
            source_url = item.get("found_on_page")
            target_url = item.get("url")
            effective_resource_kind = self._effective_resource_kind(item)
            if source_url and target_url and source_url != target_url:
                try:
                    store_resource_link(
                        self.conn,
                        source_url=source_url,
                        target_url=target_url,
                        normalized_target_url=normalize_url(target_url),
                        link_text=item.get("title"),
                        section_heading=item.get("section_heading"),
                        resource_kind=effective_resource_kind,
                        embed_type="item",
                    )
                except Exception as e:
                    spider.logger.error(f"SQLitePipeline: Failed to store resource link {source_url} -> {target_url}: {e}")
                try:
                    store_isaweb_page_context(
                        self.conn,
                        source_url=source_url,
                        target_url=target_url,
                        link_text=item.get("title"),
                        section_heading=item.get("section_heading"),
                        relation_kind=effective_resource_kind,
                        fallback_lang=item.get("language"),
                    )
                except Exception as e:
                    spider.logger.error(
                        f"SQLitePipeline: Failed to store ISAweb page context {source_url} -> {target_url}: {e}"
                    )
            if target_url:
                try:
                    normalized_target_url = normalize_url(target_url)
                    upsert_frontier_url(
                        self.conn,
                        normalized_target_url,
                        priority=self._priority_for_kind(effective_resource_kind),
                        scope_class=self._scope_class_for_url(normalized_target_url, spider),
                        resource_kind=effective_resource_kind,
                    )
                except Exception as e:
                    spider.logger.error(f"SQLitePipeline: Failed to update frontier for {target_url}: {e}")
                dataset_request = extract_dataset_request(target_url, fallback_lang=item.get("language"))
                if dataset_request is not None:
                    try:
                        upsert_frontier_url(
                            self.conn,
                            dataset_request.data_url,
                            priority=self._priority_for_kind("isaweb_dataset"),
                            scope_class=self._scope_class_for_url(dataset_request.data_url, spider),
                            resource_kind="isaweb_dataset",
                        )
                        upsert_frontier_url(
                            self.conn,
                            dataset_request.meta_url,
                            priority=self._priority_for_kind("dataset_metadata"),
                            scope_class=self._scope_class_for_url(dataset_request.meta_url, spider),
                            resource_kind="dataset_metadata",
                        )
                        upsert_frontier_url(
                            self.conn,
                            dataset_request.content_url,
                            priority=self._priority_for_kind("isaweb_content"),
                            scope_class=self._scope_class_for_url(dataset_request.content_url, spider),
                            resource_kind="isaweb_content",
                        )
                        store_isaweb_dataset(
                            self.conn,
                            hierid=dataset_request.hierid,
                            lang=dataset_request.lang,
                            pos=dataset_request.pos,
                            dimensions=dataset_request.dimensions,
                            freq=dataset_request.freq,
                            title=item.get("title"),
                            source_url=normalize_url(target_url),
                        )
                    except Exception as e:
                        spider.logger.error(
                            f"SQLitePipeline: Failed to store ISAweb dataset from {target_url}: {e}"
                        )
                else:
                    hierarchy_reference = extract_hierarchy_reference(target_url, fallback_lang=item.get("language"))
                    if hierarchy_reference is not None:
                        try:
                            upsert_frontier_url(
                                self.conn,
                                hierarchy_reference.content_url,
                                priority=self._priority_for_kind("isaweb_content"),
                                scope_class=self._scope_class_for_url(hierarchy_reference.content_url, spider),
                                resource_kind="isaweb_content",
                            )
                        except Exception as e:
                            spider.logger.error(
                                f"SQLitePipeline: Failed to update ISAweb content frontier for {target_url}: {e}"
                            )
        return item

    def _effective_resource_kind(self, item) -> str | None:
        resource_kind = item.get("resource_kind")
        target_url = item.get("url")
        if not target_url:
            return resource_kind

        isaweb_info = classify_isaweb_url(target_url)
        if isaweb_info and isaweb_info.kind == "release":
            return "release_event"
        return resource_kind

    def _priority_for_kind(self, resource_kind: str | None) -> int:
        return self.RESOURCE_PRIORITIES.get(resource_kind or "", 0)

    def _scope_class_for_url(self, url: str, spider) -> str | None:
        crawl_scope = getattr(spider, "crawl_scope", None)
        if crawl_scope is None:
            return None
        host = urlparse(url).netloc
        if not host:
            return None
        scope_class = crawl_scope.classify_host(host)
        if scope_class in {"primary", "secondary", "out_of_scope"}:
            return scope_class
        return None

    def _is_isaweb_data_response(self, url: str, content_type: str) -> bool:
        return "/isadataservice/data" in urlparse(url).path.lower() and "xml" in content_type.lower()

    def _is_isaweb_meta_response(self, url: str, content_type: str) -> bool:
        return "/isadataservice/meta" in urlparse(url).path.lower() and "xml" in content_type.lower()

    def _is_isaweb_content_response(self, url: str, content_type: str) -> bool:
        return "/isadataservice/content" in urlparse(url).path.lower() and "xml" in content_type.lower()

    def _is_isaweb_report_html_response(self, url: str, content_type: str) -> bool:
        return "/isawebstat/stabfrage/createreport" in urlparse(url).path.lower() and "text/html" in content_type.lower()

    def _is_isaweb_release_html_response(self, url: str, content_type: str) -> bool:
        return "/isawebstat/releasekalender/showreleaseforreport" in urlparse(url).path.lower() and "text/html" in content_type.lower()

    def _is_asset_response(self, url: str, content_type: str) -> bool:
        if "text/html" in content_type.lower():
            return False
        return classify_url(url).kind == "asset_document"

    def _body_hash(self, body: bytes | None) -> str | None:
        if not body:
            return None
        return hashlib.sha256(body).hexdigest()
