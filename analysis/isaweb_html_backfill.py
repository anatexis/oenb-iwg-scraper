"""Backfill ISAweb HTML report/release pages already stored in SQLite."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))

from oenb_scraper.database import init_db
from oenb_scraper.isaweb_store import (
    store_isaweb_release_html_response,
    store_isaweb_report_html_response,
)


def backfill_isaweb_html_pages(conn, *, limit: int | None = None) -> dict:
    report_rows = _select_report_pages(conn, limit=limit)
    release_rows = _select_release_pages(conn, limit=limit)

    report_materialized = 0
    for row in report_rows:
        dataset_id = store_isaweb_report_html_response(
            conn,
            response_url=row["url"],
            html_text=_load_body(row),
        )
        if dataset_id:
            report_materialized += 1

    release_materialized = 0
    for row in release_rows:
        metadata_id = store_isaweb_release_html_response(
            conn,
            response_url=row["url"],
            html_text=_load_body(row),
        )
        if metadata_id:
            release_materialized += 1

    return {
        "report_pages_scanned": len(report_rows),
        "report_pages_materialized": report_materialized,
        "release_pages_scanned": len(release_rows),
        "release_pages_materialized": release_materialized,
    }


def run_backfill(*, db_path: Path, limit: int | None = None) -> dict:
    conn = init_db(db_path)
    try:
        return backfill_isaweb_html_pages(conn, limit=limit)
    finally:
        conn.close()


def _select_report_pages(conn, *, limit: int | None) -> list:
    query = """
        select p.url, pb.storage, pb.compression, pb.file_path, pb.body_blob
        from pages p
        join page_bodies pb on pb.page_id = p.id
        left join isaweb_datasets d on d.source_url = p.url
        where p.url like '%/isawebstat/stabfrage/createReport?%'
          and p.content_type like 'text/html%'
          and d.id is null
        order by p.fetched_at asc, p.url asc
    """
    params: list[object] = []
    if limit is not None:
        query += " limit ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def _select_release_pages(conn, *, limit: int | None) -> list:
    query = """
        select p.url, pb.storage, pb.compression, pb.file_path, pb.body_blob
        from pages p
        join page_bodies pb on pb.page_id = p.id
        left join isaweb_metadata m on m.meta_url = p.url
        where p.url like '%/isawebstat/releasekalender/showReleaseForReport?%'
          and p.content_type like 'text/html%'
          and m.id is null
        order by p.fetched_at asc, p.url asc
    """
    params: list[object] = []
    if limit is not None:
        query += " limit ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def _load_body(row) -> bytes:
    body = row["body_blob"] if row["storage"] == "db" else Path(row["file_path"]).read_bytes()
    if row["compression"] == "gzip":
        body = gzip.decompress(body)
    return body


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill ISAweb HTML report/release pages from an existing SQLite DB")
    parser.add_argument("db_path", type=Path, help="SQLite database path")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit per report/release scan")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    summary = run_backfill(db_path=args.db_path, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
