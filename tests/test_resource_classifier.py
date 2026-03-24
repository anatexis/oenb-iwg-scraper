import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.resource_classifier import classify_url


def test_classify_isaweb_chart():
    result = classify_url("https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1")

    assert result.kind == "isaweb_entry"
    assert result.subtype == "chart"


def test_classify_standardized_table_topic():
    result = classify_url(
        "https://www.oenb.at/Statistik/Standardisierte-Tabellen/zinssaetze-und-wechselkurse/Eurogeldmarkt-und-Eurosystemzinssaetze-.html"
    )

    assert result.kind == "standardized_table_topic"
    assert result.subtype == "topic"


def test_classify_download_asset():
    result = classify_url("https://www.oenb.at/dam/jcr:test/report.csv")

    assert result.kind == "asset_document"
    assert result.subtype == "csv"
