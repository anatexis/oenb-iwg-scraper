import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.source_extraction import extract_source_metadata


def test_extract_source_from_chart_aria_label():
    html = '<div aria-label="Chart showing inflation. source: ECB, Eurostat"></div>'
    result = extract_source_metadata(html)

    assert "ECB" in result.sources
    assert "Eurostat" in result.sources
    assert result.source_extraction_method in {"aria-label", "chart-accessibility"}


def test_extract_source_from_highcharts_data_source_block():
    html = '<div class="highcharts-data-source">Source: ST.AT, Eurostat</div>'
    result = extract_source_metadata(html)

    assert "ST.AT" in result.sources
    assert "Eurostat" in result.sources
