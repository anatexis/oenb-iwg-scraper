import scrapy.exceptions
import requests

from oenb_scraper.pdf_analyzer import analyze_pdf


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
    """Analyze PDFs for machine readability."""

    def process_item(self, item, spider):
        if item.get("file_type") == "pdf" and item.get("machine_readable") is None:
            spider.logger.info(f"Analyzing PDF: {item['url']}")
            result = analyze_pdf(item["url"])
            item["machine_readable"] = result["machine_readable"]
            item["has_tables"] = result["has_tables"]
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
