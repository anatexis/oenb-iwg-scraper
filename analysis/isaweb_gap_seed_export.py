"""Export prioritized ISAweb recrawl seeds from a coverage audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

RESOURCE_PRIORITIES = {
    "release_event": 90,
    "isaweb_entry": 80,
}


def _split_report_ref(report_ref: str) -> tuple[str, str]:
    lang, report_id = report_ref.split(":", 1)
    return lang.upper(), report_id


def canonical_report_url(report_ref: str) -> str:
    lang, report_id = _split_report_ref(report_ref)
    return f"https://www.oenb.at/isawebstat/stabfrage/createReport?lang={lang}&report={report_id}"


def canonical_release_url(report_ref: str) -> str:
    lang, report_id = _split_report_ref(report_ref)
    return (
        "https://www.oenb.at/isawebstat/releasekalender/"
        f"showReleaseForReport?lang={lang}&report={report_id}"
    )


def _priority_score(record: dict) -> int:
    linked_count = int(record.get("linked_count", 0) or 0)
    old_count = int(record.get("old_count", 0) or 0)
    return linked_count * 100 + old_count


def build_seed_records(audit_report: dict, limit: int | None = None) -> list[dict]:
    missing_reports = audit_report.get("missing_reports", [])
    ordered = sorted(
        missing_reports,
        key=lambda row: (
            -_priority_score(row),
            row.get("report_ref", ""),
        ),
    )
    if limit is not None:
        ordered = ordered[:limit]

    seeds: list[dict] = []
    for record in ordered:
        report_ref = record["report_ref"]
        seeds.append(
            {
                "report_ref": report_ref,
                "priority_score": _priority_score(record),
                "linked_count": int(record.get("linked_count", 0) or 0),
                "old_count": int(record.get("old_count", 0) or 0),
                "sample_targets": list(record.get("sample_targets", [])),
                "report_url": canonical_report_url(report_ref),
                "release_url": canonical_release_url(report_ref),
            }
        )
    return seeds


def export_gap_seed_payload(
    *,
    audit_path: Path,
    output_path: Path | None = None,
    limit: int | None = None,
) -> dict:
    audit_report = json.loads(audit_path.read_text(encoding="utf-8"))
    seeds = build_seed_records(audit_report, limit=limit)
    payload = {
        "summary": {
            "audit_unmaterialized_reports": audit_report.get("summary", {}).get("unmaterialized_reports", 0),
            "selected_reports": len(seeds),
        },
        "seeds": seeds,
        "seed_urls": [url for seed in seeds for url in (seed["report_url"], seed["release_url"])],
    }
    if output_path is not None:
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def enqueue_gap_seed_urls(*, payload: dict, frontier_db_path: Path) -> dict:
    conn = sqlite3.connect(frontier_db_path)
    conn.row_factory = sqlite3.Row
    now = datetime.utcnow().isoformat() + "Z"
    inserted = 0
    for seed in payload.get("seeds", []):
        inserted += _upsert_frontier_row(
            conn=conn,
            url=seed["report_url"],
            priority=RESOURCE_PRIORITIES["isaweb_entry"],
            resource_kind="isaweb_entry",
            seen_at=now,
            revisit_after=(datetime.utcnow() + timedelta(hours=12)).isoformat() + "Z",
        )
        inserted += _upsert_frontier_row(
            conn=conn,
            url=seed["release_url"],
            priority=RESOURCE_PRIORITIES["release_event"],
            resource_kind="release_event",
            seen_at=now,
            revisit_after=(datetime.utcnow() + timedelta(hours=6)).isoformat() + "Z",
        )
    conn.commit()
    conn.close()
    return {"seed_reports": len(payload.get("seeds", [])), "frontier_urls": inserted}


def _upsert_frontier_row(
    *,
    conn: sqlite3.Connection,
    url: str,
    priority: int,
    resource_kind: str,
    seen_at: str,
    revisit_after: str,
) -> int:
    existing = conn.execute(
        """
        select id, priority, resource_kind, revisit_after, referring_url_count
        from frontier_urls
        where url = ?
        """,
        (url,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            update frontier_urls
            set last_seen_at = ?,
                priority = ?,
                resource_kind = ?,
                revisit_after = ?,
                active = 1,
                referring_url_count = referring_url_count + 1
            where url = ?
            """,
            (
                seen_at,
                max(existing["priority"], priority),
                resource_kind if priority >= existing["priority"] else existing["resource_kind"],
                revisit_after,
                url,
            ),
        )
        return 1

    conn.execute(
        """
        insert into frontier_urls
          (url, discovered_at, last_seen_at, priority, resource_kind, revisit_after, active, referring_url_count)
        values (?, ?, ?, ?, ?, ?, 1, 1)
        """,
        (url, seen_at, seen_at, priority, resource_kind, revisit_after),
    )
    return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export prioritized ISAweb gap seeds from an audit JSON file")
    parser.add_argument("--audit", type=Path, required=True, help="Path to isaweb coverage audit JSON")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path for seed JSON")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of report refs to export")
    parser.add_argument("--frontier-db", type=Path, default=None, help="Optional frontier DB to enqueue exported seeds into")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    payload = export_gap_seed_payload(audit_path=args.audit, output_path=args.output, limit=args.limit)
    if args.frontier_db is not None:
        enqueue_gap_seed_urls(payload=payload, frontier_db_path=args.frontier_db)
    if args.output is None:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
