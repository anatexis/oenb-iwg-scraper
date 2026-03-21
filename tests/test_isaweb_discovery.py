import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_discovery import classify_isaweb_url


def test_detect_show_result_as_transient_view():
    result = classify_isaweb_url("https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11")

    assert result.kind == "show_result"
    assert result.canonicalizable is False


def test_detect_chart_as_canonical_entry():
    result = classify_isaweb_url("https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1")

    assert result.kind == "chart"
    assert result.canonicalizable is True


def test_detect_report_as_canonical_entry():
    result = classify_isaweb_url("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8")

    assert result.kind == "report"
    assert result.canonicalizable is True


def test_ignore_static_isaweb_assets():
    result = classify_isaweb_url("https://www.oenb.at/isawebstat/webjars/bootstrap/5.1.3/css/bootstrap.min.css")

    assert result is None


def test_ignore_isaweb_action_urls():
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/stabfrage/downloadResult?lang=EN&exportTyp=CSV&report=14.8"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/exportChart?chart=9.5.1&exportRows=selected&exportTyp=CSV&lang=EN"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/dynabfrage/defineParamsAjax?hierarchieId=6&bereich=indikatoren"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/dynabfrageImportExport/loadDefinition?lang=EN"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/showMetadatenStAbfrage?lang=EN&report=14.8"
    ) is None


def test_ignore_isaweb_session_root_urls():
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/dynabfrage/"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/dynabfrage/;jsessionid=22B25331CB7E9A971DA28E5815541310"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/stabfrage/"
    ) is None
    assert classify_isaweb_url(
        "https://www.oenb.at/isawebstat/stabfrage/;jsessionid=B6E10ECB64C1AEB073EFB2CEB6FB8AB7"
    ) is None
