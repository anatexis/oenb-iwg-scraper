# Scrapy settings for oenb_scraper project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "oenb_scraper"

SPIDER_MODULES = ["oenb_scraper.spiders"]
NEWSPIDER_MODULE = "oenb_scraper.spiders"

# Polite crawling
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 0.5  # 0.5 seconds between requests
CONCURRENT_REQUESTS = 4  # 4 concurrent requests

# User agent
USER_AGENT = "OeNB-IWG-Audit-Bot/1.0 (Open Data compliance check; contact@example.com)"

# Output encoding
FEED_EXPORT_ENCODING = "utf-8"

# Logging
LOG_LEVEL = "INFO"

# Disable cookies (not needed)
COOKIES_ENABLED = False

# Breadth-first crawl order — ensures all start URLs and section landing pages
# are visited before diving deep into any single section.
DEPTH_PRIORITY = 1
SCHEDULER_DISK_QUEUE = "scrapy.squeues.PickleFifoDiskQueue"
SCHEDULER_MEMORY_QUEUE = "scrapy.squeues.FifoMemoryQueue"

# Enable AutoThrottle for additional politeness
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 5
AUTOTHROTTLE_TARGET_CONCURRENCY = 4.0

# Item pipelines
ITEM_PIPELINES = {
    "oenb_scraper.pipelines.DeduplicationPipeline": 100,
    "oenb_scraper.pipelines.FileSizePipeline": 200,
    # "oenb_scraper.pipelines.PdfAnalysisPipeline": 300,  # Disabled for performance, moved to post-processing
    # "oenb_scraper.pipelines.SQLitePipeline": 400,  # Optional: Enable for RAG/Chatbot (stores HTML in SQLite)
}

# SQLite settings (only used if SQLitePipeline is enabled)
# SQLITE_DB_PATH = "data/pages.db"

# Extensions
EXTENSIONS = {
    "oenb_scraper.pipelines.FailedUrlLogger": 100,
}
