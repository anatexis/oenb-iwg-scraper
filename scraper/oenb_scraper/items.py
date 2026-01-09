import scrapy


class DownloadItem(scrapy.Item):
    """Represents a downloadable resource found on oenb.at"""
    url = scrapy.Field()
    type = scrapy.Field()  # 'download', 'shiny_app', 'external_data'
    file_type = scrapy.Field()  # 'pdf', 'xlsx', 'csv', 'xml', 'zip', etc.
    file_size_bytes = scrapy.Field()
    title = scrapy.Field()
    found_on_page = scrapy.Field()
    page_section = scrapy.Field()
    section_heading = scrapy.Field()
    page_date = scrapy.Field()
    scraped_at = scrapy.Field()
    machine_readable = scrapy.Field()  # For PDFs: True/False/None
    has_tables = scrapy.Field()  # For PDFs: True/False/None
