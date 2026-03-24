"""SQLite database for storing crawled pages and extracted content."""
import gzip
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from oenb_scraper.freshness import should_reextract_content

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crawl_runs (
  id          INTEGER PRIMARY KEY,
  seed_url    TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  user_agent  TEXT
);

CREATE TABLE IF NOT EXISTS pages (
  id               INTEGER PRIMARY KEY,
  crawl_run_id     INTEGER REFERENCES crawl_runs(id) ON DELETE SET NULL,
  url              TEXT NOT NULL UNIQUE,
  final_url        TEXT,
  status_code      INTEGER,
  content_type     TEXT,
  fetched_at       TEXT,
  fetch_ms         INTEGER,
  bytes_downloaded INTEGER,
  etag             TEXT,
  last_modified    TEXT,
  body_hash        TEXT,
  headers_json     TEXT,
  fetch_error      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pages_fetched_at ON pages(fetched_at);
CREATE INDEX IF NOT EXISTS idx_pages_body_hash  ON pages(body_hash);
CREATE INDEX IF NOT EXISTS idx_pages_final_url  ON pages(final_url);

CREATE TABLE IF NOT EXISTS page_bodies (
  page_id      INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  storage      TEXT NOT NULL CHECK(storage IN ('file','db')),
  compression  TEXT NOT NULL DEFAULT 'gzip' CHECK(compression IN ('none','gzip','zstd')),
  file_path    TEXT,
  body_blob    BLOB
);

CREATE TABLE IF NOT EXISTS page_content (
  page_id           INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  title             TEXT,
  text_content      TEXT,
  page_section      TEXT,
  language          TEXT,
  extracted_at      TEXT,
  extractor_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_section ON page_content(page_section);

CREATE TABLE IF NOT EXISTS asset_documents (
  page_id            INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  asset_type         TEXT NOT NULL,
  extraction_status  TEXT NOT NULL,
  text_content       TEXT,
  metadata_json      TEXT,
  body_hash          TEXT,
  extracted_at       TEXT NOT NULL,
  extractor_version  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_documents_type
  ON asset_documents(asset_type, extraction_status);

CREATE TABLE IF NOT EXISTS frontier_urls (
  id                  INTEGER PRIMARY KEY,
  url                 TEXT NOT NULL UNIQUE,
  discovered_at       TEXT NOT NULL,
  last_seen_at        TEXT NOT NULL,
  last_crawled_at     TEXT,
  priority            INTEGER NOT NULL DEFAULT 0,
  scope_class         TEXT,
  resource_kind       TEXT,
  revisit_after       TEXT,
  active              INTEGER NOT NULL DEFAULT 1,
  referring_url_count INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_frontier_due
  ON frontier_urls(active, revisit_after, priority);

CREATE TABLE IF NOT EXISTS resource_links (
  id                    INTEGER PRIMARY KEY,
  source_url            TEXT NOT NULL,
  target_url            TEXT NOT NULL,
  normalized_target_url TEXT NOT NULL,
  link_text             TEXT,
  section_heading       TEXT,
  resource_kind         TEXT,
  embed_type            TEXT,
  discovered_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resource_links_target
  ON resource_links(normalized_target_url);

CREATE TABLE IF NOT EXISTS resource_versions (
  id             INTEGER PRIMARY KEY,
  url            TEXT NOT NULL,
  body_hash      TEXT,
  fetched_at     TEXT NOT NULL,
  etag           TEXT,
  last_modified  TEXT,
  status_code    INTEGER,
  UNIQUE(url, body_hash, fetched_at)
);

CREATE TABLE IF NOT EXISTS isaweb_datasets (
  id          INTEGER PRIMARY KEY,
  dataset_key TEXT NOT NULL UNIQUE,
  hierid      INTEGER NOT NULL,
  lang        TEXT NOT NULL,
  freq        TEXT,
  title       TEXT,
  source_url  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_isaweb_datasets_hierid
  ON isaweb_datasets(hierid, lang, freq);

CREATE TABLE IF NOT EXISTS isaweb_dimensions (
  id              INTEGER PRIMARY KEY,
  dataset_id      INTEGER NOT NULL REFERENCES isaweb_datasets(id) ON DELETE CASCADE,
  dimension_key   TEXT NOT NULL,
  dimension_value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_isaweb_dimensions_dataset
  ON isaweb_dimensions(dataset_id, dimension_key);

CREATE TABLE IF NOT EXISTS isaweb_observations (
  id           INTEGER PRIMARY KEY,
  dataset_id   INTEGER NOT NULL REFERENCES isaweb_datasets(id) ON DELETE CASCADE,
  period       TEXT NOT NULL,
  value        TEXT,
  unit         TEXT,
  series_label TEXT,
  created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_isaweb_observations_dataset
  ON isaweb_observations(dataset_id, period);

CREATE TABLE IF NOT EXISTS isaweb_metadata (
  id                  INTEGER PRIMARY KEY,
  meta_key            TEXT NOT NULL UNIQUE,
  hierid              INTEGER NOT NULL,
  lang                TEXT NOT NULL,
  pos                 TEXT NOT NULL,
  meta_url            TEXT NOT NULL,
  title               TEXT,
  region              TEXT,
  unit                TEXT,
  comment             TEXT,
  classification      TEXT,
  breaks              TEXT,
  frequency           TEXT,
  data_available_json TEXT,
  last_update         TEXT,
  source              TEXT,
  lag                 TEXT,
  prepared_at         TEXT,
  sender_id           TEXT,
  sender_name         TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_isaweb_metadata_lookup
  ON isaweb_metadata(hierid, lang, pos);

CREATE TABLE IF NOT EXISTS isaweb_content_nodes (
  id            INTEGER PRIMARY KEY,
  hierid        INTEGER,
  lang          TEXT NOT NULL,
  node_id       INTEGER NOT NULL,
  parent_id     INTEGER,
  label         TEXT NOT NULL,
  section_id    INTEGER,
  section_label TEXT,
  family_id     INTEGER,
  family_label  TEXT,
  path_json     TEXT NOT NULL,
  content_url   TEXT NOT NULL,
  prepared_at   TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE(lang, node_id)
);

CREATE INDEX IF NOT EXISTS idx_isaweb_content_lookup
  ON isaweb_content_nodes(lang, section_id, family_id, node_id);

CREATE TABLE IF NOT EXISTS isaweb_page_contexts (
  id                    INTEGER PRIMARY KEY,
  source_url            TEXT NOT NULL,
  target_url            TEXT NOT NULL,
  normalized_target_url TEXT NOT NULL,
  hierid                INTEGER NOT NULL,
  lang                  TEXT NOT NULL,
  relation_kind         TEXT,
  link_text             TEXT,
  section_heading       TEXT,
  section_id            INTEGER,
  section_label         TEXT,
  family_id             INTEGER,
  family_label          TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL,
  UNIQUE(source_url, normalized_target_url, hierid, lang)
);

CREATE INDEX IF NOT EXISTS idx_isaweb_page_contexts_lookup
  ON isaweb_page_contexts(hierid, lang, source_url);

CREATE TABLE IF NOT EXISTS release_events (
  id                INTEGER PRIMARY KEY,
  metadata_id       INTEGER NOT NULL REFERENCES isaweb_metadata(id) ON DELETE CASCADE,
  hierid            INTEGER NOT NULL,
  lang              TEXT NOT NULL,
  pos               TEXT NOT NULL,
  release_date_text TEXT NOT NULL,
  reference_text    TEXT,
  revision_text     TEXT,
  source_url        TEXT,
  created_at        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_release_events_unique
  ON release_events(metadata_id, release_date_text, reference_text);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with schema. Returns connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def start_crawl_run(conn: sqlite3.Connection, seed_url: str, user_agent: str) -> int:
    """Start a new crawl run. Returns run_id."""
    cursor = conn.execute(
        "INSERT INTO crawl_runs (seed_url, started_at, user_agent) VALUES (?, ?, ?)",
        (seed_url, datetime.utcnow().isoformat() + "Z", user_agent)
    )
    conn.commit()
    return cursor.lastrowid


def finish_crawl_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Mark crawl run as finished."""
    conn.execute(
        "UPDATE crawl_runs SET finished_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat() + "Z", run_id)
    )
    conn.commit()


def store_page(
    conn: sqlite3.Connection,
    run_id: int,
    url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    body: bytes,
    fetch_ms: int = None,
    etag: str = None,
    last_modified: str = None,
    headers: dict = None,
    fetch_error: str = None,
) -> int:
    """Store a page and its compressed body. Upserts on URL conflict. Returns page_id."""
    body_hash = hashlib.sha256(body).hexdigest() if body else None
    headers_json = json.dumps(headers) if headers else None
    now = datetime.utcnow().isoformat() + "Z"

    # Check if page already exists with same body_hash
    existing = conn.execute(
        "SELECT id, body_hash FROM pages WHERE url = ?", (url,)
    ).fetchone()

    if existing:
        page_id, old_hash = existing
        if not should_reextract_content(previous_hash=old_hash, current_hash=body_hash):
            # Content unchanged - just update fetched_at
            conn.execute(
                "UPDATE pages SET fetched_at = ?, crawl_run_id = ? WHERE id = ?",
                (now, run_id, page_id)
            )
            conn.commit()
            return page_id
        else:
            # Content changed - update everything
            conn.execute(
                """UPDATE pages SET crawl_run_id=?, final_url=?, status_code=?,
                   content_type=?, fetched_at=?, fetch_ms=?, bytes_downloaded=?,
                   etag=?, last_modified=?, body_hash=?, headers_json=?, fetch_error=?
                   WHERE id = ?""",
                (run_id, final_url, status_code, content_type, now, fetch_ms,
                 len(body) if body else 0, etag, last_modified, body_hash,
                 headers_json, fetch_error, page_id)
            )
            if body:
                compressed = gzip.compress(body)
                conn.execute(
                    "INSERT OR REPLACE INTO page_bodies (page_id, storage, compression, body_blob) VALUES (?, ?, ?, ?)",
                    (page_id, "db", "gzip", compressed)
                )
            # Invalidate extracted content so it gets re-extracted
            conn.execute("DELETE FROM page_content WHERE page_id = ?", (page_id,))
            conn.commit()
            return page_id

    # New page
    cursor = conn.execute(
        """INSERT INTO pages
           (crawl_run_id, url, final_url, status_code, content_type,
            fetched_at, fetch_ms, bytes_downloaded, etag, last_modified,
            body_hash, headers_json, fetch_error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, url, final_url, status_code, content_type,
         now, fetch_ms, len(body) if body else 0,
         etag, last_modified, body_hash, headers_json, fetch_error)
    )
    page_id = cursor.lastrowid

    if body:
        compressed = gzip.compress(body)
        conn.execute(
            "INSERT INTO page_bodies (page_id, storage, compression, body_blob) VALUES (?, ?, ?, ?)",
            (page_id, "db", "gzip", compressed)
        )

    conn.commit()
    return page_id


def store_resource_link(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    target_url: str,
    normalized_target_url: str,
    link_text: str | None = None,
    section_heading: str | None = None,
    resource_kind: str | None = None,
    embed_type: str | None = None,
    discovered_at: str | None = None,
) -> int:
    """Persist a discovered parent-child resource relation."""

    discovered_at = discovered_at or datetime.utcnow().isoformat() + "Z"
    cursor = conn.execute(
        """
        INSERT INTO resource_links
          (source_url, target_url, normalized_target_url, link_text, section_heading, resource_kind, embed_type, discovered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_url,
            target_url,
            normalized_target_url,
            link_text,
            section_heading,
            resource_kind,
            embed_type,
            discovered_at,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def list_resource_links_for_target(conn: sqlite3.Connection, normalized_target_url: str) -> list[sqlite3.Row]:
    """Fetch all stored parent links for a canonical target URL."""

    rows = conn.execute(
        """
        SELECT source_url, target_url, normalized_target_url, link_text, section_heading, resource_kind, embed_type, discovered_at
        FROM resource_links
        WHERE normalized_target_url = ?
        ORDER BY discovered_at ASC, id ASC
        """,
        (normalized_target_url,),
    ).fetchall()
    return list(rows)


def store_resource_version(
    conn: sqlite3.Connection,
    *,
    url: str,
    body_hash: str | None,
    status_code: int | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    fetched_at: str | None = None,
) -> int:
    """Persist an immutable fetched resource version entry."""

    fetched_at = fetched_at or datetime.utcnow().isoformat() + "Z"
    cursor = conn.execute(
        """
        INSERT INTO resource_versions
          (url, body_hash, fetched_at, etag, last_modified, status_code)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (url, body_hash, fetched_at, etag, last_modified, status_code),
    )
    conn.commit()
    return cursor.lastrowid
