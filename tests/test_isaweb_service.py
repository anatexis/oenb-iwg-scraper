import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_service import (
    build_data_url,
    build_meta_url,
    extract_hierarchy_reference,
    parse_content_positions,
    parse_data_response,
    parse_meta_response,
)


def test_build_data_url_preserves_pos_and_dimensions():
    url = build_data_url(
        hierid=11,
        lang="DE",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"], "dval2": ["00100KI"]},
        starttime="2000-01-01",
    )

    assert url.startswith("https://www.oenb.at/isadataservice/data?")
    assert "hierid=11" in url
    assert "lang=DE" in url
    assert "pos=VDBFKBSC217000" in url
    assert "dval1=AT" in url
    assert "dval2=00100KI" in url
    assert "starttime=2000-01-01" in url


def test_build_meta_url_includes_mode_and_lang():
    url = build_meta_url(hierid=11, lang="EN", mode="series")

    assert url.startswith("https://www.oenb.at/isadataservice/meta?")
    assert "hierid=11" in url
    assert "lang=EN" in url
    assert "mode=series" in url


def test_parse_data_response_extracts_series_and_observations():
    xml = """
    <OeNBData>
      <data>
        <dataSet pos="VDBKISDANZTAU" posTitle="number of foreign subsidiaries" attr1="AT" attr2="BS0100510" attr1Dim="PRODUZENT" attr2Dim="BANKENSEKTOR" freq="H" unitMult="0" unitText="in ones">
          <values>
            <obs value="90.0" periode="2005-B1"/>
            <obs value="90.0" periode="2005-B2"/>
          </values>
        </dataSet>
      </data>
    </OeNBData>
    """

    series = parse_data_response(xml)

    assert len(series) == 1
    assert series[0]["pos"] == "VDBKISDANZTAU"
    assert series[0]["title"] == "number of foreign subsidiaries"
    assert series[0]["freq"] == "H"
    assert series[0]["unit"] == "in ones"
    assert series[0]["unit_multiplier"] == "0"
    assert series[0]["dimensions"] == {"dval1": ["AT"], "dval2": ["BS0100510"]}
    assert series[0]["dimension_labels"] == {"dval1": "PRODUZENT", "dval2": "BANKENSEKTOR"}
    assert series[0]["observations"] == [
        {"period": "2005-B1", "value": "90.0", "unit": "in ones", "series_label": "number of foreign subsidiaries"},
        {"period": "2005-B2", "value": "90.0", "unit": "in ones", "series_label": "number of foreign subsidiaries"},
    ]


def test_parse_meta_response_extracts_metadata_and_releases():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <metainfo>
      <header>
        <prepared>2026-03-19T10:12:54Z</prepared>
        <sender id="AT2">
          <name>Oesterreichische Nationalbank</name>
        </sender>
        <last_update>2026-03-19T10:12:54Z</last_update>
      </header>
      <meta>
        <title>Loans to euro area residents - total</title>
        <region>-</region>
        <unit>Euro</unit>
        <comment>Collected within the framework of the balance sheet report to the ECB loans to euro area residents total.</comment>
        <classification>European System of National Accounts</classification>
        <breaks>-</breaks>
        <frequency>month</frequency>
        <data_available>
          <data>Jan. 98 - Feb. 26</data>
          <data>1998 - 2025</data>
        </data_available>
        <last_update>2026-03-13 08:02:12</last_update>
        <source>OeNB</source>
        <lag>-</lag>
        <releases>
          <release><release_date>Week 16/2026</release_date><reference>March 2026</reference><revision></revision></release>
          <release><release_date>Week 20/2026</release_date><reference>April 2026</reference><revision></revision></release>
        </releases>
      </meta>
    </metainfo>
    """

    metadata = parse_meta_response(xml)

    assert metadata["prepared_at"] == "2026-03-19T10:12:54Z"
    assert metadata["sender"] == {"id": "AT2", "name": "Oesterreichische Nationalbank"}
    assert metadata["title"] == "Loans to euro area residents - total"
    assert metadata["unit"] == "Euro"
    assert metadata["frequency"] == "month"
    assert metadata["data_available"] == ["Jan. 98 - Feb. 26", "1998 - 2025"]
    assert metadata["source"] == "OeNB"
    assert metadata["releases"] == [
        {"release_date": "Week 16/2026", "reference": "March 2026", "revision": ""},
        {"release_date": "Week 20/2026", "reference": "April 2026", "revision": ""},
    ]


def test_parse_content_positions_extracts_positions_from_groups():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-24T22:00:00Z</prepared>
        <sender id="AT2"><name>Oesterreichische Nationalbank</name></sender>
      </header>
      <groups>
        <group name="alle Daten">
          <position id="VDBESEFAZSPIFAGAB">
            <text lang="DE">Einlagefazilität</text>
          </position>
          <position id="VDBESSPITZEREFINZRNG">
            <text lang="DE">Spitzenrefinanzierungsfazilität</text>
          </position>
        </group>
      </groups>
    </content>
    """

    result = parse_content_positions(xml)

    assert result["prepared_at"] == "2026-03-24T22:00:00Z"
    assert len(result["positions"]) == 2
    assert result["positions"][0] == {"id": "VDBESEFAZSPIFAGAB", "text": "Einlagefazilität", "group": "alle Daten"}
    assert result["positions"][1] == {"id": "VDBESSPITZEREFINZRNG", "text": "Spitzenrefinanzierungsfazilität", "group": "alle Daten"}


def test_parse_content_positions_returns_empty_for_no_positions():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups><group name="alle Daten"></group></groups>
    </content>
    """

    result = parse_content_positions(xml)

    assert result["positions"] == []


def test_extract_hierarchy_reference_from_report_url():
    reference = extract_hierarchy_reference(
        "https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN"
    )

    assert reference is not None
    assert reference.hierid == 321
    assert reference.lang == "EN"
