from __future__ import annotations

from html import unescape
import re
from urllib.parse import parse_qs, urljoin, urlparse
from xml.etree import ElementTree as ET

from scrapy.selector import Selector

from oenb_scraper.isaweb_discovery import classify_isaweb_url
from oenb_scraper.isaweb_service import IsawebDatasetRequest


def infer_hierid_from_report_id(report_id: str) -> int | None:
    parts = [part for part in report_id.split(".") if part]
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        return None
    try:
        return int("".join(parts[:-1]))
    except ValueError:
        return None


def infer_hierid_from_chart_id(chart_id: str) -> int | None:
    parts = [part for part in chart_id.split(".") if part]
    if len(parts) < 3 or not all(part.isdigit() for part in parts):
        return None
    return infer_hierid_from_report_id(".".join(parts[:-1]))


def parse_content_response(xml_text: str | bytes) -> dict:
    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    return {
        "prepared_at": _normalized_text(root.findtext("./header/prepared")),
        "elements": [
            {
                "id": int(element.get("id")),
                "parent": int(element.get("parent")),
                "text": _normalized_text(element.findtext("./text")),
            }
            for element in root.findall("./content/element")
            if element.get("id") and element.get("parent") and _normalized_text(element.findtext("./text"))
        ],
    }


def extract_isaweb_urls_from_html(base_url: str, html: str) -> list[str]:
    """Extract ISAweb URLs from anchors, iframes and inline script text."""

    selector = Selector(text=html)
    candidates: set[str] = set()

    for url in selector.css("a[href]::attr(href), iframe[src]::attr(src)").getall():
        absolute = _normalize_candidate_url(base_url, url)
        if absolute is not None and _is_relevant_isaweb_url(absolute):
            candidates.add(absolute)

    script_text = unescape(html)
    for match in re.findall(r'(https?://[^"\'<>\s]+|/(?:isawebstat|dynabfrage|isadataservice)/[^"\'<>\s]+)', script_text):
        absolute = _normalize_candidate_url(base_url, match)
        if absolute is not None and _is_relevant_isaweb_url(absolute):
            candidates.add(absolute)

    return sorted(candidates)


def resolve_dataset_request_from_html(url: str, html: str, fallback_lang: str | None = None) -> IsawebDatasetRequest | None:
    selector = Selector(text=html)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    lang = (query.get("lang", [fallback_lang or "DE"])[0] or fallback_lang or "DE").upper()
    path = parsed.path.lower()

    if "createchart" in path:
        return _resolve_chart_page(selector, lang)
    if "createreport" in path:
        return _resolve_report_page(selector, query, lang)
    return None


def parse_report_table_html(url: str, html: str, fallback_lang: str | None = None) -> dict | None:
    selector = Selector(text=html)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    report_id = query.get("report", [None])[0]
    lang = (query.get("lang", [fallback_lang or "DE"])[0] or fallback_lang or "DE").upper()
    if not report_id:
        return None

    hierid = infer_hierid_from_report_id(report_id)
    if hierid is None:
        return None

    periods = _extract_report_periods(selector)
    unit = _extract_report_unit(selector)
    observations = _extract_report_observations(selector, periods, unit)
    generic_table = None
    if not observations:
        generic_table = _extract_generic_table(selector)
        if not generic_table:
            return None

    title = _extract_report_title(selector)
    metadata_url = _extract_report_metadata_url(url, selector)
    source = _extract_report_source(selector)
    comment = _extract_report_comment(selector)

    return {
        "hierid": hierid,
        "lang": lang,
        "report_id": report_id,
        "synthetic_pos": f"REPORT:{report_id}",
        "title": title,
        "unit": unit,
        "source": source,
        "comment": comment,
        "frequency": _infer_frequency_from_periods(periods),
        "metadata_url": metadata_url,
        "observations": observations,
        "table_headers": generic_table["headers"] if generic_table else None,
        "table_rows": generic_table["rows"] if generic_table else None,
    }


def parse_release_schedule_html(url: str, html: str, fallback_lang: str | None = None) -> dict | None:
    selector = Selector(text=html)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    report_id = query.get("report", [None])[0]
    lang = (query.get("lang", [fallback_lang or "DE"])[0] or fallback_lang or "DE").upper()
    if not report_id:
        return None

    hierid = infer_hierid_from_report_id(report_id)
    if hierid is None:
        return None

    title = _extract_release_title(selector)
    releases = _extract_release_rows(selector)
    if not releases:
        return None

    return {
        "hierid": hierid,
        "lang": lang,
        "report_id": report_id,
        "synthetic_pos": f"REPORT:{report_id}",
        "title": title,
        "releases": releases,
    }


def _resolve_chart_page(selector: Selector, lang: str) -> IsawebDatasetRequest | None:
    chart_id = selector.css('input[name="chartOld"]::attr(value)').get()
    report_link = selector.css('a[title="back to report"]::attr(href)').get() or ""
    report_query = parse_qs(urlparse(report_link).query)
    report_id = report_query.get("report", [None])[0]
    positions_raw = selector.css('input[name="selectedPosList"]::attr(value)').get() or ""
    positions = _extract_selected_positions(positions_raw)

    hierid = None
    if report_id:
        hierid = infer_hierid_from_report_id(report_id)
    if hierid is None and chart_id:
        hierid = infer_hierid_from_chart_id(chart_id)
    if hierid is None or not positions:
        return None

    return IsawebDatasetRequest(hierid=hierid, lang=lang, pos=positions)


def _resolve_report_page(selector: Selector, query: dict[str, list[str]], lang: str) -> IsawebDatasetRequest | None:
    report_id = query.get("report", [None])[0]
    chart_link = selector.css('a[title="create chart"]::attr(href)').get() or ""
    chart_query = parse_qs(urlparse(chart_link).query)
    chart_id = chart_query.get("chart", [None])[0]
    positions = sorted(
        {
            value
            for value in selector.css("a[data-metakey]::attr(data-metakey)").getall()
            if value and re.match(r"^[A-Z0-9]+$", value)
        }
    )

    hierid = None
    if report_id:
        hierid = infer_hierid_from_report_id(report_id)
    if hierid is None and chart_id:
        hierid = infer_hierid_from_chart_id(chart_id)
    if hierid is None or not positions:
        return None

    return IsawebDatasetRequest(hierid=hierid, lang=lang, pos=positions)


def _extract_selected_positions(raw_value: str) -> list[str]:
    positions = []
    for token in raw_value.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        positions.append(cleaned.split("_", 1)[0])
    return sorted(set(positions))


def _is_relevant_isaweb_url(url: str) -> bool:
    if classify_isaweb_url(url) is not None:
        return True

    path = urlparse(url).path.lower()
    return any(segment in path for segment in ("/isadataservice/content", "/isadataservice/data", "/isadataservice/meta"))


def _extract_report_title(selector: Selector) -> str | None:
    title = selector.css("title::text").get()
    if not title:
        return None
    title = " ".join(title.split())
    title = re.sub(r"^DATA\s*-\s*", "", title, flags=re.IGNORECASE)
    return title or None


def _extract_report_periods(selector: Selector) -> list[str]:
    candidate_rows = _extract_table_header_rows(selector)

    best: list[str] = []
    for cells in candidate_rows:
        period_cells = [cell for cell in cells if _looks_like_period_label(cell)]
        if len(period_cells) > len(best):
            best = period_cells
    return best


def _extract_report_unit(selector: Selector) -> str | None:
    for cells in _extract_table_header_rows(selector):
        if len(cells) == 1 and not _looks_like_period_label(cells[0]):
            return cells[0]
    return None


def _extract_report_observations(selector: Selector, periods: list[str], unit: str | None) -> list[dict]:
    observations: list[dict] = []
    for row in selector.css("table tbody tr"):
        series_label = _extract_row_header_text(row)
        values = _extract_row_values(row)
        if not series_label or not values:
            continue
        for period, value in zip(periods, values):
            observations.append(
                {
                    "period": period,
                    "value": value,
                    "unit": unit,
                    "series_label": series_label,
                }
            )
    if observations:
        return observations

    series_labels = _extract_report_series_labels(selector)
    if not series_labels:
        return []

    for row in selector.css("table tbody tr"):
        period = _extract_row_header_text(row)
        values = _extract_row_values(row)
        if not period or not values or not _looks_like_row_period_label(period):
            continue
        for series_label, value in zip(series_labels, values):
            observations.append(
                {
                    "period": period,
                    "value": value,
                    "unit": unit,
                    "series_label": series_label,
                }
            )
    return observations


def _extract_report_source(selector: Selector) -> str | None:
    links = selector.css("tfoot .quelle a::text").getall()
    normalized_links = [_normalized_text(value) for value in links if _normalized_text(value)]
    if normalized_links:
        return "; ".join(normalized_links)
    source_text = _normalized_text(" ".join(selector.css("tfoot .quelle *::text, tfoot .quelle::text").getall()))
    if not source_text:
        return None
    match = re.search(r"(?i)source\s*:\s*(.+)$", source_text)
    if match:
        return match.group(1).rstrip(".").strip()
    return source_text


def _extract_report_comment(selector: Selector) -> str | None:
    comment = _normalized_text(" ".join(selector.css("tfoot .footnote *::text, tfoot .footnote::text").getall()))
    if not comment:
        return None
    comment = re.sub(r"^\d+\s*", "", comment).strip()
    return comment or None


def _extract_report_metadata_url(base_url: str, selector: Selector) -> str | None:
    raw = selector.css("#metaDataUrl::attr(data-url)").get()
    if not raw:
        return None
    return urljoin(base_url, raw)


def _looks_like_period_label(value: str) -> bool:
    return bool(
        re.match(
            r"^(Q[1-4]\s+\d{2,4}|H[1-2]\s+\d{2,4}|[A-Za-z]{3,9}\.?\s+\d{2,4}|\d{4}|\d{2}\.\d{2}\.\d{2,4})$",
            value.strip(),
        )
    )


def _infer_frequency_from_periods(periods: list[str]) -> str | None:
    if not periods:
        return None
    if all(period.startswith("Q") for period in periods):
        return "Q"
    if all(period.startswith("H") for period in periods):
        return "H"
    return None


def _normalize_candidate_url(base_url: str, candidate: str) -> str | None:
    raw = unescape((candidate or "").strip())
    if not raw:
        return None

    absolute = urljoin(base_url, raw)
    parsed = urlparse(absolute)
    path = parsed.path.lower()
    if not any(segment in path for segment in ("/isawebstat/", "/dynabfrage/", "/isadataservice/")):
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    return absolute


def _extract_release_title(selector: Selector) -> str | None:
    title = _normalized_text(" ".join(selector.css("#releasetable caption .title::text, caption .title::text").getall()))
    if title:
        return title
    title = selector.css("title::text").get()
    if not title:
        return None
    title = " ".join(title.split())
    title = re.sub(r"^DATA\s*-\s*Publication schedule\s*-\s*", "", title, flags=re.IGNORECASE)
    return title or None


def _extract_release_rows(selector: Selector) -> list[dict]:
    releases: list[dict] = []
    for row in selector.css("#releasetable tbody tr, table#releasetable tbody tr"):
        cells = row.css("td")
        if len(cells) < 2:
            continue

        revision_text = _normalized_text(" ".join(cells[0].css("*::text, ::text").getall()))
        date_cell = cells[1]
        release_date = _normalized_text(" ".join(date_cell.css("b::text").getall()))
        if not release_date:
            release_date = _normalized_text(" ".join(date_cell.css("*::text, ::text").getall()))
        if not release_date:
            continue

        raw_date_cell = [value for value in (_normalized_text(text) for text in date_cell.css("*::text, ::text").getall()) if value]
        reference = None
        if raw_date_cell:
            remainder = [value for value in raw_date_cell if value != release_date]
            if remainder:
                reference = " ".join(remainder)

        releases.append(
            {
                "release_date": release_date,
                "reference": reference,
                "revision": revision_text,
            }
        )
    return releases


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _extract_table_header_rows(selector: Selector) -> list[list[str]]:
    candidate_rows: list[list[str]] = []
    for row in selector.css("table thead tr"):
        cells = [_normalized_text(value) for value in row.css("th *::text, th::text").getall()]
        cells = [value for value in cells if value]
        if cells:
            candidate_rows.append(cells)
    return candidate_rows


def _extract_row_header_text(row: Selector) -> str | None:
    return _normalized_text(" ".join(row.css("th[scope='row'] *::text, th[scope='row']::text").getall()))


def _extract_row_values(row: Selector) -> list[str]:
    values = [_normalized_text(" ".join(cell.css("span::text, ::text").getall())) for cell in row.css("td")]
    return [value for value in values if value]


def _extract_report_series_labels(selector: Selector) -> list[str]:
    for cells in _extract_table_header_rows(selector):
        if len(cells) < 2:
            continue
        candidate_labels = cells[1:]
        if all(_looks_like_period_label(value) for value in candidate_labels):
            continue
        return candidate_labels
    return []


def _looks_like_row_period_label(value: str) -> bool:
    return _looks_like_period_label(value)


def _extract_generic_table(selector: Selector) -> dict | None:
    header_rows = _extract_table_header_rows(selector)
    if not header_rows:
        return None

    headers = header_rows[0]
    if len(headers) < 2 or any(_looks_like_period_label(value) for value in headers[1:]):
        return None

    rows: list[list[str]] = []
    for row in selector.css("table tbody tr"):
        cells = [_normalized_text(" ".join(cell.css("*::text, ::text").getall())) for cell in row.css("th, td")]
        cells = [value for value in cells if value and value != "\xa0"]
        if len(cells) < 2:
            continue
        rows.append(cells)

    if not rows:
        return None

    return {"headers": headers, "rows": rows}
