import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.isaweb_coverage_audit import (
    build_coverage_report,
    collect_linked_reports,
    collect_materialized_reports,
    collect_old_discovered_reports,
    collect_unavailable_reports,
    normalize_isaweb_report_ref,
)


def test_normalize_isaweb_report_ref_handles_old_and_new_url_variants():
    assert normalize_isaweb_report_ref(
        "https://www.oenb.at/isawebstat/createChart?&lang=DE&&report=1.1.1"
    ) == "DE:1.1.1"
    assert normalize_isaweb_report_ref(
        "https://www.oenb.at/isaweb/report.do?lang=EN&report=802.1.1"
    ) == "EN:802.1.1"
    assert normalize_isaweb_report_ref(
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&original=false&report=10.4"
    ) == "EN:10.4"
    assert normalize_isaweb_report_ref(
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=801.2.1+"
    ) == "EN:801.2.1"


def test_build_coverage_report_combines_old_new_and_materialized_sources():
    old = {
        "EN:10.4": {"report_ref": "EN:10.4", "old_seen": True, "old_count": 2},
        "EN:6.9": {"report_ref": "EN:6.9", "old_seen": True, "old_count": 1},
    }
    linked = {
        "EN:10.4": {
            "report_ref": "EN:10.4",
            "linked_count": 3,
            "sample_targets": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"],
        },
        "EN:3.24.15": {
            "report_ref": "EN:3.24.15",
            "linked_count": 5,
            "sample_targets": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15"],
        },
    }
    materialized = {
        "EN:10.4": {"report_ref": "EN:10.4", "dataset_count": 1},
    }

    report = build_coverage_report(old, linked, materialized)

    assert report["summary"]["distinct_reports"] == 3
    assert report["summary"]["materialized_reports"] == 1
    assert report["summary"]["stale_old_only_reports"] == 1
    assert report["summary"]["unmaterialized_reports"] == 1
    assert report["missing_reports"][0]["report_ref"] == "EN:3.24.15"
    assert report["missing_reports"][0]["linked_count"] == 5


def test_build_coverage_report_excludes_unavailable_reports_from_missing():
    old = {
        "EN:3.24": {"report_ref": "EN:3.24", "old_seen": True, "old_count": 1},
        "EN:10.4": {"report_ref": "EN:10.4", "old_seen": True, "old_count": 1},
    }
    linked = {
        "EN:3.24": {
            "report_ref": "EN:3.24",
            "linked_count": 3,
            "sample_targets": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24"],
        },
        "EN:10.4": {
            "report_ref": "EN:10.4",
            "linked_count": 1,
            "sample_targets": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"],
        },
    }

    report = build_coverage_report(old, linked, {}, unavailable_reports={"EN:3.24"})

    assert report["summary"]["unavailable_reports"] == 1
    assert report["summary"]["unmaterialized_reports"] == 1
    assert [row["report_ref"] for row in report["missing_reports"]] == ["EN:10.4"]
    assert report["reports"][0]["report_ref"] == "EN:10.4" or report["reports"][1]["report_ref"] == "EN:10.4"
    unavailable_row = next(row for row in report["reports"] if row["report_ref"] == "EN:3.24")
    assert unavailable_row["unavailable"] is True


def test_build_coverage_report_excludes_old_only_unlinked_reports_from_missing():
    old = {
        "DE:1.1.1": {"report_ref": "DE:1.1.1", "old_seen": True, "old_count": 3},
        "EN:10.4": {"report_ref": "EN:10.4", "old_seen": True, "old_count": 1},
    }
    linked = {
        "EN:10.4": {
            "report_ref": "EN:10.4",
            "linked_count": 1,
            "sample_targets": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"],
        },
    }

    report = build_coverage_report(old, linked, {})

    assert report["summary"]["stale_old_only_reports"] == 1
    assert report["summary"]["unmaterialized_reports"] == 1
    assert [row["report_ref"] for row in report["missing_reports"]] == ["EN:10.4"]
    stale_row = next(row for row in report["reports"] if row["report_ref"] == "DE:1.1.1")
    assert stale_row["stale_old_only"] is True


def test_collect_functions_read_expected_refs_from_sqlite(tmp_path: Path):
    db_path = tmp_path / "pages.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("create table pages (id integer primary key, url text not null)")
    cur.execute(
        """
        create table isaweb_page_contexts (
            id integer primary key,
            target_url text not null
        )
        """
    )
    cur.execute(
        """
        create table isaweb_datasets (
            id integer primary key,
            source_url text
        )
        """
    )
    cur.executemany(
        "insert into pages(url) values(?)",
        [
            ("https://www.oenb.at/isawebstat/createChart?&lang=DE&&report=1.1.1",),
            ("https://www.oenb.at/isaweb/report.do?lang=EN&report=802.1.1",),
        ],
    )
    cur.executemany(
        "insert into isaweb_page_contexts(target_url) values(?)",
        [
            ("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4",),
            ("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4",),
            ("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",),
        ],
    )
    cur.execute(
        "insert into isaweb_datasets(source_url) values(?)",
        ("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&original=false&report=10.4",),
    )
    conn.commit()
    conn.close()

    old = collect_old_discovered_reports(db_path)
    linked = collect_linked_reports(db_path)
    materialized = collect_materialized_reports(db_path)

    assert "DE:1.1.1" in old
    assert "EN:802.1.1" in old
    assert linked["EN:10.4"]["linked_count"] == 2
    assert "EN:10.4" in materialized


def test_collect_unavailable_reports_reads_isaweb_error_pages(tmp_path: Path):
    db_path = tmp_path / "pages.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("create table pages (id integer primary key, url text not null)")
    cur.execute(
        """
        create table page_content (
            page_id integer primary key,
            title text,
            text_content text
        )
        """
    )
    cur.executemany(
        "insert into pages(id, url) values(?, ?)",
        [
            (1, "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24"),
            (2, "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"),
            (3, "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=801.1.11"),
            (4, "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=801.1.11"),
        ],
    )
    cur.executemany(
        "insert into page_content(page_id, title, text_content) values(?, ?, ?)",
        [
            (1, "error page", "error page The choosen report is not available!"),
            (2, "Key interest rates", "Key interest rates table"),
            (3, "error page", "error page The choosen report is not available!"),
            (4, "Fehlerseite", "Fehlerseite Der ausgewählte Bericht ist nicht verfügbar!"),
        ],
    )
    conn.commit()
    conn.close()

    unavailable = collect_unavailable_reports(db_path)

    assert unavailable == {"EN:3.24", "EN:801.1.11", "DE:801.1.11"}
