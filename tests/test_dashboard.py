"""Tests for dashboard generation."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.dashboard import generate_dashboard, generate_csv, load_data, generate_usage_snippets


class TestLoadData:
    """Test JSON data loading."""

    def test_loads_json_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"url": "test.pdf", "file_type": "pdf"}], f)
            f.flush()

            items = load_data(f.name)
            assert len(items) == 1
            assert items[0]["url"] == "test.pdf"

    def test_loads_empty_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            f.flush()

            items = load_data(f.name)
            assert items == []


class TestGenerateDashboard:
    """Test HTML dashboard generation."""

    def test_generates_html_file(self):
        items = [
            {"url": "test.xlsx", "file_type": "xlsx", "title": "Test Data",
             "page_section": "Statistik", "found_on_page": "https://example.com"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            output_path = f.name

        generate_dashboard(items, output_path)

        content = Path(output_path).read_text()
        assert "<!DOCTYPE html>" in content
        assert "OeNB Downloads" in content
        assert "test.xlsx" in content

    def test_dashboard_contains_statistics(self):
        items = [
            {"url": "a.xlsx", "file_type": "xlsx", "page_section": "Statistik",
             "found_on_page": "https://example.com", "machine_readable": True},
            {"url": "b.pdf", "file_type": "pdf", "page_section": "Geldpolitik",
             "found_on_page": "https://example.com"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            output_path = f.name

        generate_dashboard(items, output_path)

        content = Path(output_path).read_text()
        # Check for summary counts
        assert "Gesamt" in content
        assert "Hoch" in content or "high" in content

    def test_dashboard_handles_empty_items(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            output_path = f.name

        generate_dashboard([], output_path)

        content = Path(output_path).read_text()
        assert "<!DOCTYPE html>" in content


class TestGenerateCSV:
    """Test CSV export generation."""

    def test_generates_csv_file(self):
        items = [
            {"url": "test.xlsx", "file_type": "xlsx", "title": "Test Data",
             "type": "download", "page_section": "Statistik",
             "found_on_page": "https://example.com"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = f.name

        generate_csv(items, output_path)

        content = Path(output_path).read_text()
        assert "URL" in content  # Header
        assert "test.xlsx" in content

    def test_csv_contains_all_columns(self):
        items = [
            {"url": "test.pdf", "file_type": "pdf", "title": "Report",
             "type": "download", "page_section": "Test", "file_size_bytes": 1000,
             "found_on_page": "https://example.com", "machine_readable": True,
             "has_tables": False},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = f.name

        generate_csv(items, output_path)

        content = Path(output_path).read_text()
        lines = content.strip().split("\n")
        header = lines[0]

        assert "URL" in header
        assert "Titel" in header
        assert "IWG Score" in header
        assert "Konfidenz" in header

    def test_csv_uses_semicolon_separator(self):
        items = [{"url": "test.pdf", "file_type": "pdf", "page_section": "Test",
                  "found_on_page": "https://example.com", "type": "download"}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = f.name

        generate_csv(items, output_path)

        content = Path(output_path).read_text()
        assert ";" in content  # Uses semicolon for German Excel

    def test_csv_handles_empty_items(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = f.name

        generate_csv([], output_path)

        content = Path(output_path).read_text()
        # Should still have header
        assert "URL" in content


class TestGenerateUsageSnippets:
    """Test usage snippet generation."""

    def test_csv_generates_pandas_snippet(self):
        item = {"url": "https://example.com/data.csv", "file_type": "csv"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "pandas" in snippets["python"]
        assert "read_csv" in snippets["python"]
        assert "data.csv" in snippets["python"]

    def test_excel_generates_pandas_snippet(self):
        item = {"url": "https://example.com/data.xlsx", "file_type": "xlsx"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "read_excel" in snippets["python"]
        assert "openpyxl" in snippets["python"]

    def test_xls_generates_pandas_snippet(self):
        item = {"url": "https://example.com/data.xls", "file_type": "xls"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "read_excel" in snippets["python"]

    def test_xml_generates_pandas_snippet(self):
        item = {"url": "https://example.com/data.xml", "file_type": "xml"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "read_xml" in snippets["python"]
        assert "lxml" in snippets["python"]

    def test_json_generates_pandas_snippet(self):
        item = {"url": "https://example.com/data.json", "file_type": "json"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "read_json" in snippets["python"]

    def test_pdf_generates_download_snippet(self):
        item = {"url": "https://example.com/report.pdf", "file_type": "pdf"}
        snippets = generate_usage_snippets(item)

        assert "python" in snippets
        assert "requests" in snippets["python"]
        assert "report.pdf" in snippets["python"]

    def test_generates_r_csv_snippet(self):
        item = {"url": "https://example.com/data.csv", "file_type": "csv"}
        snippets = generate_usage_snippets(item)

        assert "r" in snippets
        assert "read.csv" in snippets["r"]

    def test_generates_r_excel_snippet(self):
        item = {"url": "https://example.com/data.xlsx", "file_type": "xlsx"}
        snippets = generate_usage_snippets(item)

        assert "r" in snippets
        assert "readxl" in snippets["r"]
        assert "read_excel" in snippets["r"]

    def test_generates_r_download_snippet_for_others(self):
        item = {"url": "https://example.com/report.pdf", "file_type": "pdf"}
        snippets = generate_usage_snippets(item)

        assert "r" in snippets
        assert "download.file" in snippets["r"]

    def test_generates_curl_snippet(self):
        item = {"url": "https://example.com/data.csv", "file_type": "csv"}
        snippets = generate_usage_snippets(item)

        assert "curl" in snippets
        assert "curl -O" in snippets["curl"]
        assert "data.csv" in snippets["curl"]

    def test_handles_missing_url(self):
        item = {"file_type": "csv"}
        snippets = generate_usage_snippets(item)

        # Should not crash, uses empty string
        assert "python" in snippets
        assert "r" in snippets
        assert "curl" in snippets

    def test_handles_missing_file_type(self):
        item = {"url": "https://example.com/unknown"}
        snippets = generate_usage_snippets(item)

        # Should fall back to download snippet
        assert "python" in snippets
        assert "requests" in snippets["python"]
