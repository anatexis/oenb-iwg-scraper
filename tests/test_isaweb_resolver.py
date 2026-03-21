import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_resolver import (
    extract_isaweb_urls_from_html,
    infer_hierid_from_chart_id,
    infer_hierid_from_report_id,
    parse_release_schedule_html,
    parse_report_table_html,
    parse_content_response,
    resolve_dataset_request_from_html,
)


def test_infer_hierid_from_report_id():
    assert infer_hierid_from_report_id("1.1.1") == 11
    assert infer_hierid_from_report_id("3.21.1") == 321


def test_infer_hierid_from_chart_id():
    assert infer_hierid_from_chart_id("1.1.1.1") == 11
    assert infer_hierid_from_chart_id("3.21.1.4") == 321


def test_parse_content_response_extracts_hierarchy_elements():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-19T10:23:04Z</prepared>
      </header>
      <content>
        <element id="1" parent="0"><text lang="EN">OeNB, Eurosystem and monetary indicators</text></element>
        <element id="11" parent="1"><text lang="EN">Balance sheet items of the Oesterreichische Nationalbank</text></element>
        <element id="321" parent="31"><text lang="EN">Number of Banks</text></element>
      </content>
    </content>
    """

    result = parse_content_response(xml)

    assert result["prepared_at"] == "2026-03-19T10:23:04Z"
    assert result["elements"] == [
        {"id": 1, "parent": 0, "text": "OeNB, Eurosystem and monetary indicators"},
        {"id": 11, "parent": 1, "text": "Balance sheet items of the Oesterreichische Nationalbank"},
        {"id": 321, "parent": 31, "text": "Number of Banks"},
    ]


def test_resolve_dataset_request_from_chart_html():
    html = """
    <html>
      <head><title>DATA Chart - Selected balance sheet items of the Oesterreichische Nationalbank - assets</title></head>
      <body>
        <input type="hidden" name="chartOld" value="1.1.1.1">
        <input type="hidden" name="selectedPosList" value="VDBFKBSC217000_2_2041_15_1187,VDBFKBSC317000_2_2041_15_1187">
        <a href="/isawebstat/stabfrage/createReport?report=1.1.1&amp;lang=EN" title="back to report"></a>
      </body>
    </html>
    """

    request = resolve_dataset_request_from_html(
        url="https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1",
        html=html,
    )

    assert request is not None
    assert request.hierid == 11
    assert request.lang == "EN"
    assert request.pos == ["VDBFKBSC217000", "VDBFKBSC317000"]
    assert request.data_url == "https://www.oenb.at/isadataservice/data?hierid=11&lang=EN&pos=VDBFKBSC217000&pos=VDBFKBSC317000"


def test_resolve_dataset_request_from_report_html():
    html = """
    <html>
      <head><title>DATA - Selected balance sheet items of the Oesterreichische Nationalbank - assets</title></head>
      <body>
        <a class="nav-link" href="/isawebstat/createChart?lang=EN&amp;chart=1.1.1.1" title="create chart"></a>
        <a class="metalink" href="javascript:;" data-metakey="VDBFKBSC217000"></a>
        <a class="metalink" href="javascript:;" data-metakey="VDBFKBSC317000"></a>
      </body>
    </html>
    """

    request = resolve_dataset_request_from_html(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=1.1.1",
        html=html,
    )

    assert request is not None
    assert request.hierid == 11
    assert request.lang == "EN"
    assert request.pos == ["VDBFKBSC217000", "VDBFKBSC317000"]


def test_extract_isaweb_urls_from_html_finds_script_and_iframe_references():
    html = """
    <html>
      <body>
        <script>
          const reportUrl = "/isawebstat/stabfrage/createReport?report=3.21.1&amp;lang=EN";
        </script>
        <iframe src="/isawebstat/createChart?chart=3.21.1.4&amp;lang=EN"></iframe>
      </body>
    </html>
    """

    urls = extract_isaweb_urls_from_html("https://www.oenb.at/en/Statistics/Standardized-Tables.html", html)

    assert urls == [
        "https://www.oenb.at/isawebstat/createChart?chart=3.21.1.4&lang=EN",
        "https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
    ]


def test_extract_isaweb_urls_from_html_ignores_static_assets():
    html = """
    <html>
      <body>
        <script>
          const reportUrl = "/isawebstat/stabfrage/createReport?report=14.8&amp;lang=EN";
          const cssUrl = "/isawebstat/css/oenb.css";
          const jsUrl = "/isawebstat/js/oenb.js";
          const webjarUrl = "/isawebstat/webjars/bootstrap/5.1.3/js/bootstrap.bundle.min.js";
        </script>
      </body>
    </html>
    """

    urls = extract_isaweb_urls_from_html("https://www.oenb.at/en/Statistics/Standardized-Tables.html", html)

    assert urls == [
        "https://www.oenb.at/isawebstat/stabfrage/createReport?report=14.8&lang=EN",
    ]


def test_parse_report_table_html_extracts_fallback_dataset_from_live_like_report_page():
    html = """
    <html lang="en">
      <head>
        <title>DATA - SDDS-CGD, Guarantees&lt;sup&gt;1&lt;/sup&gt;</title>
      </head>
      <body>
        <input type="hidden" id="metaDataUrl" data-url="/isawebstat/showMetadatenStAbfrage?lang=EN&amp;report=14.8">
        <table>
          <thead>
            <tr>
              <th></th>
              <th><span>Q1 25</span></th>
              <th><span>Q2 25</span></th>
            </tr>
            <tr>
              <th><span></span></th>
              <th colspan="2"><span>EUR million</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row"><span>Government Liabilities (Guarantees)</span></th>
              <td><span>68,804</span></td>
              <td><span>69,548</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="footer quelle" colspan="3">
                <span>Source: <a href="http://www.bmf.gv.at">Federal Ministry of Finance</a>.</span>
              </td>
            </tr>
            <tr>
              <td class="footer footnote" colspan="3">
                <sup>1</sup> Government liabilities explanatory note.
              </td>
            </tr>
          </tfoot>
        </table>
      </body>
    </html>
    """

    result = parse_report_table_html(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=14.8",
        html=html,
    )

    assert result is not None
    assert result["hierid"] == 14
    assert result["lang"] == "EN"
    assert result["report_id"] == "14.8"
    assert result["synthetic_pos"] == "REPORT:14.8"
    assert result["title"] == "SDDS-CGD, Guarantees<sup>1</sup>"
    assert result["unit"] == "EUR million"
    assert result["source"] == "Federal Ministry of Finance"
    assert result["comment"] == "Government liabilities explanatory note."
    assert result["frequency"] == "Q"
    assert result["metadata_url"] == "https://www.oenb.at/isawebstat/showMetadatenStAbfrage?lang=EN&report=14.8"
    assert result["observations"] == [
        {
            "period": "Q1 25",
            "value": "68,804",
            "unit": "EUR million",
            "series_label": "Government Liabilities (Guarantees)",
        },
        {
            "period": "Q2 25",
            "value": "69,548",
            "unit": "EUR million",
            "series_label": "Government Liabilities (Guarantees)",
        },
    ]


def test_parse_report_table_html_extracts_row_oriented_report_table():
    html = """
    <html lang="en">
      <head>
        <title>DATA - Base and Reference Rates of the Oesterreichische Nationalbank</title>
      </head>
      <body>
        <table class="popup resultTable" id="dataTable">
          <caption>
            <span class="title">Base and Reference Rates of the Oesterreichische Nationalbank</span>
          </caption>
          <thead>
            <tr>
              <th scope="col"><a class="metalink" data-metakey="VDBESBASREFGUELTIGAB">valid as of</a></th>
              <th scope="col"><a class="metalink" data-metakey="VDBESBASISZINSSATZ">Base rate</a></th>
              <th scope="col"><a class="metalink" data-metakey="VDBESREFERENZZINSATZ">Reference rate</a></th>
            </tr>
            <tr>
              <th scope="col"><span></span></th>
              <th colspan="2" scope="col"><span>% per annum</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row"><span>01.01.99</span></th>
              <td><span>2.50</span></td>
              <td><span>4.75</span></td>
            </tr>
            <tr>
              <th scope="row"><span>09.04.99</span></th>
              <td><span>2.00</span></td>
              <td><span>3.75</span></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    result = parse_report_table_html(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.1",
        html=html,
    )

    assert result is not None
    assert result["hierid"] == 2
    assert result["report_id"] == "2.1"
    assert result["unit"] == "% per annum"
    assert result["observations"] == [
        {
            "period": "01.01.99",
            "value": "2.50",
            "unit": "% per annum",
            "series_label": "Base rate",
        },
        {
            "period": "01.01.99",
            "value": "4.75",
            "unit": "% per annum",
            "series_label": "Reference rate",
        },
        {
            "period": "09.04.99",
            "value": "2.00",
            "unit": "% per annum",
            "series_label": "Base rate",
        },
        {
            "period": "09.04.99",
            "value": "3.75",
            "unit": "% per annum",
            "series_label": "Reference rate",
        },
    ]


def test_parse_report_table_html_extracts_row_headers_with_links_and_footnotes():
    html = """
    <html lang="en">
      <head>
        <title>DATA - Financial Soundness Indicators</title>
      </head>
      <body>
        <table class="popup resultTable" id="dataTable">
          <caption>
            <span class="title">Financial Soundness Indicators</span>
          </caption>
          <thead>
            <tr>
              <th scope="col"><span>&#160;</span></th>
              <th scope="col"><span>Q3 24</span></th>
              <th scope="col"><span>Q4 24</span></th>
            </tr>
            <tr>
              <th scope="col"><span></span></th>
              <th colspan="2" scope="col"><span>in %</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">
                <a class="metalink" data-metakey="VDBKIFSI01">
                  Regulatory Tier 1 capital to risk-weighted assets (CBCSDI)<sup>1</sup>
                </a>
              </th>
              <td><span>18.54</span></td>
              <td><span>18.95</span></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    result = parse_report_table_html(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",
        html=html,
    )

    assert result is not None
    assert result["hierid"] == 324
    assert result["report_id"] == "3.24.15"
    assert result["unit"] == "in %"
    assert result["frequency"] == "Q"
    assert result["observations"] == [
        {
            "period": "Q3 24",
            "value": "18.54",
            "unit": "in %",
            "series_label": "Regulatory Tier 1 capital to risk-weighted assets (CBCSDI) 1",
        },
        {
            "period": "Q4 24",
            "value": "18.95",
            "unit": "in %",
            "series_label": "Regulatory Tier 1 capital to risk-weighted assets (CBCSDI) 1",
        },
    ]


def test_parse_report_table_html_extracts_half_year_periods():
    html = """
    <html lang="en">
      <head>
        <title>DATA - Number of Banks' Subsidiaries and Branches Abroad</title>
      </head>
      <body>
        <input type="hidden" id="metaDataUrl" data-url="/isawebstat/showMetadatenStAbfrage?lang=EN&amp;report=3.2">
        <table class="popup resultTable" id="dataTable">
          <caption>
            <span class="title">Number of Banks' Subsidiaries and Branches Abroad</span>
          </caption>
          <thead>
            <tr>
              <th scope="col"><span>End of period</span></th>
              <th scope="col"><span>H1 22</span></th>
              <th scope="col"><span>H2 22</span></th>
              <th scope="col"><span>H1 23</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row"><span>Subsidiaries</span></th>
              <td><span>47</span></td>
              <td><span>49</span></td>
              <td><span>51</span></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    result = parse_report_table_html(
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.2",
        html=html,
    )

    assert result is not None
    assert result["hierid"] == 3
    assert result["report_id"] == "3.2"
    assert result["frequency"] == "H"
    assert result["metadata_url"] == "https://www.oenb.at/isawebstat/showMetadatenStAbfrage?lang=EN&report=3.2"
    assert result["observations"] == [
        {
            "period": "H1 22",
            "value": "47",
            "unit": None,
            "series_label": "Subsidiaries",
        },
        {
            "period": "H2 22",
            "value": "49",
            "unit": None,
            "series_label": "Subsidiaries",
        },
        {
            "period": "H1 23",
            "value": "51",
            "unit": None,
            "series_label": "Subsidiaries",
        },
    ]


def test_parse_release_schedule_html_extracts_release_rows_from_report_page():
    html = """
    <html lang="en">
      <head>
        <title>DATA - Publication schedule - Residential property price index (RPPI)</title>
      </head>
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
            <tr class="leer5">
              <td colspan="2">&nbsp;</td>
            </tr>
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

    result = parse_release_schedule_html(
        url="https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.6",
        html=html,
    )

    assert result is not None
    assert result["hierid"] == 6
    assert result["lang"] == "EN"
    assert result["report_id"] == "6.6"
    assert result["synthetic_pos"] == "REPORT:6.6"
    assert result["title"] == "Residential property price index (RPPI)"
    assert result["releases"] == [
        {
            "release_date": "as available",
            "reference": None,
            "revision": None,
        },
        {
            "release_date": "19.03.2026",
            "reference": "February 2026 provisional",
            "revision": "final",
        },
    ]
