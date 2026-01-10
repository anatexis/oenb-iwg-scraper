import hashlib
import json
from pathlib import Path

import scrapy.exceptions
import requests

from oenb_scraper.pdf_analyzer import analyze_pdf

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
    """Remove duplicate URLs."""

    def __init__(self):
        self.seen_urls = set()

    def process_item(self, item, spider):
        url = item.get("url")
        if url in self.seen_urls:
            raise scrapy.exceptions.DropItem(f"Duplicate URL: {url}")
        self.seen_urls.add(url)
        return item
