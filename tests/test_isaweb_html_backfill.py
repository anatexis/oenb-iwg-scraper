from __future__ import annotations

import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db, store_page

from analysis.isaweb_html_backfill import backfill_isaweb_html_pages


def _store_html_page(conn, *, url: str, html: str) -> None:
    store_page(
        conn,
        run_id=None,
        url=url,
        final_url=url,
        status_code=200,
        content_type="text/html;charset=UTF-8",
        body=html.encode("utf-8"),
    )


def test_backfill_materializes_report_and_release_html_from_existing_pages(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "crawler.db")

    report_html = """
    <html lang="de">
      <head><title>DATA - Umtauschbare Schilling-Banknoten</title></head>
      <body>
        <input type="hidden" id="metaDataUrl" data-url="/isawebstat/showMetadatenStAbfrage?lang=DE&amp;report=5.1.2">
        <table class="popup resultTable" id="dataTable">
          <caption><span class="title">Umtauschbare Schilling-Banknoten</span></caption>
          <thead>
            <tr>
              <th><span>Nominale</span></th>
              <th><span>Portrait</span></th>
              <th><span>Datum</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span>S 5000/I. Form</span></td>
              <td><span>Wolfgang A. Mozart</span></td>
              <td><span>04.01.1988</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="footer quelle" colspan="3">
                <span>Quelle: <a href="https://www.oenb.at">OeNB</a>.</span>
              </td>
            </tr>
          </tfoot>
        </table>
      </body>
    </html>
    """
    release_html = """
    <html lang="de">
      <head><title>DATA - Veröffentlichungstermine - Umtauschbare Schilling-Banknoten</title></head>
      <body>
        <table class="popup resultTable" id="releasetable">
          <caption><span class="title">Umtauschbare Schilling-Banknoten</span></caption>
          <thead>
            <tr><th>Veröffentlichungsstrategie</th><th>Veröffentlichungstermin</th></tr>
          </thead>
          <tbody>
            <tr><td class="txt1 alignLeft">final</td><td class="txt3 alignLeft"><b>nach Verfügbarkeit</b></td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    _store_html_page(
        conn,
        url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=5.1.2",
        html=report_html,
    )
    _store_html_page(
        conn,
        url="https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=DE&report=5.1.2",
        html=release_html,
    )

    summary = backfill_isaweb_html_pages(conn, limit=20)

    dataset = conn.execute(
        "select dataset_key, hierid, lang, title from isaweb_datasets where source_url like '%report=5.1.2%'"
    ).fetchone()
    metadata = conn.execute(
        "select pos, lang, title, source from isaweb_metadata where pos = 'REPORT:5.1.2' and lang = 'DE'"
    ).fetchone()
    releases = conn.execute(
        "select release_date_text from release_events"
    ).fetchall()

    assert summary["report_pages_scanned"] == 1
    assert summary["report_pages_materialized"] == 1
    assert summary["release_pages_scanned"] == 1
    assert summary["release_pages_materialized"] == 1
    assert dataset["dataset_key"] == "hierid=51|lang=DE|pos=REPORT:5.1.2|report_id=5.1.2"
    assert dataset["title"] == "Umtauschbare Schilling-Banknoten"
    assert metadata["title"] == "Umtauschbare Schilling-Banknoten"
    assert metadata["source"] == "OeNB"
    assert [row["release_date_text"] for row in releases] == ["nach Verfügbarkeit"]
