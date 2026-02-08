# Crawler v2: Inkrementelles Crawlen + Isawebstat-Datenextraktion

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Crawler so umbauen, dass (1) nur geänderte Seiten neu gecrawlt werden, (2) Session-ID-Duplikate in SQLite eliminiert werden, und (3) Zeitreihendaten aus isawebstat-Chart-Seiten extrahiert werden.

**Architecture:** Drei unabhängige Verbesserungen am bestehenden Scrapy-Crawler. Die SQLitePipeline bekommt URL-Normalisierung und Conditional-GET-Logik. Ein neuer Extraktor parsed JSON-Daten aus `<script>`-Tags der isawebstat-Chart-Seiten. Alle Änderungen sind abwärtskompatibel - die bestehende DB bleibt nutzbar.

**Tech Stack:** Scrapy, SQLite, BeautifulSoup, Python re/json (keine neuen Dependencies)

---

## Hintergrund

### Problem 1: Duplikate in SQLite
Die `DeduplicationPipeline` normalisiert URLs (entfernt jsessionid), aber nur für `DownloadItems`. Die `SQLitePipeline` speichert den Raw-URL von `response.url`. Ergebnis: 19.004 isawebstat-Seiten, davon tausende Duplikate (gleiche Seite, verschiedene Session-IDs).

### Problem 2: Kein inkrementelles Crawlen
Die DB hat Felder für `body_hash`, `etag`, `last_modified`, aber der Spider nutzt sie nicht. Jeder Crawl-Lauf holt alle Seiten neu (26.834 Seiten).

### Problem 3: Isawebstat-Daten unsichtbar
Die Chart-Seiten (z.B. `createChart?chart=10.4.1` = Leitzinssätze) enthalten die Zeitreihendaten als JSON direkt im `<script>`-Tag:
```javascript
$scope.data = [
  {key: "Euroraum", values: [{"label": "2025", "value": 2.15}, ...]}
];
```
Der `extract_text.py` entfernt `<script>`-Tags und verliert diese Daten.

---

## Task 1: URL-Normalisierung in SQLitePipeline

**Files:**
- Modify: `scraper/oenb_scraper/pipelines.py:279-293` (SQLitePipeline.response_received)
- Test: `tests/test_sqlite_pipeline.py`

**Step 1: Write the failing test**

In `tests/test_sqlite_pipeline.py` am Ende hinzufügen:

```python
def test_sqlite_pipeline_normalizes_session_ids():
    """Test that SQLitePipeline deduplicates URLs with different session IDs."""
    from oenb_scraper.pipelines import SQLitePipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        pipeline = SQLitePipeline(db_path)

        spider = MagicMock()
        spider.name = "oenb"
        spider.start_urls = ["https://www.oenb.at/"]
        spider.settings = MagicMock()
        spider.settings.get = MagicMock(return_value="TestBot/1.0")
        pipeline.open_spider(spider)

        # Simulate two responses with different session IDs but same logical URL
        for session_id in ["ABC123", "DEF456"]:
            response = MagicMock()
            response.url = f"https://www.oenb.at/isawebstat/createChart;jsessionid={session_id}?lang=DE&chart=10.4.1"
            response.status = 200
            response.headers = {b"Content-Type": b"text/html; charset=utf-8"}
            response.body = b"<html><body>Chart data</body></html>"

            request = MagicMock()
            request.url = response.url

            pipeline.response_received(response, request, spider)

        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        assert count == 1, f"Expected 1 page but got {count} (session ID dedup failed)"

        url = conn.execute("SELECT url FROM pages").fetchone()[0]
        assert "jsessionid" not in url, f"Session ID not removed from stored URL: {url}"
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version && python -m pytest tests/test_sqlite_pipeline.py::test_sqlite_pipeline_normalizes_session_ids -v`
Expected: FAIL (currently stores both URLs, count == 2)

**Step 3: Write minimal implementation**

In `scraper/oenb_scraper/pipelines.py`, add a `_normalize_url` method to `SQLitePipeline` and use it in `response_received`. Reuse the normalization logic from `DeduplicationPipeline`:

```python
class SQLitePipeline:
    """Store pages and bodies in SQLite database using response_received signal."""

    # Session-related query parameters to strip
    _SESSION_PARAMS = {'jsessionid', 'JSESSIONID', 'PHPSESSID', 'sid', 'session_id'}

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.run_id = None
        self.stored_urls = set()

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL: remove session IDs, fragments, sort query params."""
        from urllib.parse import urldefrag, urlparse, parse_qs, urlencode

        url = urldefrag(url)[0]
        parsed = urlparse(url)

        # Remove jsessionid from path
        path = parsed.path
        for token in (';jsessionid=', ';JSESSIONID='):
            if token in path:
                path = path.split(token)[0]

        # Filter and sort query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in query_params.items()
                    if k not in SQLitePipeline._SESSION_PARAMS}
        sorted_query = urlencode(sorted(filtered.items()), doseq=True)

        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if sorted_query:
            normalized += f"?{sorted_query}"
        return normalized

    # ... (rest of existing methods unchanged)

    def response_received(self, response, request, spider):
        """Store every HTML response in SQLite."""
        if not self.conn or not self.run_id:
            return

        content_type = response.headers.get(b"Content-Type", b"").decode("utf-8", errors="ignore")
        if "text/html" not in content_type:
            return

        # Normalize URL before dedup check and storage
        normalized_url = self._normalize_url(response.url)
        if normalized_url in self.stored_urls:
            return
        self.stored_urls.add(normalized_url)

        try:
            store_page(
                self.conn,
                run_id=self.run_id,
                url=normalized_url,           # Store normalized URL
                final_url=response.url,       # Keep original as final_url
                status_code=response.status,
                content_type=content_type,
                body=response.body,
            )
        except Exception as e:
            spider.logger.error(f"SQLitePipeline: Failed to store {normalized_url}: {e}")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sqlite_pipeline.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/pipelines.py tests/test_sqlite_pipeline.py
git commit -m "fix: normalize URLs in SQLitePipeline to eliminate session-ID duplicates"
```

---

## Task 2: Inkrementelles Crawlen (Conditional GET)

**Files:**
- Modify: `scraper/oenb_scraper/pipelines.py` (SQLitePipeline)
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py` (start_requests)
- Test: `tests/test_sqlite_pipeline.py`

**Step 1: Write the failing test**

```python
def test_sqlite_pipeline_skips_unchanged_pages():
    """Test that SQLitePipeline skips pages with unchanged body_hash."""
    from oenb_scraper.pipelines import SQLitePipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        pipeline = SQLitePipeline(db_path)

        spider = MagicMock()
        spider.name = "oenb"
        spider.start_urls = ["https://www.oenb.at/"]
        spider.settings = MagicMock()
        spider.settings.get = MagicMock(return_value="TestBot/1.0")
        pipeline.open_spider(spider)

        url = "https://www.oenb.at/test.html"
        body = b"<html><body>Same content</body></html>"

        # First request: should store
        response1 = MagicMock()
        response1.url = url
        response1.status = 200
        response1.headers = {b"Content-Type": b"text/html"}
        response1.body = body
        request1 = MagicMock()
        request1.url = url
        pipeline.response_received(response1, request1, spider)

        # Simulate a second crawl run by clearing stored_urls
        # (as if spider restarted) but keeping the DB
        pipeline.stored_urls.clear()

        # Second request with same body: should update fetched_at but not create duplicate
        response2 = MagicMock()
        response2.url = url
        response2.status = 200
        response2.headers = {b"Content-Type": b"text/html"}
        response2.body = body
        request2 = MagicMock()
        request2.url = url
        pipeline.response_received(response2, request2, spider)

        pipeline.close_spider(spider)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        assert count == 1, f"Expected 1 page but got {count} (should upsert, not duplicate)"
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sqlite_pipeline.py::test_sqlite_pipeline_skips_unchanged_pages -v`
Expected: FAIL (IntegrityError on UNIQUE constraint or count == 2)

**Step 3: Write minimal implementation**

Modify `store_page` in `database.py` to use `INSERT OR REPLACE` and modify `response_received` to handle existing pages:

In `scraper/oenb_scraper/database.py`, change `store_page` to use upsert:

```python
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
        if old_hash == body_hash:
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
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sqlite_pipeline.py tests/test_database.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py tests/test_sqlite_pipeline.py
git commit -m "feat: add incremental crawling - skip unchanged pages, upsert on URL"
```

---

## Task 3: Isawebstat Chart-Daten extrahieren

**Files:**
- Create: `analysis/extract_chart_data.py`
- Test: `tests/test_extract_chart_data.py`

**Step 1: Write the failing test**

Create `tests/test_extract_chart_data.py`:

```python
"""Tests for isawebstat chart data extraction."""


def test_extract_chart_json_from_script():
    """Test extracting chart data JSON from isawebstat <script> tag."""
    from analysis.extract_chart_data import extract_chart_data

    html = '''
    <html><head><title>DATA Chart - Leitzinssätze</title></head>
    <body>
    <script>
    $scope.data = [
        {
            key: "Euroraum",
            color: "#607EA9",
            values: [{"x": "0", "label": "2023", "value": 4.5}, {"x": "1", "label": "2024", "value": 3.15}, {"x": "2", "label": "2025", "value": 2.15}]
        },
        {
            key: "USA",
            color: "#CD3482",
            values: [{"x": "0", "label": "2023", "value": 5.5}, {"x": "1", "label": "2024", "value": 4.5}, {"x": "2", "label": "2025", "value": 3.75}]
        }
    ];
    </script>
    </body></html>
    '''

    result = extract_chart_data(html)

    assert result is not None
    assert result["title"] == "Leitzinssätze"
    assert len(result["series"]) == 2
    assert result["series"][0]["key"] == "Euroraum"
    assert result["series"][0]["values"][-1] == {"label": "2025", "value": 2.15}
    assert result["series"][1]["key"] == "USA"


def test_extract_chart_json_returns_none_for_non_chart():
    """Test that non-chart HTML returns None."""
    from analysis.extract_chart_data import extract_chart_data

    html = '<html><body><p>Normal page</p></body></html>'
    result = extract_chart_data(html)
    assert result is None


def test_chart_data_to_text():
    """Test converting chart data to searchable text."""
    from analysis.extract_chart_data import chart_data_to_text

    chart_data = {
        "title": "Leitzinssätze",
        "source": "Macrobond",
        "series": [
            {
                "key": "Euroraum",
                "values": [
                    {"label": "2024", "value": 3.15},
                    {"label": "2025", "value": 2.15},
                ]
            },
            {
                "key": "USA",
                "values": [
                    {"label": "2024", "value": 4.5},
                    {"label": "2025", "value": 3.75},
                ]
            }
        ]
    }

    text = chart_data_to_text(chart_data)

    assert "Leitzinssätze" in text
    assert "Euroraum" in text
    assert "2025: 2.15" in text
    assert "USA" in text
    assert "2025: 3.75" in text
    assert "Macrobond" in text
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extract_chart_data.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

Create `analysis/extract_chart_data.py`:

```python
"""Extract structured data from isawebstat chart pages.

The isawebstat chart pages embed time-series data as JavaScript objects
in <script> tags. This module extracts and converts them to searchable text.
"""
import json
import re
from pathlib import Path


def extract_chart_data(html: str) -> dict | None:
    """Extract chart data from isawebstat HTML.

    Looks for $scope.data = [...] in <script> tags and parses the
    embedded JSON time-series data.

    Returns:
        {"title": str, "source": str, "series": [{"key": str, "values": [...]}]}
        or None if not a chart page.
    """
    # Find $scope.data = [...];
    match = re.search(r'\$scope\.data\s*=\s*\[(.+?)\];\s*$', html, re.DOTALL | re.MULTILINE)
    if not match:
        return None

    raw = match.group(1)

    # Parse series: each {key: "...", color: "...", values: [...]}
    series = []
    for series_match in re.finditer(
        r'key:\s*"([^"]+)".*?values:\s*\[([^\]]+)\]',
        raw, re.DOTALL
    ):
        key = series_match.group(1)
        values_raw = series_match.group(2)

        values = []
        for val_match in re.finditer(
            r'"label"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*([0-9.\-]+)',
            values_raw
        ):
            values.append({
                "label": val_match.group(1),
                "value": float(val_match.group(2)),
            })

        if values:
            series.append({"key": key, "values": values})

    if not series:
        return None

    # Extract title from <title> tag (remove "DATA Chart - " prefix)
    title_match = re.search(r'<title>(?:DATA Chart - )?(.+?)</title>', html)
    title = title_match.group(1).strip() if title_match else "Unbekannt"

    # Extract source from caption HTML
    source = ""
    source_match = re.search(r"html:\s*'Quelle:\s*.*?title=\"([^\"]+)\"", html)
    if source_match:
        source = source_match.group(1)

    return {"title": title, "source": source, "series": series}


def chart_data_to_text(chart_data: dict) -> str:
    """Convert chart data to searchable plain text.

    Produces text like:
        Leitzinssätze (Quelle: Macrobond)
        Euroraum: 2023: 4.5, 2024: 3.15, 2025: 2.15
        USA: 2023: 5.5, 2024: 4.5, 2025: 3.75
    """
    lines = []

    title = chart_data["title"]
    source = chart_data.get("source", "")
    if source:
        lines.append(f"{title} (Quelle: {source})")
    else:
        lines.append(title)

    for s in chart_data["series"]:
        values_str = ", ".join(f"{v['label']}: {v['value']}" for v in s["values"])
        lines.append(f"{s['key']}: {values_str}")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract_chart_data.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add analysis/extract_chart_data.py tests/test_extract_chart_data.py
git commit -m "feat: add isawebstat chart data extractor - parses JS time-series from HTML"
```

---

## Task 4: Chart-Daten in Text-Extraktion integrieren

**Files:**
- Modify: `analysis/extract_text.py:12-30` (extract_text_from_html)
- Test: `tests/test_extract_text.py`

**Step 1: Write the failing test**

Add to `tests/test_extract_text.py`:

```python
def test_extract_text_includes_chart_data():
    """Test that isawebstat chart data is included in extracted text."""
    from analysis.extract_text import extract_text_from_html

    html = '''
    <html><head><title>DATA Chart - Leitzinssätze</title></head>
    <body>
    <script>
    $scope.data = [
        {
            key: "Euroraum",
            color: "#607EA9",
            values: [{"x": "0", "label": "2024", "value": 3.15}, {"x": "1", "label": "2025", "value": 2.15}]
        }
    ];
    </script>
    <div>Chart wählen Leitzinssätze</div>
    </body></html>
    '''

    result = extract_text_from_html(html)

    assert "Leitzinssätze" in result["text"]
    assert "Euroraum" in result["text"]
    assert "2025: 2.15" in result["text"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extract_text.py::test_extract_text_includes_chart_data -v`
Expected: FAIL ("Euroraum" and "2025: 2.15" not in text because <script> is stripped)

**Step 3: Write minimal implementation**

Modify `analysis/extract_text.py` to check for chart data before stripping scripts:

```python
"""Extract clean text from HTML pages."""
import sqlite3
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import re

from analysis.extract_chart_data import extract_chart_data, chart_data_to_text


def extract_text_from_html(html: str) -> dict:
    """Extract title and clean text from HTML.

    For isawebstat chart pages, also extracts embedded time-series data
    from <script> tags before they are removed.

    Returns:
        {"title": str, "text": str}
    """
    # Extract chart data BEFORE stripping scripts
    chart_data = extract_chart_data(html)
    chart_text = chart_data_to_text(chart_data) if chart_data else ""

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    # Append chart data if present
    if chart_text:
        text = f"{text}\n\n{chart_text}"

    return {"title": title, "text": text}
```

(Keep all other functions in the file unchanged.)

**Step 4: Run ALL tests to verify nothing is broken**

Run: `python -m pytest tests/test_extract_text.py tests/test_extract_chart_data.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add analysis/extract_text.py tests/test_extract_text.py
git commit -m "feat: integrate chart data extraction into text pipeline"
```

---

## Task 5: DB-Bereinigung - Bestehende Duplikate entfernen

**Files:**
- Create: `analysis/cleanup_db.py`
- Test: `tests/test_cleanup_db.py`

**Step 1: Write the failing test**

Create `tests/test_cleanup_db.py`:

```python
"""Tests for database cleanup script."""
import sqlite3
import tempfile
from pathlib import Path

def test_dedup_removes_session_id_duplicates():
    """Test that cleanup deduplicates pages with session IDs in URLs."""
    from oenb_scraper.database import init_db, start_crawl_run, store_page
    from analysis.cleanup_db import dedup_pages

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://test.at/", "Test/1.0")

        body = b"<html><body>Same content</body></html>"
        store_page(conn, run_id, "https://example.com/page;jsessionid=AAA?lang=DE&chart=1", "https://example.com/page", 200, "text/html", body)
        store_page(conn, run_id, "https://example.com/page;jsessionid=BBB?lang=DE&chart=1", "https://example.com/page", 200, "text/html", body)
        store_page(conn, run_id, "https://example.com/other.html", "https://example.com/other.html", 200, "text/html", body)
        conn.close()

        removed = dedup_pages(db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        conn.close()

        assert removed == 1
        assert count == 2  # one deduped + "other.html"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cleanup_db.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

Create `analysis/cleanup_db.py`:

```python
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
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_cleanup_db.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add analysis/cleanup_db.py tests/test_cleanup_db.py
git commit -m "feat: add DB cleanup script to deduplicate session-ID URLs"
```

---

## Task 6: Re-Extraktion mit Chart-Daten

**Files:**
- Modify: `analysis/extract_text.py:49-83` (run_extraction)

Dieses Task braucht keinen neuen Code - nur die bestehende `run_extraction` muss nach der DB-Bereinigung (Task 5) und dem neuen Extraktor (Task 4) nochmal ausgeführt werden.

**Step 1: Bereinigung durchführen**

```bash
cd /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version
source venv/bin/activate
python analysis/cleanup_db.py data/pages.db
```

Expected: "Removed X,XXX duplicate pages"

**Step 2: Alte Extraktionen löschen und neu extrahieren**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
conn.execute('DELETE FROM page_content')
conn.commit()
print(f'Deleted {conn.total_changes} old extractions')
conn.close()
"
python analysis/extract_text.py data/pages.db --version v2-with-charts
```

**Step 3: Verifizieren**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
total = conn.execute('SELECT COUNT(*) FROM page_content').fetchone()[0]
charts = conn.execute(\"SELECT COUNT(*) FROM page_content WHERE text_content LIKE '%Leitzinssätze%Euroraum%2025%'\").fetchone()[0]
print(f'Total pages with content: {total:,}')
print(f'Pages with chart data (Leitzinssätze): {charts}')
conn.close()
"
```

Expected: charts > 0

**Step 4: Commit**

No code changes to commit - this is a data operation.

---

## Zusammenfassung

| Task | Was | Aufwand |
|------|-----|---------|
| 1 | URL-Normalisierung in SQLitePipeline | Klein |
| 2 | Inkrementelles Crawlen (Upsert) | Mittel |
| 3 | Chart-Daten-Extraktor | Mittel |
| 4 | Integration in Text-Pipeline | Klein |
| 5 | DB-Bereinigung (einmalig) | Klein |
| 6 | Re-Extraktion | Ausführung |

Nach Abschluss:
- Nächster Crawl-Lauf: `./run.sh --rag` speichert nur geänderte Seiten
- Isawebstat-Charts liefern durchsuchbare Zeitreihendaten
- Duplikate sind bereinigt (~17.000 Seiten weniger)
