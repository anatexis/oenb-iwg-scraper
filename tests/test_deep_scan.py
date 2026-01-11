"""Tests for DeepScanner class."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.deep_scan import DeepScanner


class TestDeepScannerInit:
    """Test DeepScanner initialization."""

    def test_default_values(self):
        scanner = DeepScanner()
        assert scanner.limit_percent == 0.1
        assert scanner.min_items == 5

    def test_custom_values(self):
        scanner = DeepScanner(limit_percent=0.2, min_items=10)
        assert scanner.limit_percent == 0.2
        assert scanner.min_items == 10


class TestScanItemsSelection:
    """Test item selection logic in scan_items."""

    def test_scans_top_scoring_items(self):
        scanner = DeepScanner(min_items=2)

        items = [
            {"url": "a.csv", "file_type": "csv", "iwg_score": 30, "iwg_factors": []},
            {"url": "b.csv", "file_type": "csv", "iwg_score": 80, "iwg_factors": []},
            {"url": "c.csv", "file_type": "csv", "iwg_score": 50, "iwg_factors": []},
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "Valid"}
            scanner.scan_items(items)

        # Should only scan the top 2 (b.csv with 80, c.csv with 50)
        assert mock_check.call_count == 2
        checked_urls = [call[0][0]["url"] for call in mock_check.call_args_list]
        assert "b.csv" in checked_urls
        assert "c.csv" in checked_urls

    def test_respects_min_items(self):
        scanner = DeepScanner(limit_percent=0.01, min_items=3)

        items = [
            {"url": f"{i}.csv", "file_type": "csv", "iwg_score": i, "iwg_factors": []}
            for i in range(10)
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "Valid"}
            scanner.scan_items(items)

        # 0.01 * 10 = 0.1 -> rounds to 0, but min_items=3 should take over
        assert mock_check.call_count == 3

    def test_respects_limit_percent(self):
        scanner = DeepScanner(limit_percent=0.5, min_items=1)

        items = [
            {"url": f"{i}.csv", "file_type": "csv", "iwg_score": i, "iwg_factors": []}
            for i in range(10)
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "Valid"}
            scanner.scan_items(items)

        # 0.5 * 10 = 5
        assert mock_check.call_count == 5

    def test_does_not_scan_more_than_available(self):
        scanner = DeepScanner(min_items=100)

        items = [
            {"url": "a.csv", "file_type": "csv", "iwg_score": 50, "iwg_factors": []},
            {"url": "b.csv", "file_type": "csv", "iwg_score": 60, "iwg_factors": []},
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "Valid"}
            scanner.scan_items(items)

        # Only 2 items available
        assert mock_check.call_count == 2


class TestScanResults:
    """Test scan result handling."""

    def test_adds_scan_result_to_scanned_items(self):
        scanner = DeepScanner(min_items=1)

        items = [
            {"url": "a.csv", "file_type": "csv", "iwg_score": 50, "iwg_factors": []},
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "File is valid"}
            result = scanner.scan_items(items)

        assert result[0]["scan_result"]["status"] == "ok"

    def test_non_scanned_items_have_none_result(self):
        scanner = DeepScanner(min_items=1)

        items = [
            {"url": "a.csv", "file_type": "csv", "iwg_score": 100, "iwg_factors": []},
            {"url": "b.csv", "file_type": "csv", "iwg_score": 10, "iwg_factors": []},
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "ok", "message": "Valid"}
            result = scanner.scan_items(items)

        # b.csv has lower score, should not be scanned
        low_score_item = next(i for i in result if i["url"] == "b.csv")
        assert low_score_item["scan_result"] is None

    def test_adds_broken_file_factor_on_error(self):
        scanner = DeepScanner(min_items=1)

        items = [
            {"url": "a.csv", "file_type": "csv", "iwg_score": 50, "iwg_factors": []},
        ]

        with patch.object(scanner, "_check_file") as mock_check:
            mock_check.return_value = {"status": "error", "message": "Parse failed"}
            result = scanner.scan_items(items)

        assert ("Broken File (Deep Scan)", 0) in result[0]["iwg_factors"]


class TestCheckFile:
    """Test individual file checking."""

    def test_returns_skipped_for_unsupported_type(self):
        scanner = DeepScanner()

        item = {"url": "https://example.com/doc.docx", "file_type": "docx"}

        with patch("analysis.deep_scan.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.iter_content = MagicMock(return_value=[b"content"])
            mock_get.return_value = mock_response

            result = scanner._check_file(item)

        assert result["status"] == "skipped"
        assert result["reason"] == "unsupported_type"

    def test_returns_error_on_http_failure(self):
        scanner = DeepScanner()

        item = {"url": "https://example.com/data.csv", "file_type": "csv"}

        with patch("analysis.deep_scan.requests.get") as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            result = scanner._check_file(item)

        assert result["status"] == "error"
        assert "Connection failed" in result["message"]


class TestTryCsv:
    """Test CSV parsing."""

    def test_parses_comma_separated(self):
        scanner = DeepScanner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("a,b,c\n1,2,3\n4,5,6\n")
            f.flush()

            # Should not raise
            scanner._try_csv(f.name)

    def test_parses_semicolon_separated(self):
        scanner = DeepScanner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("a;b;c\n1;2;3\n4;5;6\n")
            f.flush()

            # Should not raise
            scanner._try_csv(f.name)

    def test_raises_on_invalid_csv(self):
        scanner = DeepScanner()

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(b"\xff\xfe\x00\x00")  # Invalid UTF-8
            f.flush()

            with pytest.raises(Exception) as exc:
                scanner._try_csv(f.name)

            assert "CSV parse error" in str(exc.value)


class TestTryExcel:
    """Test Excel parsing."""

    def test_raises_on_invalid_excel(self):
        scanner = DeepScanner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xlsx", delete=False) as f:
            f.write("not an excel file")
            f.flush()

            with pytest.raises(Exception) as exc:
                scanner._try_excel(f.name)

            assert "Excel parse error" in str(exc.value)


class TestTryPdf:
    """Test PDF parsing."""

    def test_raises_on_invalid_pdf(self):
        scanner = DeepScanner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("not a pdf file")
            f.flush()

            with pytest.raises(Exception) as exc:
                scanner._try_pdf(f.name)

            assert "PDF parse error" in str(exc.value)
