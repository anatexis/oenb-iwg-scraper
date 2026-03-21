import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

import oenb_scraper.asset_extraction as asset_extraction
from oenb_scraper.asset_extraction import extract_asset_payload


def test_extract_asset_payload_for_csv_includes_headers_and_counts():
    payload = extract_asset_payload(
        url="https://www.oenb.at/downloads/leitzins.csv",
        content_type="text/csv; charset=utf-8",
        body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
    )

    assert payload["asset_type"] == "csv"
    assert payload["extraction_status"] == "text_extracted"
    assert payload["metadata"]["row_count"] == 2
    assert payload["metadata"]["column_names"] == ["period", "value"]
    assert "period" in payload["text_content"]
    assert "2026-02" in payload["text_content"]


def test_extract_asset_payload_for_zip_lists_entries():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data/leitzins.csv", "period,value\n2026-01,2.5\n")
        archive.writestr("docs/readme.txt", "Leitzins data package")

    payload = extract_asset_payload(
        url="https://www.oenb.at/downloads/leitzins.zip",
        content_type="application/zip",
        body=buffer.getvalue(),
    )

    assert payload["asset_type"] == "zip"
    assert payload["extraction_status"] == "metadata_only"
    assert payload["metadata"]["entry_count"] == 2
    assert payload["metadata"]["entry_names"] == ["data/leitzins.csv", "docs/readme.txt"]


def test_extract_asset_payload_for_xlsx_lists_sheet_names():
    buffer = io.BytesIO()
    workbook_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets>
        <sheet name="Leitzinsen" sheetId="1" r:id="rId1"/>
        <sheet name="Inflation" sheetId="2" r:id="rId2"/>
      </sheets>
    </workbook>
    """
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)

    payload = extract_asset_payload(
        url="https://www.oenb.at/downloads/statistics.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=buffer.getvalue(),
    )

    assert payload["asset_type"] == "xlsx"
    assert payload["extraction_status"] == "metadata_only"
    assert payload["metadata"]["sheet_names"] == ["Leitzinsen", "Inflation"]


def test_extract_asset_payload_for_docx_extracts_document_text():
    buffer = io.BytesIO()
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Leitzins aktuell</w:t></w:r></w:p>
        <w:p><w:r><w:t>Stand März 2026</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    payload = extract_asset_payload(
        url="https://www.oenb.at/downloads/leitzins.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body=buffer.getvalue(),
    )

    assert payload["asset_type"] == "docx"
    assert payload["extraction_status"] == "text_extracted"
    assert "Leitzins aktuell" in payload["text_content"]
    assert payload["metadata"]["paragraph_count"] == 2


def test_extract_asset_payload_for_pdf_dispatches_to_pdf_handler(monkeypatch):
    monkeypatch.setattr(
        asset_extraction,
        "_extract_pdf_payload",
        lambda asset_type, body: {
            "asset_type": asset_type,
            "extraction_status": "text_extracted",
            "text_content": "Leitzins aktuell",
            "metadata": {"page_count": 1},
        },
    )

    payload = extract_asset_payload(
        url="https://www.oenb.at/downloads/leitzins.pdf",
        content_type="application/pdf",
        body=b"%PDF-1.4\n",
    )

    assert payload["asset_type"] == "pdf"
    assert payload["extraction_status"] == "text_extracted"
    assert payload["text_content"] == "Leitzins aktuell"
