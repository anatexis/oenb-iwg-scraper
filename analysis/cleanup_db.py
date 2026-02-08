"""One-time cleanup: deduplicate pages with session IDs in URLs."""
import sqlite3
from pathlib import Path
from urllib.parse import urldefrag, urlparse, parse_qs, urlencode

SESSION_PARAMS = {'jsessionid', 'JSESSIONID', 'PHPSESSID', 'sid', 'session_id'}


def normalize_url(url: str) -> str:
    """Normalize URL by removing session IDs and sorting query params."""
    url = urldefrag(url)[0]
    parsed = urlparse(url)

    path = parsed.path
    for token in (';jsessionid=', ';JSESSIONID='):
        if token in path:
            path = path.split(token)[0]

    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query_params.items() if k not in SESSION_PARAMS}
    sorted_query = urlencode(sorted(filtered.items()), doseq=True)

    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if sorted_query:
        normalized += f"?{sorted_query}"
    return normalized


def dedup_pages(db_path: Path) -> int:
    """Remove duplicate pages, keeping the one with the newest fetched_at.

    Returns number of removed pages.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    rows = conn.execute("SELECT id, url FROM pages").fetchall()

    # Group by normalized URL
    groups = {}
    for page_id, url in rows:
        norm = normalize_url(url)
        groups.setdefault(norm, []).append(page_id)

    removed = 0
    for norm_url, page_ids in groups.items():
        if len(page_ids) <= 1:
            continue

        # Keep the one with latest fetched_at
        keep_id = conn.execute(
            f"SELECT id FROM pages WHERE id IN ({','.join('?' * len(page_ids))}) ORDER BY fetched_at DESC LIMIT 1",
            page_ids
        ).fetchone()[0]

        delete_ids = [pid for pid in page_ids if pid != keep_id]

        # Update the kept page's URL to the normalized form
        conn.execute("UPDATE pages SET url = ? WHERE id = ?", (norm_url, keep_id))

        # Delete duplicates (CASCADE deletes page_bodies and page_content)
        conn.execute(
            f"DELETE FROM pages WHERE id IN ({','.join('?' * len(delete_ids))})",
            delete_ids
        )
        removed += len(delete_ids)

    conn.commit()
    conn.close()
    return removed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deduplicate pages in SQLite DB")
    parser.add_argument("db_path", type=Path, help="Path to pages.db")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    args = parser.parse_args()

    removed = dedup_pages(args.db_path)
    print(f"Removed {removed:,} duplicate pages")
