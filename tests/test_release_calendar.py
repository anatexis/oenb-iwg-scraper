import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db
from oenb_scraper.release_calendar import store_release_events


def test_release_event_links_back_to_dataset_family(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    cursor = conn.execute(
        """
        INSERT INTO isaweb_metadata
          (meta_key, hierid, lang, pos, meta_url, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "hierid=11|lang=EN|pos=VDBFKBSC217000",
            11,
            "EN",
            "VDBFKBSC217000",
            "https://www.oenb.at/isadataservice/meta?lang=EN&hierid=11&pos=VDBFKBSC217000",
            "Base rates",
            "2026-03-19T10:12:54Z",
            "2026-03-19T10:12:54Z",
        ),
    )
    metadata_id = cursor.lastrowid
    conn.commit()

    stored = store_release_events(
        conn,
        metadata_id=metadata_id,
        hierid=11,
        lang="EN",
        pos="VDBFKBSC217000",
        source_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=11&pos=VDBFKBSC217000",
        releases=[
            {"release_date": "Week 16/2026", "reference": "March 2026", "revision": ""},
            {"release_date": "Week 20/2026", "reference": "April 2026", "revision": ""},
        ],
    )

    row = conn.execute(
        """
        SELECT metadata_id, hierid, lang, pos, release_date_text, reference_text
        FROM release_events
        ORDER BY release_date_text
        LIMIT 1
        """
    ).fetchone()

    assert stored == 2
    assert row["metadata_id"] == metadata_id
    assert row["hierid"] == 11
    assert row["lang"] == "EN"
    assert row["pos"] == "VDBFKBSC217000"
    assert row["release_date_text"] == "Week 16/2026"
    assert row["reference_text"] == "March 2026"


def test_store_release_events_deduplicates_identical_rows(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    cursor = conn.execute(
        """
        INSERT INTO isaweb_metadata
          (meta_key, hierid, lang, pos, meta_url, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "hierid=51|lang=DE|pos=REPORT:5.1.2",
            51,
            "DE",
            "REPORT:5.1.2",
            "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=DE&report=5.1.2",
            "Umtauschbare Schilling-Banknoten",
            "2026-03-20T12:00:00Z",
            "2026-03-20T12:00:00Z",
        ),
    )
    metadata_id = cursor.lastrowid
    conn.commit()

    stored = store_release_events(
        conn,
        metadata_id=metadata_id,
        hierid=51,
        lang="DE",
        pos="REPORT:5.1.2",
        source_url="https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=DE&report=5.1.2",
        releases=[
            {"release_date": "nach Verfügbarkeit", "reference": None, "revision": "final"},
            {"release_date": "nach Verfügbarkeit", "reference": None, "revision": "final"},
        ],
    )

    rows = conn.execute(
        "select release_date_text, reference_text, revision_text from release_events"
    ).fetchall()

    assert stored == 1
    assert [(row["release_date_text"], row["reference_text"], row["revision_text"]) for row in rows] == [
        ("nach Verfügbarkeit", None, "final"),
    ]
