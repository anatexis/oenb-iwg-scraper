from __future__ import annotations

import re
from dataclasses import dataclass, field

from scrapy.selector import Selector


SOURCE_SELECTORS = (
    ".footer.quelle",
    ".highcharts-data-source",
    "td.quelle",
    ".quelle",
    ".source",
    ".data-source",
    "tfoot td",
    "table caption",
    "figcaption",
    ".chart-source",
    ".figure-source",
)

SOURCE_PREFIX_RE = re.compile(
    r"(?i)\b(?:quelle|quellen|source|sources|datenquelle|data\s+source|geodaten|data)\s*:\s*([^\n\r<]+)"
)
REPORTING_PREFIX_RE = re.compile(
    r"(?i)\b(?:reporting institutions?)\s*:\s*([^\n\r<]+)"
)
SPLIT_RE = re.compile(r"\s*(?:,|;|/|\bund\b|\band\b)\s*", re.IGNORECASE)


@dataclass
class SourceMetadata:
    sources: list[str] = field(default_factory=list)
    source_links: list[dict[str, str]] = field(default_factory=list)
    source_text_raw: list[str] = field(default_factory=list)
    reporting_institutions: list[str] = field(default_factory=list)
    source_extraction_method: str | None = None


MAX_SOURCES = 100


def extract_source_metadata(html: str) -> SourceMetadata:
    """Extract source and provenance metadata from HTML or plain text."""

    selector = Selector(text=html or "")
    metadata = SourceMetadata()
    seen_raw: set[tuple[str, str]] = set()

    for method, text, links in _iter_candidates(selector, html or ""):
        # Cap: giant archive pages otherwise yield >10k junk "sources"
        # (author names, table fragments) that poison downstream merging.
        if len(metadata.sources) >= MAX_SOURCES:
            break
        key = (method, text)
        if key in seen_raw:
            continue
        seen_raw.add(key)

        sources = _parse_source_names(text)
        reporting = _parse_reporting_institutions(text)
        if not sources and not reporting:
            continue

        if sources:
            metadata.source_text_raw.append(text.strip())
            _extend_unique(metadata.sources, sources[:MAX_SOURCES])
            _extend_unique_dicts(metadata.source_links, links)
            metadata.source_extraction_method = metadata.source_extraction_method or method

        if reporting:
            _extend_unique(metadata.reporting_institutions, reporting)

    del metadata.sources[MAX_SOURCES:]
    del metadata.source_text_raw[MAX_SOURCES:]
    return metadata


def extract_source_names(text: str) -> list[str]:
    """Compatibility helper for legacy spider methods."""

    return _parse_source_names(text)


def _iter_candidates(selector: Selector, raw_text: str):
    for css_selector in SOURCE_SELECTORS:
        for node in selector.css(css_selector):
            text = _node_text(node)
            if _contains_provenance_marker(text):
                yield ("selector", text, _extract_links(node))

    for node in selector.xpath("//*"):
        text = node.xpath("string(.)").get(default="").strip()
        if _contains_provenance_marker(text):
            yield ("selector", text, _extract_links(node))

    for value in selector.xpath("//@aria-label").getall():
        if _contains_provenance_marker(value):
            yield ("aria-label", value, [])

    described_ids = selector.xpath("//@aria-describedby").getall()
    for raw_ids in described_ids:
        for elem_id in raw_ids.split():
            text = _described_text(selector, elem_id)
            if text and _contains_provenance_marker(text):
                yield ("chart-accessibility", text, [])

    for match in SOURCE_PREFIX_RE.finditer(raw_text):
        yield ("text-pattern", match.group(0), [])
    for match in REPORTING_PREFIX_RE.finditer(raw_text):
        yield ("text-pattern", match.group(0), [])


def _contains_provenance_marker(text: str) -> bool:
    return bool(SOURCE_PREFIX_RE.search(text or "") or REPORTING_PREFIX_RE.search(text or ""))


def _node_text(node) -> str:
    texts = [part.strip() for part in node.css("::text").getall() if part.strip()]
    return " ".join(texts)


def _extract_links(node) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for link in node.css("a[href]"):
        label = " ".join(part.strip() for part in link.css("::text").getall() if part.strip())
        url = link.attrib.get("href", "").strip()
        if not label or not url:
            continue
        entry = {"label": label, "url": url}
        if entry not in links:
            links.append(entry)
    return links


def _described_text(selector: Selector, elem_id: str) -> str:
    texts = selector.xpath(f'//*[@id="{elem_id}"]//text()').getall()
    return " ".join(part.strip() for part in texts if part.strip())


def _parse_source_names(text: str) -> list[str]:
    names: list[str] = []
    normalized_text = " ".join((text or "").split())
    for match in SOURCE_PREFIX_RE.finditer(normalized_text):
        _extend_unique(names, _split_names(match.group(1)))
    return names


def _parse_reporting_institutions(text: str) -> list[str]:
    names: list[str] = []
    normalized_text = " ".join((text or "").split())
    for match in REPORTING_PREFIX_RE.finditer(normalized_text):
        _extend_unique(names, _split_names(match.group(1)))
    return names


def _split_names(raw_value: str) -> list[str]:
    names: list[str] = []
    for part in SPLIT_RE.split(raw_value):
        name = _clean_name(part)
        if name:
            names.append(name)
    return names


def _clean_name(value: str) -> str:
    value = re.sub(
        r"(?i)^(?:quelle|quellen|source|sources|datenquelle|data\s+source|geodaten|data|reporting institutions?)\s*:\s*",
        "",
        value or "",
    )
    value = re.sub(r"^[\(\[\s]+", "", value).strip()
    value = re.sub(r"[\.\s]+$", "", value).strip()
    while value.endswith(")") and value.count("(") < value.count(")"):
        value = value[:-1].rstrip()
    while value.endswith("]") and value.count("[") < value.count("]"):
        value = value[:-1].rstrip()

    if not value:
        return ""
    if value[0].isdigit():
        return ""
    if len(value) < 2 or len(value) > 50:
        return ""
    if value[0].islower():
        return ""
    return " ".join(value.split())


def _extend_unique(target: list[str], values: list[str]) -> None:
    existing = set(target)
    for value in values:
        if value not in existing:
            existing.add(value)
            target.append(value)


def _extend_unique_dicts(target: list[dict[str, str]], values: list[dict[str, str]]) -> None:
    existing = {tuple(sorted(entry.items())) for entry in target}
    for value in values:
        key = tuple(sorted(value.items()))
        if key not in existing:
            existing.add(key)
            target.append(value)
