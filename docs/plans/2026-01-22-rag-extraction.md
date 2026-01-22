# RAG Text Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store raw HTML and extract text from OeNB pages for later RAG/chatbot use.

**Architecture:** New SQLite pipeline stores HTTP metadata + compressed HTML. Separate extraction script processes HTML to clean text. Export script converts to Parquet for Cloudera.

**Tech Stack:** SQLite, gzip, BeautifulSoup, pyarrow/pandas

---

## Task 1: Create SQLite Database Module

**Files:**
- Create: `scraper/oenb_scraper/database.py`
- Test: `tests/test_database.py`

**Step 1: Write the failing test**

```python
# tests/test_database.py
import sqlite3
import tempfile
from pathlib import Path

def test_create_tables():
    """Test that init_db creates all required tables."""
    from oenb_scraper.database import init_db

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "crawl_runs" in tables
        assert "pages" in tables
        assert "page_bodies" in tables
        assert "page_content" in tables
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_create_tables -v`
Expected: FAIL with "No module named 'oenb_scraper.database'"

**Step 3: Write minimal implementation**

```python
# scraper/oenb_scraper/database.py
"""SQLite database for storing crawled pages and extracted content."""
import sqlite3
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py::test_create_tables -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py tests/test_database.py
git commit -m "feat: add SQLite database module with schema"
```

---

## Task 2: Add Crawl Run Helper Functions

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Test: `tests/test_database.py`

**Step 1: Write the failing test**

```python
# tests/test_database.py (add to file)
def test_start_and_finish_crawl_run():
    """Test crawl run lifecycle."""
    from oenb_scraper.database import init_db, start_crawl_run, finish_crawl_run

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")
        assert run_id == 1

        # Check it's stored
        row = conn.execute("SELECT seed_url, user_agent FROM crawl_runs WHERE id=?", (run_id,)).fetchone()
        assert row[0] == "https://www.oenb.at/"
        assert row[1] == "TestBot/1.0"

        finish_crawl_run(conn, run_id)

        row = conn.execute("SELECT finished_at FROM crawl_runs WHERE id=?", (run_id,)).fetchone()
        assert row[0] is not None

        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_start_and_finish_crawl_run -v`
Expected: FAIL with "cannot import name 'start_crawl_run'"

**Step 3: Write minimal implementation**

```python
# scraper/oenb_scraper/database.py (add to file)
from datetime import datetime


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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py::test_start_and_finish_crawl_run -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py tests/test_database.py
git commit -m "feat: add crawl run start/finish functions"
```

---

## Task 3: Add Page Storage Function

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Test: `tests/test_database.py`

**Step 1: Write the failing test**

```python
# tests/test_database.py (add to file)
import gzip

def test_store_page_with_body():
    """Test storing a page with compressed body."""
    from oenb_scraper.database import init_db, start_crawl_run, store_page

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        html = b"<html><body>Test page</body></html>"

        page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/test.html",
            final_url="https://www.oenb.at/test.html",
            status_code=200,
            content_type="text/html",
            body=html,
        )

        assert page_id == 1

        # Verify page record
        row = conn.execute("SELECT url, status_code FROM pages WHERE id=?", (page_id,)).fetchone()
        assert row[0] == "https://www.oenb.at/test.html"
        assert row[1] == 200

        # Verify body is stored compressed
        row = conn.execute("SELECT compression, body_blob FROM page_bodies WHERE page_id=?", (page_id,)).fetchone()
        assert row[0] == "gzip"
        assert gzip.decompress(row[1]) == html

        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_store_page_with_body -v`
Expected: FAIL with "cannot import name 'store_page'"

**Step 3: Write minimal implementation**

```python
# scraper/oenb_scraper/database.py (add to file)
import gzip
import hashlib


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
    """Store a page and its compressed body. Returns page_id."""
    body_hash = hashlib.sha256(body).hexdigest() if body else None
    headers_json = json.dumps(headers) if headers else None

    cursor = conn.execute(
        """INSERT INTO pages
           (crawl_run_id, url, final_url, status_code, content_type,
            fetched_at, fetch_ms, bytes_downloaded, etag, last_modified,
            body_hash, headers_json, fetch_error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, url, final_url, status_code, content_type,
         datetime.utcnow().isoformat() + "Z", fetch_ms, len(body) if body else 0,
         etag, last_modified, body_hash, headers_json, fetch_error)
    )
    page_id = cursor.lastrowid

    # Store compressed body
    if body:
        compressed = gzip.compress(body)
        conn.execute(
            "INSERT INTO page_bodies (page_id, storage, compression, body_blob) VALUES (?, ?, ?, ?)",
            (page_id, "db", "gzip", compressed)
        )

    conn.commit()
    return page_id
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py::test_store_page_with_body -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py tests/test_database.py
git commit -m "feat: add store_page function with gzip compression"
```

---

## Task 4: Create SQLite Pipeline for Scrapy

**Files:**
- Modify: `scraper/oenb_scraper/pipelines.py`
- Modify: `scraper/oenb_scraper/settings.py`
- Test: `tests/test_sqlite_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/test_sqlite_pipeline.py
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

def test_sqlite_pipeline_stores_page():
    """Test that SQLitePipeline stores response body."""
    from oenb_scraper.pipelines import SQLitePipeline
    from oenb_scraper.items import DownloadItem

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"

        # Create pipeline
        pipeline = SQLitePipeline(db_path)

        # Mock spider
        spider = MagicMock()
        spider.name = "oenb"
        spider.settings = {"USER_AGENT": "TestBot/1.0"}

        pipeline.open_spider(spider)

        # Create item with response
        item = DownloadItem()
        item["url"] = "https://www.oenb.at/test.html"
        item["type"] = "webpage_with_data"

        # Mock response
        response = MagicMock()
        response.url = "https://www.oenb.at/test.html"
        response.status = 200
        response.headers = {b"Content-Type": [b"text/html"]}
        response.body = b"<html><body>Test</body></html>"

        # Process
        pipeline.process_item(item, spider, response=response)
        pipeline.close_spider(spider)

        # Verify
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT url, status_code FROM pages").fetchone()
        assert row[0] == "https://www.oenb.at/test.html"
        assert row[1] == 200
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sqlite_pipeline.py -v`
Expected: FAIL with "cannot import name 'SQLitePipeline'"

**Step 3: Write minimal implementation**

```python
# scraper/oenb_scraper/pipelines.py (add to file)
from oenb_scraper.database import init_db, start_crawl_run, finish_crawl_run, store_page


class SQLitePipeline:
    """Store pages and bodies in SQLite database."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.run_id = None

    @classmethod
    def from_crawler(cls, crawler):
        db_path = crawler.settings.get("SQLITE_DB_PATH", "data/pages.db")
        return cls(db_path)

    def open_spider(self, spider):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = init_db(self.db_path)
        user_agent = spider.settings.get("USER_AGENT", "unknown")
        self.run_id = start_crawl_run(self.conn, spider.start_urls[0] if spider.start_urls else "", user_agent)
        spider.logger.info(f"SQLitePipeline: DB at {self.db_path}, run_id={self.run_id}")

    def close_spider(self, spider):
        if self.conn and self.run_id:
            finish_crawl_run(self.conn, self.run_id)
            self.conn.close()

    def process_item(self, item, spider, response=None):
        """Store page if we have a response."""
        if response and hasattr(response, 'body'):
            store_page(
                self.conn,
                run_id=self.run_id,
                url=item.get("url", response.url),
                final_url=response.url,
                status_code=response.status,
                content_type=response.headers.get(b"Content-Type", [b""])[0].decode("utf-8", errors="ignore"),
                body=response.body,
            )
        return item
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_sqlite_pipeline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/pipelines.py tests/test_sqlite_pipeline.py
git commit -m "feat: add SQLitePipeline for storing pages"
```

---

## Task 5: Create Text Extraction Script

**Files:**
- Create: `analysis/extract_text.py`
- Test: `tests/test_extract_text.py`

**Step 1: Write the failing test**

```python
# tests/test_extract_text.py
def test_extract_text_from_html():
    """Test extracting clean text from HTML."""
    from analysis.extract_text import extract_text_from_html

    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation here</nav>
        <main>
            <h1>Main Content</h1>
            <p>This is the important text.</p>
        </main>
        <footer>Footer stuff</footer>
        <script>var x = 1;</script>
    </body>
    </html>
    """

    result = extract_text_from_html(html)

    assert result["title"] == "Test Page"
    assert "Main Content" in result["text"]
    assert "important text" in result["text"]
    assert "Navigation here" not in result["text"]  # nav excluded
    assert "var x = 1" not in result["text"]  # script excluded
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract_text.py::test_extract_text_from_html -v`
Expected: FAIL with "No module named 'analysis.extract_text'"

**Step 3: Write minimal implementation**

```python
# analysis/extract_text.py
"""Extract clean text from HTML pages."""
from bs4 import BeautifulSoup
import re


def extract_text_from_html(html: str) -> dict:
    """Extract title and clean text from HTML.

    Returns:
        {"title": str, "text": str}
    """
    soup = BeautifulSoup(html, "html.parser")

    # Get title
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Remove unwanted elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Get text
    text = soup.get_text(separator=" ", strip=True)

    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return {"title": title, "text": text}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract_text.py::test_extract_text_from_html -v`
Expected: PASS

**Step 5: Commit**

```bash
git add analysis/extract_text.py tests/test_extract_text.py
git commit -m "feat: add text extraction from HTML"
```

---

## Task 6: Add Batch Extraction CLI

**Files:**
- Modify: `analysis/extract_text.py`
- Test: `tests/test_extract_text.py`

**Step 1: Write the failing test**

```python
# tests/test_extract_text.py (add to file)
import sqlite3
import tempfile
import gzip
from pathlib import Path

def test_batch_extraction():
    """Test extracting text from all pages in database."""
    from analysis.extract_text import extract_text_from_html, run_extraction
    from oenb_scraper.database import init_db, start_crawl_run, store_page

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://test.at/", "Test/1.0")

        # Store test page
        html = b"<html><head><title>Test</title></head><body><p>Content here</p></body></html>"
        store_page(conn, run_id, "https://test.at/page1.html", "https://test.at/page1.html", 200, "text/html", html)
        conn.close()

        # Run extraction
        run_extraction(db_path, extractor_version="test-v1")

        # Verify
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT title, text_content, extractor_version FROM page_content").fetchone()
        assert row[0] == "Test"
        assert "Content here" in row[1]
        assert row[2] == "test-v1"
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract_text.py::test_batch_extraction -v`
Expected: FAIL with "cannot import name 'run_extraction'"

**Step 3: Write minimal implementation**

```python
# analysis/extract_text.py (add to file)
import sqlite3
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def get_section_from_url(url: str) -> str:
    """Extract section from URL path."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0].lower() == "en":
        parts = parts[1:]
    return parts[0] if parts else "Startseite"


def get_language_from_url(url: str) -> str:
    """Extract language from URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    return "en" if parts and parts[0].lower() == "en" else "de"


def run_extraction(db_path: Path, extractor_version: str = "v1") -> int:
    """Extract text from all pages without content. Returns count."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get pages without extracted content
    cursor = conn.execute("""
        SELECT p.id, p.url, pb.body_blob, pb.compression
        FROM pages p
        JOIN page_bodies pb ON pb.page_id = p.id
        LEFT JOIN page_content pc ON pc.page_id = p.id
        WHERE pc.page_id IS NULL AND p.content_type LIKE '%html%'
    """)

    count = 0
    for row in cursor:
        body = row["body_blob"]
        if row["compression"] == "gzip":
            body = gzip.decompress(body)

        html = body.decode("utf-8", errors="ignore")
        result = extract_text_from_html(html)

        conn.execute(
            """INSERT INTO page_content
               (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], result["title"], result["text"],
             get_section_from_url(row["url"]), get_language_from_url(row["url"]),
             datetime.utcnow().isoformat() + "Z", extractor_version)
        )
        count += 1

    conn.commit()
    conn.close()
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract text from crawled pages")
    parser.add_argument("db_path", type=Path, help="Path to SQLite database")
    parser.add_argument("--version", default="v1", help="Extractor version tag")
    args = parser.parse_args()

    count = run_extraction(args.db_path, args.version)
    print(f"Extracted text from {count} pages")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract_text.py::test_batch_extraction -v`
Expected: PASS

**Step 5: Commit**

```bash
git add analysis/extract_text.py tests/test_extract_text.py
git commit -m "feat: add batch text extraction CLI"
```

---

## Task 7: Create Parquet Export Script

**Files:**
- Create: `analysis/export_parquet.py`
- Test: `tests/test_export_parquet.py`

**Step 1: Write the failing test**

```python
# tests/test_export_parquet.py
import sqlite3
import tempfile
from pathlib import Path

def test_export_to_parquet():
    """Test exporting page_content to Parquet."""
    from analysis.export_parquet import export_to_parquet
    from oenb_scraper.database import init_db

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "export.parquet"

        conn = init_db(db_path)

        # Insert test data directly
        conn.execute("INSERT INTO pages (id, url, status_code) VALUES (1, 'https://test.at/', 200)")
        conn.execute("""INSERT INTO page_content
                        (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
                        VALUES (1, 'Test Title', 'Test content', 'Statistik', 'de', '2026-01-22', 'v1')""")
        conn.commit()
        conn.close()

        # Export
        export_to_parquet(db_path, parquet_path)

        # Verify
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        assert len(df) == 1
        assert df.iloc[0]["title"] == "Test Title"
        assert df.iloc[0]["url"] == "https://test.at/"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_parquet.py -v`
Expected: FAIL with "No module named 'analysis.export_parquet'"

**Step 3: Write minimal implementation**

```python
# analysis/export_parquet.py
"""Export page content to Parquet format for Cloudera/Hive."""
import sqlite3
from pathlib import Path
import pandas as pd


def export_to_parquet(db_path: Path, output_path: Path) -> int:
    """Export page_content joined with pages to Parquet. Returns row count."""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            pc.title,
            pc.text_content,
            pc.page_section,
            pc.language,
            pc.extracted_at,
            pc.extractor_version
        FROM page_content pc
        JOIN pages p ON p.id = pc.page_id
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    df.to_parquet(output_path, index=False)
    return len(df)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export to Parquet")
    parser.add_argument("db_path", type=Path, help="Path to SQLite database")
    parser.add_argument("output_path", type=Path, help="Output Parquet file")
    args = parser.parse_args()

    count = export_to_parquet(args.db_path, args.output_path)
    print(f"Exported {count} rows to {args.output_path}")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_parquet.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add analysis/export_parquet.py tests/test_export_parquet.py
git commit -m "feat: add Parquet export for Cloudera"
```

---

## Task 8: Update Requirements

**Files:**
- Modify: `requirements.txt`

**Step 1: Add dependencies**

```bash
echo "beautifulsoup4>=4.12.0" >> requirements.txt
echo "pandas>=2.0.0" >> requirements.txt
echo "pyarrow>=14.0.0" >> requirements.txt
```

**Step 2: Install and verify**

Run: `pip install -r requirements.txt`
Run: `python -c "import bs4; import pandas; import pyarrow; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add beautifulsoup4, pandas, pyarrow dependencies"
```

---

## Task 9: Integration Test

**Files:**
- Test: `tests/test_integration.py`

**Step 1: Write integration test**

```python
# tests/test_integration.py
"""End-to-end integration test for RAG extraction pipeline."""
import sqlite3
import tempfile
from pathlib import Path

def test_full_pipeline():
    """Test: init DB → store page → extract text → export parquet."""
    from oenb_scraper.database import init_db, start_crawl_run, store_page, finish_crawl_run
    from analysis.extract_text import run_extraction
    from analysis.export_parquet import export_to_parquet

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "export.parquet"

        # 1. Init and store
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "Test/1.0")

        html = b"""<html>
        <head><title>OeNB Statistik</title></head>
        <body>
            <nav>Menu</nav>
            <main><h1>Inflation</h1><p>Die Inflation betrug 3.5%.</p></main>
        </body>
        </html>"""

        store_page(conn, run_id,
                   "https://www.oenb.at/Statistik/inflation.html",
                   "https://www.oenb.at/Statistik/inflation.html",
                   200, "text/html", html)

        finish_crawl_run(conn, run_id)
        conn.close()

        # 2. Extract
        count = run_extraction(db_path, "v1")
        assert count == 1

        # 3. Export
        count = export_to_parquet(db_path, parquet_path)
        assert count == 1

        # 4. Verify
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        assert "Inflation" in df.iloc[0]["text_content"]
        assert df.iloc[0]["page_section"] == "Statistik"
```

**Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration test"
```

---

## Summary

After completing all tasks:

1. **Database module** (`database.py`) - Schema + CRUD functions
2. **SQLite Pipeline** - Stores pages during crawl
3. **Text extractor** (`extract_text.py`) - HTML → clean text
4. **Parquet export** (`export_parquet.py`) - SQLite → Parquet

**Usage:**
```bash
# Crawl (stores in SQLite)
scrapy crawl oenb

# Extract text
python -m analysis.extract_text data/pages.db

# Export for Cloudera
python -m analysis.export_parquet data/pages.db data/pages.parquet
```
