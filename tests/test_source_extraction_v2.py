import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.source_extraction import extract_source_metadata


def test_extract_source_and_reporting_institutions_from_english_text():
    html = """
    <div>
      <p>Source: OeNB, Statistics Austria</p>
      <p>Reporting institutions: Statistics Austria</p>
    </div>
    """
    result = extract_source_metadata(html)

    assert "OeNB" in result.sources
    assert "Statistics Austria" in result.sources
    assert result.reporting_institutions == ["Statistics Austria"]
    assert "Source: OeNB, Statistics Austria" in result.source_text_raw


def test_extract_linked_sources_and_multiple_separators():
    html = """
    <p>
      Quelle:
      <a href="https://www.oenb.at/">OeNB</a>,
      <a href="https://www.statistik.at/">Statistik Austria</a> und
      <a href="https://ec.europa.eu/eurostat">Eurostat</a>
    </p>
    """
    result = extract_source_metadata(html)

    assert result.sources == ["OeNB", "Statistik Austria", "Eurostat"]
    assert result.source_links == [
        {"label": "OeNB", "url": "https://www.oenb.at/"},
        {"label": "Statistik Austria", "url": "https://www.statistik.at/"},
        {"label": "Eurostat", "url": "https://ec.europa.eu/eurostat"},
    ]


def test_extract_source_names_preserves_balanced_parentheses():
    html = """
    <div>
      <p>Source: ECB main refinancing operation (MRO), Macrobond</p>
    </div>
    """

    result = extract_source_metadata(html)

    assert result.sources == ["ECB main refinancing operation (MRO)", "Macrobond"]


def test_extract_source_metadata_caps_pathological_source_lists():
    """Giant archive pages yield >10k junk 'sources' (author names, table
    fragments). Cap the lists so downstream merging stays sane."""
    blocks = "\n".join(
        f"<p>Quelle: Autor {chr(65 + i % 26)}. Nachname{i}</p>" for i in range(500)
    )
    metadata = extract_source_metadata(f"<html><body>{blocks}</body></html>")
    assert len(metadata.sources) <= 100
    assert len(metadata.source_text_raw) <= 100
