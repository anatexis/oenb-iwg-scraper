"""SQLite database for storing crawled pages and extracted content."""
import sqlite3
from datetime import datetime
from pathlib import Path

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
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with schema. Returns connection."""
    conn = sqlite3.connect(db_path)
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
