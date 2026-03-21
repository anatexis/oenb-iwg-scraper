from __future__ import annotations

import csv
import io
import json
import zipfile
from xml.etree import ElementTree as ET

from oenb_scraper.resource_classifier import classify_url


TEXT_PREVIEW_LIMIT = 8000
ROW_PREVIEW_LIMIT = 5
ENTRY_PREVIEW_LIMIT = 50
EXTRACTOR_VERSION = "asset-extractor-v1"


def extract_asset_payload(*, url: str, content_type: str, body: bytes) -> dict:
    """Extract lightweight knowledge-base content from a fetched asset."""

    asset_type = _asset_type_for(url, content_type)
    if asset_type == "csv":
        return _extract_csv_payload(asset_type, body)
    if asset_type in {"json", "geojson"}:
        return _extract_json_payload(asset_type, body)
    if asset_type in {"xlsx", "ods"}:
        return _extract_spreadsheet_package_payload(asset_type, body)
    if asset_type == "docx":
        return _extract_docx_payload(asset_type, body)
    if asset_type == "pptx":
        return _extract_pptx_payload(asset_type, body)
    if asset_type == "pdf" or "pdf" in content_type.lower():
        return _extract_pdf_payload(asset_type, body)
    if asset_type in {"xml", "gml", "kml", "rdf"} or "xml" in content_type.lower():
        return _extract_xml_payload(asset_type, body)
    if asset_type in {"txt", "ttl", "rtf"}:
        return _extract_text_payload(asset_type, body)
    if asset_type == "zip":
        return _extract_zip_payload(asset_type, body)

    return {
        "asset_type": asset_type,
        "extraction_status": "unsupported",
        "text_content": None,
        "metadata": {},
    }


def _extract_csv_payload(asset_type: str, body: bytes) -> dict:
    text = _decode_text(body)
    reader = csv.reader(io.StringIO(text), dialect=_sniff_csv(text))
    rows = list(reader)
    if not rows:
        return {
            "asset_type": asset_type,
            "extraction_status": "metadata_only",
            "text_content": None,
            "metadata": {"row_count": 0, "column_count": 0, "column_names": []},
        }

    header = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    preview_rows = rows[: 1 + ROW_PREVIEW_LIMIT]
    preview_text = "\n".join(" | ".join(cell.strip() for cell in row) for row in preview_rows)
    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted",
        "text_content": preview_text[:TEXT_PREVIEW_LIMIT],
        "metadata": {
            "row_count": len(data_rows),
            "column_count": len(header),
            "column_names": header,
        },
    }


def _extract_json_payload(asset_type: str, body: bytes) -> dict:
    text = _decode_text(body)
    parsed = json.loads(text)

    if isinstance(parsed, list):
        record_count = len(parsed)
        column_names = []
        if parsed and isinstance(parsed[0], dict):
            column_names = sorted({key for item in parsed[:ROW_PREVIEW_LIMIT] if isinstance(item, dict) for key in item.keys()})
        preview = json.dumps(parsed[:ROW_PREVIEW_LIMIT], ensure_ascii=False, indent=2)
        metadata = {"top_level_type": "array", "record_count": record_count, "column_names": column_names}
    elif isinstance(parsed, dict):
        preview = json.dumps(parsed, ensure_ascii=False, indent=2)[:TEXT_PREVIEW_LIMIT]
        metadata = {"top_level_type": "object", "keys": sorted(parsed.keys())}
    else:
        preview = json.dumps(parsed, ensure_ascii=False)
        metadata = {"top_level_type": type(parsed).__name__}

    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted",
        "text_content": preview[:TEXT_PREVIEW_LIMIT],
        "metadata": metadata,
    }


def _extract_xml_payload(asset_type: str, body: bytes) -> dict:
    text = _decode_text(body)
    root = ET.fromstring(text)
    child_tags = [child.tag.split("}", 1)[-1] for child in list(root)[:ENTRY_PREVIEW_LIMIT]]
    text_nodes = [
        " ".join(node.split())
        for node in root.itertext()
        if node and " ".join(node.split())
    ][:ROW_PREVIEW_LIMIT]
    preview = "\n".join(text_nodes)[:TEXT_PREVIEW_LIMIT] or None

    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted" if preview else "metadata_only",
        "text_content": preview,
        "metadata": {
            "root_tag": root.tag.split("}", 1)[-1],
            "child_tags": child_tags,
        },
    }


def _extract_text_payload(asset_type: str, body: bytes) -> dict:
    text = _decode_text(body)
    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted",
        "text_content": text[:TEXT_PREVIEW_LIMIT],
        "metadata": {"character_count": len(text)},
    }


def _extract_zip_payload(asset_type: str, body: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        entry_names = sorted(archive.namelist())
    return {
        "asset_type": asset_type,
        "extraction_status": "metadata_only",
        "text_content": None,
        "metadata": {
            "entry_count": len(entry_names),
            "entry_names": entry_names[:ENTRY_PREVIEW_LIMIT],
        },
    }


def _extract_spreadsheet_package_payload(asset_type: str, body: bytes) -> dict:
    sheet_names: list[str] = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        workbook_path = "xl/workbook.xml" if asset_type == "xlsx" else "content.xml"
        if workbook_path in archive.namelist():
            if asset_type == "xlsx":
                workbook_xml = archive.read(workbook_path).decode("utf-8", errors="replace")
                root = ET.fromstring(workbook_xml)
                namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                sheet_names = [sheet.get("name") for sheet in root.findall(".//x:sheet", namespace) if sheet.get("name")]
            else:
                sheet_names = ["content.xml"]

    return {
        "asset_type": asset_type,
        "extraction_status": "metadata_only",
        "text_content": None,
        "metadata": {"sheet_names": sheet_names},
    }


def _extract_docx_payload(asset_type: str, body: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if "word/document.xml" not in archive.namelist():
            return {
                "asset_type": asset_type,
                "extraction_status": "metadata_only",
                "text_content": None,
                "metadata": {"paragraph_count": 0},
            }
        document_xml = archive.read("word/document.xml").decode("utf-8", errors="replace")

    root = ET.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        text = " ".join(
            " ".join(node.split())
            for node in paragraph.itertext()
            if node and " ".join(node.split())
        ).strip()
        if text:
            paragraphs.append(text)

    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted" if paragraphs else "metadata_only",
        "text_content": "\n".join(paragraphs)[:TEXT_PREVIEW_LIMIT] if paragraphs else None,
        "metadata": {"paragraph_count": len(paragraphs)},
    }


def _extract_pptx_payload(asset_type: str, body: bytes) -> dict:
    slide_texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        for slide_name in slide_names:
            slide_xml = archive.read(slide_name).decode("utf-8", errors="replace")
            root = ET.fromstring(slide_xml)
            text = " ".join(
                " ".join(node.split())
                for node in root.itertext()
                if node and " ".join(node.split())
            ).strip()
            if text:
                slide_texts.append(text)

    return {
        "asset_type": asset_type,
        "extraction_status": "text_extracted" if slide_texts else "metadata_only",
        "text_content": "\n".join(slide_texts)[:TEXT_PREVIEW_LIMIT] if slide_texts else None,
        "metadata": {"slide_count": len(slide_texts)},
    }


def _extract_pdf_payload(asset_type: str, body: bytes) -> dict:
    try:
        import pdfplumber
    except ImportError:
        return {
            "asset_type": asset_type,
            "extraction_status": "metadata_only",
            "text_content": None,
            "metadata": {"error": "pdfplumber unavailable"},
        }

    try:
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            page_texts = []
            has_tables = False
            for page in pdf.pages[:10]:
                text = (page.extract_text() or "").strip()
                if text:
                    page_texts.append(" ".join(text.split()))
                if not has_tables and (page.extract_tables() or []):
                    has_tables = True
            return {
                "asset_type": asset_type,
                "extraction_status": "text_extracted" if page_texts else "metadata_only",
                "text_content": "\n".join(page_texts)[:TEXT_PREVIEW_LIMIT] if page_texts else None,
                "metadata": {"page_count": len(pdf.pages), "has_tables": has_tables},
            }
    except Exception as exc:
        return {
            "asset_type": asset_type,
            "extraction_status": "metadata_only",
            "text_content": None,
            "metadata": {"error": str(exc)},
        }


def _asset_type_for(url: str, content_type: str) -> str:
    classified = classify_url(url)
    if classified.subtype and classified.subtype != "unknown":
        return classified.subtype

    content_type = content_type.lower()
    if "json" in content_type:
        return "json"
    if "xml" in content_type:
        return "xml"
    if "csv" in content_type:
        return "csv"
    if "zip" in content_type:
        return "zip"
    return "unknown"


def _decode_text(body: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _sniff_csv(text: str) -> csv.Dialect:
    sample = text[:2048]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.get_dialect("excel")
