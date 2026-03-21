from __future__ import annotations

import sqlite3
from datetime import datetime


def store_release_events(
    conn: sqlite3.Connection,
    *,
    metadata_id: int,
    hierid: int,
    lang: str,
    pos: str,
    source_url: str,
    releases: list[dict],
) -> int:
    """Replace release events for a metadata entry."""

    now = datetime.utcnow().isoformat() + "Z"
    conn.execute("DELETE FROM release_events WHERE metadata_id = ?", (metadata_id,))

    unique_releases = []
    seen_keys = set()
    for release in releases:
        key = (
            release["release_date"],
            release.get("reference"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_releases.append(release)

    for release in unique_releases:
        conn.execute(
            """
            INSERT INTO release_events
              (metadata_id, hierid, lang, pos, release_date_text, reference_text, revision_text, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata_id,
                hierid,
                lang,
                pos,
                release["release_date"],
                release.get("reference"),
                release.get("revision"),
                source_url,
                now,
            ),
        )

    conn.commit()
    return len(unique_releases)
