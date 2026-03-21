from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from oenb_scraper.isaweb_discovery import classify_isaweb_url
from oenb_scraper.resource_types import ResourceKind


DOWNLOAD_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".xml", ".zip",
    ".doc", ".docx", ".ppt", ".pptx", ".json",
    ".txt", ".odt", ".rtf", ".epub", ".geojson", ".kml", ".gml", ".rdf", ".ttl", ".ods",
}
DOWNLOAD_QUERY_FORMATS = {"csv", "xlsx", "xls", "xml", "json", "pdf", "zip"}
SHINY_PATTERNS = ("shinyapps.io", "/shiny/", "shiny.oenb.at")
STANDARDIZED_TABLES_PATTERN = "/statistik/standardisierte-tabellen"


@dataclass(frozen=True)
class ClassifiedUrl:
    kind: str
    subtype: str | None = None


def classify_url(url: str) -> ClassifiedUrl:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    isaweb_info = classify_isaweb_url(url)
    if isaweb_info:
        return ClassifiedUrl(kind=ResourceKind.ISAWEB_ENTRY.value, subtype=isaweb_info.kind.replace("_", "-"))

    if _is_download(url):
        return ClassifiedUrl(kind=ResourceKind.ASSET_DOCUMENT.value, subtype=_download_subtype(url))

    if any(pattern in url.lower() for pattern in SHINY_PATTERNS):
        return ClassifiedUrl(kind=ResourceKind.SHINY_APP.value, subtype="app")

    if STANDARDIZED_TABLES_PATTERN in path_lower:
        return ClassifiedUrl(kind=ResourceKind.STANDARDIZED_TABLE_TOPIC.value, subtype="topic")

    return ClassifiedUrl(kind=ResourceKind.PAGE_DOCUMENT.value, subtype="html")


def _is_download(url: str) -> bool:
    parsed = urlparse(url.lower())
    path = parsed.path

    if any(path.endswith(ext) for ext in DOWNLOAD_EXTENSIONS):
        return True

    format_param = parse_qs(parsed.query).get("format", [])
    return bool(format_param and format_param[0].lower() in DOWNLOAD_QUERY_FORMATS)


def _download_subtype(url: str) -> str:
    parsed = urlparse(url.lower())
    path = parsed.path
    for ext in DOWNLOAD_EXTENSIONS:
        if path.endswith(ext):
            return ext.lstrip(".")

    format_param = parse_qs(parsed.query).get("format", [])
    if format_param:
        return format_param[0].lower()
    return "unknown"
