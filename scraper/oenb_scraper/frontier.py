from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"


DEFAULT_REVISIT_HOURS = 24
RESOURCE_REVISIT_HOURS = {
    "page_document": 24,
    "standardized_table_topic": 12,
    "isaweb_entry": 12,
    "dataset_metadata": 12,
    "isaweb_dataset": 12,
    "release_event": 6,
    "html_table": 24,
    "shiny_app": 24,
    "asset_document": 48,
}


def upsert_frontier_url(
    conn: sqlite3.Connection,
    url: str,
    *,
    priority: int = 0,
    revisit_after: str | None = None,
    seen_at: str | None = None,
    scope_class: str | None = None,
    resource_kind: str | None = None,
) -> None:
    """Insert or refresh a URL in the persistent crawl frontier."""

    seen_at = seen_at or _utcnow()
    existing = conn.execute(
        """
        SELECT priority, resource_kind, revisit_after, referring_url_count
        FROM frontier_urls
        WHERE url = ?
        """,
        (url,),
    ).fetchone()

    if existing:
        keep_existing_kind = existing["priority"] > priority
        next_priority = max(existing["priority"], priority)
        next_kind = existing["resource_kind"] if keep_existing_kind else (resource_kind or existing["resource_kind"])
        next_revisit_after = _earlier_timestamp(existing["revisit_after"], revisit_after)
        conn.execute(
            """
            UPDATE frontier_urls
            SET last_seen_at = ?,
                priority = ?,
                scope_class = COALESCE(?, scope_class),
                resource_kind = ?,
                revisit_after = ?,
                active = 1,
                referring_url_count = referring_url_count + 1
            WHERE url = ?
            """,
            (seen_at, next_priority, scope_class, next_kind, next_revisit_after, url),
        )
    else:
        conn.execute(
            """
            INSERT INTO frontier_urls
              (url, discovered_at, last_seen_at, priority, scope_class, resource_kind, revisit_after)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url, seen_at, seen_at, priority, scope_class, resource_kind, revisit_after),
        )

    conn.commit()


def get_due_frontier_urls(
    conn: sqlite3.Connection,
    *,
    now: str | None = None,
    limit: int = 100,
    resource_kinds: list[str] | None = None,
) -> list[dict]:
    """Return URLs that are currently due for crawl."""

    now = now or _utcnow()
    params: list[object] = [now]
    query = """
        SELECT url, priority, last_seen_at, revisit_after, referring_url_count
        FROM frontier_urls
        WHERE active = 1
          AND (revisit_after IS NULL OR revisit_after <= ?)
    """
    if resource_kinds:
        placeholders = ", ".join("?" for _ in resource_kinds)
        query += f"\n          AND resource_kind IN ({placeholders})"
        params.extend(resource_kinds)
    query += """
        ORDER BY priority DESC, COALESCE(revisit_after, '') ASC, discovered_at ASC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_open_isaweb_report_urls(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
) -> list[str]:
    """Return unmaterialized ISAweb createReport targets discovered from page contexts."""

    rows = conn.execute(
        """
        SELECT ipc.target_url
        FROM isaweb_page_contexts ipc
        LEFT JOIN isaweb_datasets d
          ON d.source_url = ipc.target_url
        WHERE ipc.target_url LIKE '%/isawebstat/stabfrage/createReport?%'
          AND d.id IS NULL
        GROUP BY ipc.target_url, ipc.lang
        ORDER BY CASE WHEN ipc.lang = 'EN' THEN 0 ELSE 1 END,
                 COUNT(*) DESC,
                 ipc.target_url ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row[0] for row in rows]


def mark_frontier_crawled(
    conn: sqlite3.Connection,
    url: str,
    *,
    crawled_at: str | None = None,
    revisit_after: str | None = None,
) -> None:
    """Update crawl bookkeeping after a successful fetch attempt."""

    crawled_at = crawled_at or _utcnow()
    conn.execute(
        """
        UPDATE frontier_urls
        SET last_crawled_at = ?,
            revisit_after = COALESCE(?, revisit_after)
        WHERE url = ?
        """,
        (crawled_at, revisit_after, url),
    )
    conn.commit()


def schedule_revisit_after(resource_kind: str | None, *, now: str | None = None) -> str:
    """Return the next revisit timestamp for a resource kind."""

    base = _parse_timestamp(now) if now else datetime.utcnow()
    hours = RESOURCE_REVISIT_HOURS.get(resource_kind or "", DEFAULT_REVISIT_HOURS)
    return (base + timedelta(hours=hours)).isoformat() + "Z"


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _earlier_timestamp(left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if _parse_timestamp(left) <= _parse_timestamp(right) else right
