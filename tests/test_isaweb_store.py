import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db
from oenb_scraper.isaweb_store import (
    store_isaweb_content_response,
    canonical_dataset_key,
    store_isaweb_data_response,
    store_isaweb_dataset,
    store_isaweb_meta_response,
    store_isaweb_observations,
    store_isaweb_page_context,
    store_isaweb_release_html_response,
    store_isaweb_report_html_response,
)


def test_store_isaweb_dataset_with_canonical_key(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    dataset_id = store_isaweb_dataset(
        conn,
        hierid=11,
        lang="DE",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"], "dval2": ["00100KI"]},
        freq="M",
        title="Leitzinssätze",
        source_url="https://www.oenb.at/isawebstat/createChart?lang=DE&chart=10.4.1",
    )

    row = conn.execute(
        "SELECT dataset_key, title, source_url, freq FROM isaweb_datasets WHERE id = ?",
        (dataset_id,),
    ).fetchone()

    assert row["dataset_key"] == canonical_dataset_key(
        hierid=11,
        lang="DE",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"], "dval2": ["00100KI"]},
        freq="M",
    )
    assert row["title"] == "Leitzinssätze"
    assert row["source_url"] == "https://www.oenb.at/isawebstat/createChart?lang=DE&chart=10.4.1"
    assert row["freq"] == "M"


def test_store_isaweb_observations_appends_rows(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    dataset_id = store_isaweb_dataset(
        conn,
        hierid=11,
        lang="EN",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"]},
        freq="M",
        title="Base rates",
        source_url="https://www.oenb.at/isawebstat/createChart?lang=EN&chart=10.4.1",
    )

    store_isaweb_observations(
        conn,
        dataset_id=dataset_id,
        observations=[
            {"period": "2025-01", "value": "2.15", "unit": "%", "series_label": "Euro area"},
            {"period": "2025-02", "value": "2.15", "unit": "%", "series_label": "Euro area"},
        ],
    )

    row = conn.execute(
        "SELECT COUNT(*) AS count FROM isaweb_observations WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()

    assert row["count"] == 2


def test_store_isaweb_observations_replaces_existing_rows_for_same_dataset(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    dataset_id = store_isaweb_dataset(
        conn,
        hierid=11,
        lang="EN",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"]},
        freq="M",
        title="Base rates",
        source_url="https://www.oenb.at/isadataservice/data?hierid=11&lang=EN&pos=VDBFKBSC217000&dval1=AT&freq=M",
    )

    store_isaweb_observations(
        conn,
        dataset_id=dataset_id,
        observations=[
            {"period": "2025-01", "value": "2.15", "unit": "%", "series_label": "Euro area"},
            {"period": "2025-02", "value": "2.15", "unit": "%", "series_label": "Euro area"},
        ],
    )
    store_isaweb_observations(
        conn,
        dataset_id=dataset_id,
        observations=[
            {"period": "2025-02", "value": "2.00", "unit": "%", "series_label": "Euro area"},
        ],
    )

    rows = conn.execute(
        """
        SELECT period, value
        FROM isaweb_observations
        WHERE dataset_id = ?
        ORDER BY period
        """,
        (dataset_id,),
    ).fetchall()

    assert [(row["period"], row["value"]) for row in rows] == [("2025-02", "2.00")]


def test_store_isaweb_data_response_materializes_multiple_series(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    xml = """
    <OeNBData>
      <data>
        <dataSet pos="VDBKISDANZTAU" posTitle="number of foreign subsidiaries" attr1="AT" attr2="BS0100510" attr3="Z5" attr4="Z0Z" attr1Dim="PRODUZENT" attr2Dim="BANKENSEKTOR" attr3Dim="REGION" attr4Dim="WAEHRUNG" freq="H" unitMult="0" unitText="in ones">
          <values>
            <obs value="90.0" periode="2005-B1"/>
            <obs value="90.0" periode="2005-B2"/>
          </values>
        </dataSet>
        <dataSet pos="VDBKISDANZTEU" posTitle="number of foreign subsidiaries hereof in the EU" attr1="AT" attr2="BS0100510" attr3="Z5" attr4="Z0Z" attr1Dim="PRODUZENT" attr2Dim="BANKENSEKTOR" attr3Dim="REGION" attr4Dim="WAEHRUNG" freq="H" unitMult="0" unitText="in ones">
          <values>
            <obs value="45.0" periode="2005-B1"/>
          </values>
        </dataSet>
      </data>
    </OeNBData>
    """

    stored = store_isaweb_data_response(
        conn,
        response_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBKISDANZTAU&pos=VDBKISDANZTEU&freq=H&starttime=200501",
        xml_text=xml,
    )

    dataset_count = conn.execute("SELECT COUNT(*) AS count FROM isaweb_datasets").fetchone()["count"]
    observation_count = conn.execute("SELECT COUNT(*) AS count FROM isaweb_observations").fetchone()["count"]
    first_dataset = conn.execute(
        """
        SELECT hierid, lang, freq, title
        FROM isaweb_datasets
        ORDER BY title
        LIMIT 1
        """
    ).fetchone()

    assert stored == 2
    assert dataset_count == 2
    assert observation_count == 3
    assert first_dataset["hierid"] == 321
    assert first_dataset["lang"] == "EN"
    assert first_dataset["freq"] == "H"


def test_store_isaweb_meta_response_persists_metadata_and_release_events(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
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

    metadata_id = store_isaweb_meta_response(
        conn,
        response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=11&pos=VDBFKBSC217000",
        xml_text=xml,
    )

    metadata_row = conn.execute(
        """
        SELECT hierid, lang, pos, title, unit, frequency, source, data_available_json
        FROM isaweb_metadata
        WHERE id = ?
        """,
        (metadata_id,),
    ).fetchone()
    release_count = conn.execute(
        "SELECT COUNT(*) AS count FROM release_events WHERE metadata_id = ?",
        (metadata_id,),
    ).fetchone()["count"]

    assert metadata_row["hierid"] == 11
    assert metadata_row["lang"] == "EN"
    assert metadata_row["pos"] == "VDBFKBSC217000"
    assert metadata_row["title"] == "Loans to euro area residents - total"
    assert metadata_row["unit"] == "Euro"
    assert metadata_row["frequency"] == "month"
    assert metadata_row["source"] == "OeNB"
    assert json.loads(metadata_row["data_available_json"]) == ["Jan. 98 - Feb. 26", "1998 - 2025"]
    assert release_count == 2


def test_store_isaweb_content_response_persists_hierarchy_context(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-19T10:23:04Z</prepared>
      </header>
      <content>
        <element id="3" parent="0"><text lang="EN">Financial institutions</text></element>
        <element id="31" parent="3"><text lang="EN">Banks</text></element>
        <element id="321" parent="31"><text lang="EN">Number of Banks</text></element>
      </content>
    </content>
    """

    stored = store_isaweb_content_response(
        conn,
        response_url="https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1",
        xml_text=xml,
    )

    row = conn.execute(
        """
        SELECT node_id, parent_id, lang, label, section_id, section_label, family_id, family_label, path_json
        FROM isaweb_content_nodes
        WHERE node_id = 321 AND lang = 'EN'
        """
    ).fetchone()

    assert stored == 3
    assert row["node_id"] == 321
    assert row["parent_id"] == 31
    assert row["label"] == "Number of Banks"
    assert row["section_id"] == 3
    assert row["section_label"] == "Financial institutions"
    assert row["family_id"] == 31
    assert row["family_label"] == "Banks"
    assert json.loads(row["path_json"]) == [3, 31, 321]


def test_store_isaweb_page_context_resolves_labels_from_existing_content(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-19T10:23:04Z</prepared>
      </header>
      <content>
        <element id="3" parent="0"><text lang="EN">Financial institutions</text></element>
        <element id="31" parent="3"><text lang="EN">Banks</text></element>
        <element id="321" parent="31"><text lang="EN">Number of Banks</text></element>
      </content>
    </content>
    """
    store_isaweb_content_response(
        conn,
        response_url="https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1",
        xml_text=xml,
    )

    context_id = store_isaweb_page_context(
        conn,
        source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html",
        target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
        link_text="Number of Banks",
        section_heading="Financial institutions",
        relation_kind="isaweb_entry",
    )

    row = conn.execute(
        """
        SELECT source_url, target_url, hierid, lang, section_id, section_label, family_id, family_label
        FROM isaweb_page_contexts
        WHERE id = ?
        """,
        (context_id,),
    ).fetchone()

    assert row["source_url"] == "https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html"
    assert row["target_url"] == "https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN"
    assert row["hierid"] == 321
    assert row["lang"] == "EN"
    assert row["section_id"] == 3
    assert row["section_label"] == "Financial institutions"
    assert row["family_id"] == 31
    assert row["family_label"] == "Banks"


def test_store_isaweb_release_html_response_attaches_release_events_to_report_metadata(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    report_html = """
    <html lang="en">
      <head><title>DATA - Residential property price index (RPPI)</title></head>
      <body>
        <table class="popup resultTable" id="dataTable">
          <caption>
            <span class="title">Residential property price index (RPPI)</span>
          </caption>
          <thead>
            <tr>
              <th></th>
              <th><span>2024</span></th>
              <th><span>2025</span></th>
            </tr>
            <tr>
              <th><span></span></th>
              <th colspan="2"><span>Index</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row"><span>Austria - Residential Property Price Index 2000=100 hedonic regr model</span></th>
              <td><span>257.8</span></td>
              <td><span>266.9</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="footer quelle" colspan="3">
                <span>Source: <a href="https://www.oenb.at">OeNB</a>.</span>
              </td>
            </tr>
          </tfoot>
        </table>
      </body>
    </html>
    """
    store_isaweb_report_html_response(
        conn,
        response_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6",
        html_text=report_html,
    )

    release_html = """
    <html lang="en">
      <head><title>DATA - Publication schedule - Residential property price index (RPPI)</title></head>
      <body>
        <table class="popup resultTable" id="releasetable">
          <caption>
            <span class="title">Residential property price index (RPPI)</span>
          </caption>
          <thead>
            <tr>
              <th>release strategy</th>
              <th>release date</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="txt1 alignLeft"></td>
              <td class="txt3 alignLeft"><b>as available</b><br/></td>
            </tr>
            <tr>
              <td class="txt1 alignLeft">final</td>
              <td class="txt3 alignLeft"><b>19.03.2026</b><br/>February 2026 provisional</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    metadata_id = store_isaweb_release_html_response(
        conn,
        response_url="https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",
        html_text=release_html,
    )

    metadata = conn.execute(
        """
        SELECT pos, title, source
        FROM isaweb_metadata
        WHERE id = ?
        """,
        (metadata_id,),
    ).fetchone()
    releases = conn.execute(
        """
        SELECT release_date_text, reference_text, revision_text, source_url
        FROM release_events
        WHERE metadata_id = ?
        ORDER BY id
        """,
        (metadata_id,),
    ).fetchall()

    assert metadata["pos"] == "REPORT:6.6"
    assert metadata["title"] == "Residential property price index (RPPI)"
    assert metadata["source"] == "OeNB"
    assert [(row["release_date_text"], row["reference_text"], row["revision_text"]) for row in releases] == [
        ("as available", None, None),
        ("19.03.2026", "February 2026 provisional", "final"),
    ]
    assert all(
        row["source_url"] == "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6"
        for row in releases
    )


def test_store_isaweb_content_response_backfills_existing_page_contexts(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    context_id = store_isaweb_page_context(
        conn,
        source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions.html",
        target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
        link_text="Number of Banks",
        section_heading="Financial institutions",
        relation_kind="isaweb_entry",
    )

    before = conn.execute(
        """
        SELECT section_id, family_id
        FROM isaweb_page_contexts
        WHERE id = ?
        """,
        (context_id,),
    ).fetchone()

    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-19T10:23:04Z</prepared>
      </header>
      <content>
        <element id="3" parent="0"><text lang="EN">Financial institutions</text></element>
        <element id="31" parent="3"><text lang="EN">Banks</text></element>
        <element id="321" parent="31"><text lang="EN">Number of Banks</text></element>
      </content>
    </content>
    """
    store_isaweb_content_response(
        conn,
        response_url="https://www.oenb.at/isadataservice/content?lang=EN&report=3.21.1",
        xml_text=xml,
    )

    after = conn.execute(
        """
        SELECT section_id, section_label, family_id, family_label
        FROM isaweb_page_contexts
        WHERE id = ?
        """,
        (context_id,),
    ).fetchone()

    assert before["section_id"] is None
    assert before["family_id"] is None
    assert after["section_id"] == 3
    assert after["section_label"] == "Financial institutions"
    assert after["family_id"] == 31
    assert after["family_label"] == "Banks"


def test_store_isaweb_report_html_response_materializes_descriptive_table_without_time_series(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    report_html = """
    <html lang="en">
      <head>
        <title>DATA - Schilling Banknotes Eligible for Exchange</title>
      </head>
      <body>
        <input type="hidden" id="metaDataUrl" data-url="/isawebstat/showMetadatenStAbfrage?lang=EN&amp;report=5.1.2">
        <table class="popup resultTable" id="dataTable">
          <caption>
            <span class="title">Schilling Banknotes Eligible for Exchange</span>
          </caption>
          <thead>
            <tr>
              <th scope="col"><span>Denomination</span></th>
              <th scope="col"><span>Portrait featured on the front</span></th>
              <th scope="col"><span>Date</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span>1000 schilling</span></td>
              <td><span>Karl Landsteiner</span></td>
              <td><span>1983</span></td>
            </tr>
            <tr>
              <td><span>5000 schilling</span></td>
              <td><span>Wolfgang Amadeus Mozart</span></td>
              <td><span>1989</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="footer quelle" colspan="3">
                <span>Source: <a href="https://www.oenb.at">OeNB</a>.</span>
              </td>
            </tr>
            <tr>
              <td class="footer footnote" colspan="3">
                <sup>1</sup> These banknotes ceased to be legal tender on February 28, 2002.
              </td>
            </tr>
          </tfoot>
        </table>
      </body>
    </html>
    """

    dataset_id = store_isaweb_report_html_response(
        conn,
        response_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1.2",
        html_text=report_html,
    )

    dataset = conn.execute(
        """
        SELECT hierid, lang, freq, title, source_url
        FROM isaweb_datasets
        WHERE id = ?
        """,
        (dataset_id,),
    ).fetchone()
    metadata = conn.execute(
        """
        SELECT pos, title, source, comment
        FROM isaweb_metadata
        WHERE pos = 'REPORT:5.1.2'
        """,
    ).fetchone()
    observation_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM isaweb_observations
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    ).fetchone()["count"]

    assert dataset_id > 0
    assert dataset["hierid"] == 51
    assert dataset["lang"] == "EN"
    assert dataset["freq"] is None
    assert dataset["title"] == "Schilling Banknotes Eligible for Exchange"
    assert metadata["pos"] == "REPORT:5.1.2"
    assert metadata["title"] == "Schilling Banknotes Eligible for Exchange"
    assert metadata["source"] == "OeNB"
    assert metadata["comment"] == "These banknotes ceased to be legal tender on February 28, 2002."
    assert observation_count == 0
