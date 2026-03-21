from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from analysis.isaweb_gap_seed_export import (
    build_seed_records,
    canonical_report_url,
    canonical_release_url,
    enqueue_gap_seed_urls,
    export_gap_seed_payload,
)


def test_canonical_urls_are_built_from_report_ref() -> None:
    assert (
        canonical_report_url("EN:10.4")
        == "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"
    )
    assert (
        canonical_release_url("DE:5.1.2")
        == "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=DE&report=5.1.2"
    )


def test_build_seed_records_prioritizes_linked_then_old_counts() -> None:
    audit_report = {
        "summary": {"unmaterialized_reports": 3},
        "missing_reports": [
            {
                "report_ref": "EN:2.4",
                "linked_count": 5,
                "old_count": 2,
                "sample_targets": [
                    "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.4"
                ],
            },
            {
                "report_ref": "DE:5.1.2",
                "linked_count": 6,
                "old_count": 1,
                "sample_targets": [],
            },
            {
                "report_ref": "EN:2.13",
                "linked_count": 5,
                "old_count": 4,
                "sample_targets": [],
            },
        ]
    }

    seeds = build_seed_records(audit_report, limit=2)

    assert [seed["report_ref"] for seed in seeds] == ["DE:5.1.2", "EN:2.13"]
    assert seeds[0]["report_url"] == (
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=5.1.2"
    )
    assert seeds[0]["release_url"] == (
        "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=DE&report=5.1.2"
    )
    assert seeds[0]["priority_score"] > seeds[1]["priority_score"]


def test_export_gap_seed_payload_writes_urls_and_metadata(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "seeds.json"
    audit_path.write_text(
        json.dumps(
            {
                "summary": {"unmaterialized_reports": 2},
                "missing_reports": [
                    {
                        "report_ref": "EN:3.2",
                        "linked_count": 6,
                        "old_count": 3,
                        "sample_targets": [],
                    },
                    {
                        "report_ref": "EN:5.1.2",
                        "linked_count": 7,
                        "old_count": 2,
                        "sample_targets": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = export_gap_seed_payload(audit_path=audit_path, output_path=output_path, limit=1)

    assert payload["summary"]["selected_reports"] == 1
    assert payload["seeds"][0]["report_ref"] == "EN:5.1.2"
    assert payload["seed_urls"] == [
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1.2",
        "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=5.1.2",
    ]
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


def test_export_gap_seed_payload_ignores_stale_old_only_refs(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "seeds.json"
    audit_path.write_text(
        json.dumps(
            {
                "summary": {"unmaterialized_reports": 1, "stale_old_only_reports": 1},
                "missing_reports": [],
                "reports": [
                    {
                        "report_ref": "DE:1.1.1",
                        "linked_count": 0,
                        "old_count": 3,
                        "stale_old_only": True,
                        "sample_targets": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = export_gap_seed_payload(audit_path=audit_path, output_path=output_path)

    assert payload["summary"]["audit_unmaterialized_reports"] == 1
    assert payload["summary"]["selected_reports"] == 0
    assert payload["seeds"] == []
    assert payload["seed_urls"] == []


def test_enqueue_gap_seed_urls_upserts_frontier_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "pages.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        create table frontier_urls (
          id integer primary key,
          url text not null unique,
          discovered_at text not null,
          last_seen_at text not null,
          last_crawled_at text,
          priority integer not null default 0,
          scope_class text,
          resource_kind text,
          revisit_after text,
          active integer not null default 1,
          referring_url_count integer not null default 1
        );
        """
    )
    conn.commit()
    conn.close()

    payload = {
        "seeds": [
            {
                "report_ref": "EN:5.1.2",
                "priority_score": 702,
                "report_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1.2",
                "release_url": "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=5.1.2",
            }
        ]
    }

    summary = enqueue_gap_seed_urls(payload=payload, frontier_db_path=db_path)

    assert summary == {"seed_reports": 1, "frontier_urls": 2}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "select url, priority, resource_kind, active from frontier_urls order by priority desc, url asc"
    ).fetchall()
    conn.close()

    assert [row["url"] for row in rows] == [
        "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=5.1.2",
        "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1.2",
    ]
    assert rows[0]["priority"] == 90
    assert rows[0]["resource_kind"] == "release_event"
    assert rows[1]["priority"] == 80
    assert rows[1]["resource_kind"] == "isaweb_entry"
