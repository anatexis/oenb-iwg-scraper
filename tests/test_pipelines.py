"""Tests for scraper pipelines."""

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

import oenb_scraper.pipelines as pipelines_module
from oenb_scraper.pipelines import PdfAnalysisPipeline


class TestPdfAnalysisCaching:
    """Test PDF analysis caching functionality."""

    def setup_method(self):
        """Set up temp cache directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cache_dir = pipelines_module.CACHE_DIR
        pipelines_module.CACHE_DIR = Path(self.temp_dir) / ".pdf_cache"

    def teardown_method(self):
        """Restore original cache directory."""
        pipelines_module.CACHE_DIR = self.original_cache_dir

    def test_cache_key_is_md5_of_url(self):
        pipeline = PdfAnalysisPipeline()
        url = "https://example.com/test.pdf"
        expected = hashlib.md5(url.encode()).hexdigest()
        assert pipeline._cache_key(url) == expected

    def test_cache_directory_created_on_init(self):
        pipeline = PdfAnalysisPipeline()
        assert pipelines_module.CACHE_DIR.exists()

    def test_empty_cache_on_first_run(self):
        pipeline = PdfAnalysisPipeline()
        assert pipeline.cache == {}

    @patch("oenb_scraper.pipelines.analyze_pdf")
    def test_pdf_analyzed_when_not_in_cache(self, mock_analyze):
        mock_analyze.return_value = {
            "machine_readable": True,
            "has_tables": False,
            "error": None,
        }
        spider = MagicMock()

        pipeline = PdfAnalysisPipeline()
        item = {"file_type": "pdf", "url": "https://example.com/doc.pdf"}

        result = pipeline.process_item(item, spider)

        mock_analyze.assert_called_once_with("https://example.com/doc.pdf")
        assert result["machine_readable"] is True
        assert result["has_tables"] is False

    @patch("oenb_scraper.pipelines.analyze_pdf")
    def test_result_cached_after_analysis(self, mock_analyze):
        mock_analyze.return_value = {
            "machine_readable": True,
            "has_tables": True,
            "error": None,
        }
        spider = MagicMock()

        pipeline = PdfAnalysisPipeline()
        url = "https://example.com/doc.pdf"
        item = {"file_type": "pdf", "url": url}

        pipeline.process_item(item, spider)

        key = pipeline._cache_key(url)
        assert key in pipeline.cache
        assert pipeline.cache[key]["machine_readable"] is True
        assert pipeline.cache[key]["has_tables"] is True

    @patch("oenb_scraper.pipelines.analyze_pdf")
    def test_cached_result_used_without_reanalysis(self, mock_analyze):
        spider = MagicMock()

        pipeline = PdfAnalysisPipeline()
        url = "https://example.com/cached.pdf"
        key = pipeline._cache_key(url)

        # Pre-populate cache
        pipeline.cache[key] = {"machine_readable": False, "has_tables": True}

        item = {"file_type": "pdf", "url": url}
        result = pipeline.process_item(item, spider)

        mock_analyze.assert_not_called()
        assert result["machine_readable"] is False
        assert result["has_tables"] is True

    @patch("oenb_scraper.pipelines.analyze_pdf")
    def test_cache_persists_to_file(self, mock_analyze):
        mock_analyze.return_value = {
            "machine_readable": True,
            "has_tables": False,
            "error": None,
        }
        spider = MagicMock()

        pipeline = PdfAnalysisPipeline()
        url = "https://example.com/persist.pdf"
        item = {"file_type": "pdf", "url": url}

        pipeline.process_item(item, spider)

        # Check file was written
        cache_file = pipelines_module.CACHE_DIR / "pdf_analysis.json"
        assert cache_file.exists()

        # Verify content
        saved = json.loads(cache_file.read_text())
        key = pipeline._cache_key(url)
        assert key in saved

    @patch("oenb_scraper.pipelines.analyze_pdf")
    def test_cache_loaded_from_file_on_new_instance(self, mock_analyze):
        mock_analyze.return_value = {
            "machine_readable": True,
            "has_tables": True,
            "error": None,
        }
        spider = MagicMock()

        # First pipeline processes item
        pipeline1 = PdfAnalysisPipeline()
        url = "https://example.com/reload.pdf"
        item = {"file_type": "pdf", "url": url}
        pipeline1.process_item(item, spider)

        # Second pipeline should load from cache file
        pipeline2 = PdfAnalysisPipeline()
        key = pipeline2._cache_key(url)
        assert key in pipeline2.cache

        # Process same item - should not call analyze_pdf again
        mock_analyze.reset_mock()
        item2 = {"file_type": "pdf", "url": url}
        pipeline2.process_item(item2, spider)
        mock_analyze.assert_not_called()

    def test_non_pdf_items_not_processed(self):
        spider = MagicMock()
        pipeline = PdfAnalysisPipeline()

        item = {"file_type": "xlsx", "url": "https://example.com/data.xlsx"}
        result = pipeline.process_item(item, spider)

        assert "machine_readable" not in result or result.get("machine_readable") is None

    def test_items_with_existing_analysis_skipped(self):
        spider = MagicMock()
        pipeline = PdfAnalysisPipeline()

        item = {
            "file_type": "pdf",
            "url": "https://example.com/already.pdf",
            "machine_readable": True,  # Already analyzed
        }

        with patch("oenb_scraper.pipelines.analyze_pdf") as mock:
            pipeline.process_item(item, spider)
            mock.assert_not_called()
