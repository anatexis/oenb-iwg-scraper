"""Audit ISAweb coverage across old and rebuilt crawl artifacts."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def normalize_isaweb_report_ref(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    report = (query.get("report") or [None])[0]
    lang = (query.get("lang") or [None])[0]
    if not report or not lang:
        return None
    report = report.strip().rstrip("+").strip()
    if not report:
        return None
    return f"{lang.upper()}:{report}"


def collect_old_discovered_reports(db_path: Path) -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result: dict[str, dict] = {}
    for (url,) in cur.execute("select url from pages where url like '%isaweb%'"):
        report_ref = normalize_isaweb_report_ref(url)
        if not report_ref:
            continue
        entry = result.setdefault(report_ref, {"report_ref": report_ref, "old_seen": True, "old_count": 0})
        entry["old_count"] += 1
    conn.close()
    return result


def collect_linked_reports(db_path: Path) -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result: dict[str, dict] = {}
    for (target_url,) in cur.execute("select target_url from isaweb_page_contexts where target_url like '%report=%'"):
        report_ref = normalize_isaweb_report_ref(target_url)
        if not report_ref:
            continue
        entry = result.setdefault(
            report_ref,
            {
                "report_ref": report_ref,
                "linked_count": 0,
                "sample_targets": [],
            },
        )
        entry["linked_count"] += 1
        if target_url not in entry["sample_targets"] and len(entry["sample_targets"]) < 5:
            entry["sample_targets"].append(target_url)
    conn.close()
    return result


def collect_materialized_reports(db_path: Path) -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result: dict[str, dict] = {}
    for (source_url,) in cur.execute("select source_url from isaweb_datasets where source_url is not null"):
        report_ref = normalize_isaweb_report_ref(source_url)
        if not report_ref:
            continue
        entry = result.setdefault(report_ref, {"report_ref": report_ref, "dataset_count": 0})
        entry["dataset_count"] += 1
    conn.close()
    return result


def collect_unavailable_reports(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result: set[str] = set()
    query = """
        select p.url, pc.title, pc.text_content
        from pages p
        join page_content pc on pc.page_id = p.id
        where p.url like '%report=%'
    """
    for url, title, text_content in cur.execute(query):
        report_ref = normalize_isaweb_report_ref(url)
        if not report_ref:
            continue
        title_text = (title or "").strip().lower()
        content_text = (text_content or "").strip().lower()
        is_english_unavailable = title_text == "error page" and "report is not available" in content_text
        is_german_unavailable = title_text == "fehlerseite" and "bericht ist nicht verfügbar" in content_text
        if is_english_unavailable or is_german_unavailable:
            result.add(report_ref)
    conn.close()
    return result


def build_coverage_report(
    old_discovered: dict[str, dict],
    linked_reports: dict[str, dict],
    materialized_reports: dict[str, dict],
    unavailable_reports: set[str] | None = None,
) -> dict:
    unavailable_reports = unavailable_reports or set()
    refs = sorted(set(old_discovered) | set(linked_reports) | set(materialized_reports))
    records = []
    missing = []
    for report_ref in refs:
        old_seen = report_ref in old_discovered
        linked_count = linked_reports.get(report_ref, {}).get("linked_count", 0)
        materialized = report_ref in materialized_reports
        unavailable = report_ref in unavailable_reports
        stale_old_only = old_seen and linked_count == 0 and not materialized and not unavailable
        record = {
            "report_ref": report_ref,
            "old_seen": old_seen,
            "old_count": old_discovered.get(report_ref, {}).get("old_count", 0),
            "linked_count": linked_count,
            "materialized": materialized,
            "unavailable": unavailable,
            "stale_old_only": stale_old_only,
            "dataset_count": materialized_reports.get(report_ref, {}).get("dataset_count", 0),
            "sample_targets": linked_reports.get(report_ref, {}).get("sample_targets", []),
        }
        records.append(record)
        if not record["materialized"] and not record["unavailable"] and not record["stale_old_only"]:
            missing.append(record)

    missing.sort(key=lambda row: (-row["linked_count"], -row["old_count"], row["report_ref"]))
    return {
        "summary": {
            "distinct_reports": len(records),
            "old_discovered_reports": sum(1 for row in records if row["old_seen"]),
            "linked_reports": sum(1 for row in records if row["linked_count"] > 0),
            "materialized_reports": sum(1 for row in records if row["materialized"]),
            "unavailable_reports": sum(1 for row in records if row["unavailable"]),
            "stale_old_only_reports": sum(1 for row in records if row["stale_old_only"]),
            "unmaterialized_reports": sum(
                1
                for row in records
                if not row["materialized"] and not row["unavailable"] and not row["stale_old_only"]
            ),
        },
        "reports": records,
        "missing_reports": missing,
    }


def run_isaweb_coverage_audit(*, old_db_path: Path, new_db_path: Path) -> dict:
    old = collect_old_discovered_reports(old_db_path)
    linked = collect_linked_reports(new_db_path)
    materialized = collect_materialized_reports(new_db_path)
    unavailable = collect_unavailable_reports(new_db_path)
    return build_coverage_report(old, linked, materialized, unavailable)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit ISAweb coverage between old and rebuilt crawls")
    parser.add_argument("--old-db", type=Path, required=True, help="Old crawl SQLite DB path")
    parser.add_argument("--new-db", type=Path, required=True, help="Rebuilt crawl SQLite DB path")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    report = run_isaweb_coverage_audit(old_db_path=args.old_db, new_db_path=args.new_db)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
