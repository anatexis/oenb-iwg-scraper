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
DOWNLOAD_DELAY = 1.5  # 1.5 seconds between requests
CONCURRENT_REQUESTS = 1  # One request at a time

# User agent
USER_AGENT = "OeNB-IWG-Audit-Bot/1.0 (Open Data compliance check; contact@example.com)"

# Output encoding
FEED_EXPORT_ENCODING = "utf-8"

# Logging
LOG_LEVEL = "INFO"

# Disable cookies (not needed)
COOKIES_ENABLED = False

# Enable AutoThrottle for additional politeness
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

    "oenb_scraper.pipelines.DeduplicationPipeline": 100,
    "oenb_scraper.pipelines.FileSizePipeline": 200,
    # "oenb_scraper.pipelines.PdfAnalysisPipeline": 300,  # Disabled for performance, moved to post-processing
