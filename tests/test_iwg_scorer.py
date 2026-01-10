"""Tests for IWG relevance scoring."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.iwg_scorer import calculate_iwg_score, enrich_items_with_scores


class TestFileTypeScoring:
    """Test scoring based on file type."""

    def test_xlsx_scores_40_points(self):
        item = {"file_type": "xlsx"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] >= 40
        assert ("Dateityp: xlsx", 40) in result["iwg_factors"]

    def test_csv_scores_40_points(self):
        item = {"file_type": "csv"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] >= 40

    def test_pdf_scores_20_points(self):
        item = {"file_type": "pdf"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] == 20

    def test_zip_scores_15_points(self):
        item = {"file_type": "zip"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] == 15

    def test_unknown_filetype_scores_zero(self):
        item = {"file_type": "unknown"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] == 0


class TestShinyAppScoring:
    """Test scoring for Shiny apps."""

    def test_shiny_app_gets_30_bonus(self):
        item = {"type": "shiny_app", "file_type": "shiny"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] >= 30
        assert ("Shiny App (visualisierte Daten)", 30) in result["iwg_factors"]


class TestMachineReadabilityScoring:
    """Test scoring based on machine readability."""

    def test_machine_readable_adds_20_points(self):
        item = {"file_type": "pdf", "machine_readable": True}
        result = calculate_iwg_score(item)
        # pdf (20) + machine_readable (20) = 40
        assert result["iwg_score"] == 40

    def test_not_machine_readable_subtracts_20_points(self):
        item = {"file_type": "pdf", "machine_readable": False}
        result = calculate_iwg_score(item)
        # pdf (20) - not_readable (20) = 0
        assert result["iwg_score"] == 0

    def test_has_tables_adds_10_points(self):
        item = {"file_type": "pdf", "has_tables": True}
        result = calculate_iwg_score(item)
        # pdf (20) + has_tables (10) = 30
        assert result["iwg_score"] == 30


class TestSectionScoring:
    """Test scoring based on page section."""

    def test_statistik_section_adds_25_points(self):
        item = {"file_type": "pdf", "page_section": "Statistik"}
        result = calculate_iwg_score(item)
        # pdf (20) + statistik (25) = 45
        assert result["iwg_score"] == 45

    def test_meldewesen_section_adds_15_points(self):
        item = {"file_type": "pdf", "page_section": "Meldewesen"}
        result = calculate_iwg_score(item)
        # pdf (20) + meldewesen (15) = 35
        assert result["iwg_score"] == 35

    def test_geldpolitik_section_adds_10_points(self):
        item = {"file_type": "pdf", "page_section": "Geldpolitik"}
        result = calculate_iwg_score(item)
        # pdf (20) + geldpolitik (10) = 30
        assert result["iwg_score"] == 30


class TestKeywordScoring:
    """Test scoring based on keywords in title."""

    def test_daten_keyword_adds_15_points(self):
        # Note: \bdaten\b requires standalone word, not compound like "Wirtschaftsdaten"
        item = {"file_type": "pdf", "title": "Aktuelle Daten 2024"}
        result = calculate_iwg_score(item)
        # pdf (20) + keyword daten (15) = 35
        assert result["iwg_score"] == 35

    def test_statistik_keyword_adds_15_points(self):
        item = {"file_type": "pdf", "title": "Statistik Übersicht"}
        result = calculate_iwg_score(item)
        # pdf (20) + statistik (15) = 35
        assert result["iwg_score"] == 35

    def test_zeitreihe_keyword_adds_15_points(self):
        item = {"file_type": "pdf", "title": "Zeitreihe Inflation"}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] == 35

    def test_multiple_keywords_add_up(self):
        item = {"file_type": "pdf", "title": "Statistik Daten Report"}
        result = calculate_iwg_score(item)
        # pdf (20) + statistik (15) + daten (15) + report (5) = 55
        assert result["iwg_score"] == 55


class TestConfidenceLevels:
    """Test confidence level assignment."""

    def test_high_confidence_for_score_70_plus(self):
        # xlsx (40) + statistik (25) + machine_readable (20) = 85
        item = {
            "file_type": "xlsx",
            "page_section": "Statistik",
            "machine_readable": True,
        }
        result = calculate_iwg_score(item)
        assert result["iwg_confidence"] == "high"
        assert result["iwg_score"] >= 70

    def test_medium_confidence_for_score_40_to_69(self):
        # pdf (20) + statistik (25) = 45
        item = {"file_type": "pdf", "page_section": "Statistik"}
        result = calculate_iwg_score(item)
        assert result["iwg_confidence"] == "medium"
        assert 40 <= result["iwg_score"] < 70

    def test_low_confidence_for_score_below_40(self):
        item = {"file_type": "pdf"}
        result = calculate_iwg_score(item)
        assert result["iwg_confidence"] == "low"
        assert result["iwg_score"] < 40


class TestScoreCapping:
    """Test that score is capped at 0-100."""

    def test_score_capped_at_100(self):
        # Create item with maximum possible score
        item = {
            "type": "shiny_app",
            "file_type": "xlsx",
            "page_section": "Statistik",
            "machine_readable": True,
            "has_tables": True,
            "title": "Statistik Daten Zeitreihe Dataset Download Bericht Report Analyse",
        }
        result = calculate_iwg_score(item)
        assert result["iwg_score"] <= 100

    def test_score_not_negative(self):
        # PDF that's not machine readable
        item = {"file_type": "unknown", "machine_readable": False}
        result = calculate_iwg_score(item)
        assert result["iwg_score"] >= 0


class TestEnrichItems:
    """Test batch enrichment of items."""

    def test_enrich_adds_score_to_each_item(self):
        items = [
            {"file_type": "xlsx", "url": "test1.xlsx"},
            {"file_type": "pdf", "url": "test2.pdf"},
        ]
        enriched = enrich_items_with_scores(items)

        assert len(enriched) == 2
        assert "iwg_score" in enriched[0]
        assert "iwg_confidence" in enriched[0]
        assert "iwg_factors" in enriched[0]

    def test_enrich_preserves_original_fields(self):
        items = [{"file_type": "xlsx", "url": "test.xlsx", "title": "Test"}]
        enriched = enrich_items_with_scores(items)

        assert enriched[0]["url"] == "test.xlsx"
        assert enriched[0]["title"] == "Test"
        assert enriched[0]["file_type"] == "xlsx"

    def test_enrich_empty_list_returns_empty(self):
        enriched = enrich_items_with_scores([])
        assert enriched == []
