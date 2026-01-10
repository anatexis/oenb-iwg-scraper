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
    """Track duplicate URLs and mark items found in multiple languages."""

    def __init__(self):
        self.seen_urls = {}  # url -> item reference

    def process_item(self, item, spider):
        url = item.get("url")
        language = item.get("language", "de")

        if url in self.seen_urls:
            # URL already seen - update the original item's found_in_languages
            original_item = self.seen_urls[url]
            existing_languages = original_item.get("found_in_languages") or []
            if language not in existing_languages:
                existing_languages.append(language)
                original_item["found_in_languages"] = existing_languages
                spider.logger.debug(f"Duplicate URL found in {language}: {url}")
            raise scrapy.exceptions.DropItem(f"Duplicate URL: {url}")

        # First occurrence - initialize found_in_languages
        item["found_in_languages"] = [language]
        self.seen_urls[url] = item
        return item
