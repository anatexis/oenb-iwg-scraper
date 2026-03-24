import scrapy

from oenb_scraper.resource_types import ResourceKind


class ResourceItem(scrapy.Item):
    """Generic resource envelope for the rebuilt crawler."""

    url = scrapy.Field()
    resource_kind = scrapy.Field()  # See ResourceKind
    subtype = scrapy.Field()
    title = scrapy.Field()
    language = scrapy.Field()
    page_section = scrapy.Field()
    section_heading = scrapy.Field()
    found_on_page = scrapy.Field()
    source_urls = scrapy.Field()
    sources = scrapy.Field()
    source_links = scrapy.Field()
    source_text_raw = scrapy.Field()
    reporting_institutions = scrapy.Field()
    source_extraction_method = scrapy.Field()


class DownloadItem(scrapy.Item):
    """Legacy item kept for compatibility while the resource model is migrated."""

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
    language = scrapy.Field()  # 'de' or 'en'
    found_in_languages = scrapy.Field()  # ['de'], ['en'], or ['de', 'en'] for duplicates
    link_count = scrapy.Field()  # How many times this URL was linked from different pages
    sources = scrapy.Field()  # List of sources, e.g. ['OeNB', 'Statistik Austria']
    source_links = scrapy.Field()  # List of {label, url} provenance references
    source_text_raw = scrapy.Field()  # Raw matched source snippets
    reporting_institutions = scrapy.Field()  # Structured reporting institutions field
    source_extraction_method = scrapy.Field()  # text-pattern, selector, aria-label, ...
    source_urls = scrapy.Field()  # Flattened list of source link targets
    has_html_tables = scrapy.Field()  # For webpages: True if page has data tables
    table_count = scrapy.Field()  # Number of substantial tables on page
    resource_kind = scrapy.Field()  # Transitional field mirroring ResourceKind


LEGACY_TYPE_TO_RESOURCE_KIND = {
    "download": ResourceKind.ASSET_DOCUMENT.value,
    "shiny_app": ResourceKind.SHINY_APP.value,
    "webpage_with_data": ResourceKind.HTML_TABLE.value,
    "interactive_data": ResourceKind.ISAWEB_ENTRY.value,
    "standardized_tables": ResourceKind.STANDARDIZED_TABLE_TOPIC.value,
}
