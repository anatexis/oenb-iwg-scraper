# OeNB IWG Scraper - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a web scraper that catalogs all downloads on oenb.at and generates an IWG relevance analysis dashboard.

**Architecture:** Scrapy spider crawls oenb.at, saves to JSON. Analysis script calculates IWG scores and generates standalone HTML dashboard with CSV export.

**Tech Stack:** Python 3.10+, Scrapy, pdfplumber, Jinja2

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `scraper/` directory structure
- Create: `data/.gitkeep`
- Create: `output/.gitkeep`

**Step 1: Create requirements.txt**

```txt
scrapy>=2.11.0
pdfplumber>=0.10.0
jinja2>=3.1.0
requests>=2.31.0
```

**Step 2: Create directory structure**

Run:
```bash
mkdir -p scraper data output analysis
touch data/.gitkeep output/.gitkeep
```

**Step 3: Initialize Scrapy project**

Run:
```bash
cd scraper && scrapy startproject oenb_scraper .
```

Expected: Creates `scrapy.cfg`, `oenb_scraper/` with `__init__.py`, `items.py`, `middlewares.py`, `pipelines.py`, `settings.py`, `spiders/`

**Step 4: Install dependencies**

Run:
```bash
pip install -r requirements.txt
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: initialize project structure with Scrapy"
```

---

## Task 2: Define Scrapy Item

**Files:**
- Modify: `scraper/oenb_scraper/items.py`

**Step 1: Write the item definition**

Replace contents of `scraper/oenb_scraper/items.py`:

```python
import scrapy


class DownloadItem(scrapy.Item):
    """Represents a downloadable resource found on oenb.at"""
    url = scrapy.Field()
    type = scrapy.Field()  # 'download', 'shiny_app', 'external_data'
    file_type = scrapy.Field()  # 'pdf', 'xlsx', 'csv', 'xml', 'zip', etc.
    file_size_bytes = scrapy.Field()
    title = scrapy.Field()
    found_on_page = scrapy.Field()
    page_section = scrapy.Field()
    section_heading = scrapy.Field()
    page_date = scrapy.Field()
    scraped_at = scrapy.Field()
    machine_readable = scrapy.Field()  # For PDFs: True/False/None
    has_tables = scrapy.Field()  # For PDFs: True/False/None
```

**Step 2: Commit**

```bash
git add scraper/oenb_scraper/items.py
git commit -m "feat: define DownloadItem schema"
```

---

## Task 3: Configure Scrapy Settings

**Files:**
- Modify: `scraper/oenb_scraper/settings.py`

**Step 1: Update settings for polite crawling**

Add/modify these settings in `scraper/oenb_scraper/settings.py`:

```python
BOT_NAME = "oenb_scraper"

SPIDER_MODULES = ["oenb_scraper.spiders"]
NEWSPIDER_MODULE = "oenb_scraper.spiders"

# Polite crawling
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 1.5  # 1.5 seconds between requests
CONCURRENT_REQUESTS = 1  # One request at a time

# User agent
USER_AGENT = "OeNB-IWG-Audit-Bot/1.0 (Open Data compliance check; contact@example.com)"

# Output encoding
FEED_EXPORT_ENCODING = "utf-8"

# Logging
LOG_LEVEL = "INFO"

# Disable cookies (not needed)
COOKIES_ENABLED = False

# Enable AutoThrottle for additional politeness
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
```

**Step 2: Commit**

```bash
git add scraper/oenb_scraper/settings.py
git commit -m "feat: configure polite crawling settings"
```

---

## Task 4: Create Basic Spider

**Files:**
- Create: `scraper/oenb_scraper/spiders/oenb_spider.py`

**Step 1: Write the spider skeleton**

Create `scraper/oenb_scraper/spiders/oenb_spider.py`:

```python
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import scrapy

from oenb_scraper.items import DownloadItem


class OenbSpider(scrapy.Spider):
    name = "oenb"
    allowed_domains = ["oenb.at", "www.oenb.at"]
    start_urls = [
        "https://www.oenb.at/",
        "https://www.oenb.at/Service/Sitemap.html",
    ]

    # File extensions to capture as downloads
    DOWNLOAD_EXTENSIONS = {
        ".pdf", ".xlsx", ".xls", ".csv", ".xml", ".zip",
        ".doc", ".docx", ".ppt", ".pptx", ".json"
    }

    # Patterns for Shiny apps
    SHINY_PATTERNS = [
        r"shinyapps\.io",
        r"/shiny/",
        r"shiny\.oenb\.at",
    ]

    def parse(self, response):
        """Parse a page for downloads and follow links."""
        page_url = response.url
        page_section = self._extract_section(page_url)
        page_date = self._extract_page_date(response)

        # Find all links on the page
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            full_url = urljoin(page_url, href)
            link_text = link.css("::text").get() or ""
            link_text = link_text.strip()

            # Check if it's a download
            if self._is_download(full_url):
                yield self._create_download_item(
                    url=full_url,
                    title=link_text,
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                )

            # Check if it's a Shiny app
            elif self._is_shiny_app(full_url):
                yield self._create_shiny_item(
                    url=full_url,
                    title=link_text,
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading=self._find_section_heading(link, response),
                    page_date=page_date,
                )

            # Follow internal links
            elif self._is_internal_link(full_url):
                yield response.follow(full_url, callback=self.parse)

        # Also check iframes for embedded Shiny apps
        for iframe in response.css("iframe[src]"):
            src = iframe.attrib.get("src", "")
            if self._is_shiny_app(src):
                yield self._create_shiny_item(
                    url=src,
                    title="Embedded Shiny App",
                    found_on_page=page_url,
                    page_section=page_section,
                    section_heading="",
                    page_date=page_date,
                )

    def _is_download(self, url: str) -> bool:
        """Check if URL points to a downloadable file."""
        parsed = urlparse(url.lower())
        path = parsed.path
        return any(path.endswith(ext) for ext in self.DOWNLOAD_EXTENSIONS)

    def _is_shiny_app(self, url: str) -> bool:
        """Check if URL is a Shiny app."""
        return any(re.search(pattern, url, re.I) for pattern in self.SHINY_PATTERNS)

    def _is_internal_link(self, url: str) -> bool:
        """Check if URL is internal to oenb.at."""
        parsed = urlparse(url)
        return parsed.netloc in self.allowed_domains or parsed.netloc == ""

    def _extract_section(self, url: str) -> str:
        """Extract page section from URL path."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
        return "Startseite"

    def _extract_page_date(self, response) -> str | None:
        """Try to extract page date from meta tags or content."""
        # Try meta date
        date = response.css('meta[name="date"]::attr(content)').get()
        if date:
            return date

        # Try last-modified header
        last_modified = response.headers.get("Last-Modified")
        if last_modified:
            return last_modified.decode("utf-8", errors="ignore")

        return None

    def _find_section_heading(self, link, response) -> str:
        """Find the nearest heading above the link."""
        # Try to find preceding h1, h2, h3
        for heading in ["h1", "h2", "h3"]:
            headings = response.css(f"{heading}::text").getall()
            if headings:
                return headings[-1].strip()
        return ""

    def _get_file_extension(self, url: str) -> str:
        """Extract file extension from URL."""
        parsed = urlparse(url.lower())
        path = parsed.path
        for ext in self.DOWNLOAD_EXTENSIONS:
            if path.endswith(ext):
                return ext.lstrip(".")
        return "unknown"

    def _create_download_item(self, **kwargs) -> DownloadItem:
        """Create a DownloadItem for a downloadable file."""
        item = DownloadItem()
        item["url"] = kwargs["url"]
        item["type"] = "download"
        item["file_type"] = self._get_file_extension(kwargs["url"])
        item["file_size_bytes"] = None  # Will be filled by pipeline
        item["title"] = kwargs["title"]
        item["found_on_page"] = kwargs["found_on_page"]
        item["page_section"] = kwargs["page_section"]
        item["section_heading"] = kwargs["section_heading"]
        item["page_date"] = kwargs["page_date"]
        item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
        item["machine_readable"] = None  # Will be filled by pipeline for PDFs
        item["has_tables"] = None
        return item

    def _create_shiny_item(self, **kwargs) -> DownloadItem:
        """Create a DownloadItem for a Shiny app."""
        item = DownloadItem()
        item["url"] = kwargs["url"]
        item["type"] = "shiny_app"
        item["file_type"] = "shiny"
        item["file_size_bytes"] = None
        item["title"] = kwargs["title"]
        item["found_on_page"] = kwargs["found_on_page"]
        item["page_section"] = kwargs["page_section"]
        item["section_heading"] = kwargs["section_heading"]
        item["page_date"] = kwargs["page_date"]
        item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
        item["machine_readable"] = True  # Shiny apps have data
        item["has_tables"] = None
        return item
```

**Step 2: Test spider runs without errors**

Run:
```bash
cd scraper && scrapy crawl oenb --nolog -s CLOSESPIDER_PAGECOUNT=5
```

Expected: Spider starts, visits a few pages, outputs items (or empty if no downloads on first pages)

**Step 3: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py
git commit -m "feat: implement OeNB spider with download detection"
```

---

## Task 5: Add PDF Analysis Pipeline

**Files:**
- Create: `scraper/oenb_scraper/pdf_analyzer.py`
- Modify: `scraper/oenb_scraper/pipelines.py`
- Modify: `scraper/oenb_scraper/settings.py`

**Step 1: Create PDF analyzer module**

Create `scraper/oenb_scraper/pdf_analyzer.py`:

```python
import io
import requests
import pdfplumber


def analyze_pdf(url: str, timeout: int = 30) -> dict:
    """
    Download and analyze a PDF for machine readability.

    Returns dict with:
        - machine_readable: bool
        - has_tables: bool
        - error: str or None
    """
    result = {
        "machine_readable": False,
        "has_tables": False,
        "error": None,
    }

    try:
        # Download PDF (first 5MB max to avoid huge files)
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Read up to 5MB
        content = b""
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            content += chunk
            if len(content) > 5 * 1024 * 1024:
                break

        # Analyze with pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text_found = False
            tables_found = False

            # Check first 5 pages max
            for page in pdf.pages[:5]:
                text = page.extract_text() or ""
                if len(text.strip()) > 50:  # More than 50 chars = has text
                    text_found = True

                tables = page.extract_tables() or []
                if tables:
                    tables_found = True

                if text_found and tables_found:
                    break

            result["machine_readable"] = text_found
            result["has_tables"] = tables_found

    except requests.RequestException as e:
        result["error"] = f"Download error: {e}"
    except Exception as e:
        result["error"] = f"PDF analysis error: {e}"

    return result
```

**Step 2: Create pipeline for PDF analysis and file size**

Replace contents of `scraper/oenb_scraper/pipelines.py`:

```python
import requests

from oenb_scraper.pdf_analyzer import analyze_pdf


class FileSizePipeline:
    """Fetch file size via HEAD request."""

    def process_item(self, item, spider):
        if item.get("type") == "download" and item.get("file_size_bytes") is None:
            try:
                response = requests.head(item["url"], timeout=10, allow_redirects=True)
                size = response.headers.get("Content-Length")
                if size:
                    item["file_size_bytes"] = int(size)
            except Exception:
                pass  # Size remains None
        return item


class PdfAnalysisPipeline:
    """Analyze PDFs for machine readability."""

    def process_item(self, item, spider):
        if item.get("file_type") == "pdf" and item.get("machine_readable") is None:
            spider.logger.info(f"Analyzing PDF: {item['url']}")
            result = analyze_pdf(item["url"])
            item["machine_readable"] = result["machine_readable"]
            item["has_tables"] = result["has_tables"]
            if result["error"]:
                spider.logger.warning(f"PDF analysis error: {result['error']}")
        return item


class DeduplicationPipeline:
    """Remove duplicate URLs."""

    def __init__(self):
        self.seen_urls = set()

    def process_item(self, item, spider):
        url = item.get("url")
        if url in self.seen_urls:
            raise scrapy.exceptions.DropItem(f"Duplicate URL: {url}")
        self.seen_urls.add(url)
        return item
```

**Step 3: Enable pipelines in settings**

Add to `scraper/oenb_scraper/settings.py`:

```python
ITEM_PIPELINES = {
    "oenb_scraper.pipelines.DeduplicationPipeline": 100,
    "oenb_scraper.pipelines.FileSizePipeline": 200,
    "oenb_scraper.pipelines.PdfAnalysisPipeline": 300,
}
```

**Step 4: Add missing import to pipelines**

Add at top of `scraper/oenb_scraper/pipelines.py`:

```python
import scrapy.exceptions
```

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/
git commit -m "feat: add PDF analysis and file size pipelines"
```

---

## Task 6: Create IWG Scoring Module

**Files:**
- Create: `analysis/__init__.py`
- Create: `analysis/iwg_scorer.py`

**Step 1: Create init file**

Create empty `analysis/__init__.py`:

```python
```

**Step 2: Create IWG scorer**

Create `analysis/iwg_scorer.py`:

```python
"""
IWG (Informationsweiterverwendungsgesetz) relevance scoring.

Scoring heuristic:
- File type: XLSX/CSV/XML +40, PDF +20, ZIP +15
- Machine readable: Yes +20, No -20
- Page section: Statistik +25, Meldewesen +15, Geldpolitik +10
- Keywords in title: "Daten", "Statistik", "Zeitreihe" +15
- Shiny App: +30

Confidence levels:
- High (70-100): Very likely IWG relevant
- Medium (40-69): Review recommended
- Low (0-39): Probably not IWG relevant
"""

import re


# Score weights
FILE_TYPE_SCORES = {
    "xlsx": 40,
    "xls": 40,
    "csv": 40,
    "xml": 40,
    "json": 40,
    "pdf": 20,
    "zip": 15,
    "doc": 5,
    "docx": 5,
    "ppt": 5,
    "pptx": 5,
}

SECTION_SCORES = {
    "statistik": 25,
    "meldewesen": 15,
    "geldpolitik": 10,
    "finanzmarkt": 10,
    "publikationen": 10,
}

KEYWORDS = [
    (r"\bdaten\b", 15),
    (r"\bstatistik", 15),
    (r"\bzeitreihe", 15),
    (r"\bdataset", 15),
    (r"\bdownload", 5),
    (r"\bbericht", 5),
    (r"\breport", 5),
    (r"\banalyse", 5),
]


def calculate_iwg_score(item: dict) -> dict:
    """
    Calculate IWG relevance score for a download item.

    Returns dict with:
        - iwg_score: int (0-100, capped)
        - iwg_confidence: str ('high', 'medium', 'low')
        - iwg_factors: list of (factor, points) tuples
    """
    score = 0
    factors = []

    # File type score
    file_type = (item.get("file_type") or "").lower()
    if file_type in FILE_TYPE_SCORES:
        points = FILE_TYPE_SCORES[file_type]
        score += points
        factors.append((f"Dateityp: {file_type}", points))

    # Shiny app bonus
    if item.get("type") == "shiny_app":
        score += 30
        factors.append(("Shiny App (visualisierte Daten)", 30))

    # Machine readability
    if item.get("machine_readable") is True:
        score += 20
        factors.append(("Maschinenlesbar", 20))
    elif item.get("machine_readable") is False:
        score -= 20
        factors.append(("Nicht maschinenlesbar", -20))

    # Has tables (for PDFs)
    if item.get("has_tables") is True:
        score += 10
        factors.append(("Enthält Tabellen", 10))

    # Section score
    section = (item.get("page_section") or "").lower()
    for section_key, points in SECTION_SCORES.items():
        if section_key in section:
            score += points
            factors.append((f"Bereich: {section}", points))
            break

    # Keyword matching in title
    title = (item.get("title") or "").lower()
    heading = (item.get("section_heading") or "").lower()
    text_to_check = f"{title} {heading}"

    matched_keywords = set()
    for pattern, points in KEYWORDS:
        if re.search(pattern, text_to_check, re.I):
            keyword = pattern.replace(r"\b", "").replace("\\", "")
            if keyword not in matched_keywords:
                matched_keywords.add(keyword)
                score += points
                factors.append((f"Keyword: {keyword}", points))

    # Cap score at 0-100
    score = max(0, min(100, score))

    # Determine confidence level
    if score >= 70:
        confidence = "high"
    elif score >= 40:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "iwg_score": score,
        "iwg_confidence": confidence,
        "iwg_factors": factors,
    }


def enrich_items_with_scores(items: list[dict]) -> list[dict]:
    """Add IWG scores to a list of items."""
    enriched = []
    for item in items:
        result = calculate_iwg_score(item)
        enriched_item = {**item, **result}
        enriched.append(enriched_item)
    return enriched
```

**Step 3: Commit**

```bash
git add analysis/
git commit -m "feat: implement IWG relevance scoring"
```

---

## Task 7: Create Dashboard Generator

**Files:**
- Create: `analysis/dashboard.py`
- Create: `analysis/templates/dashboard.html`

**Step 1: Create templates directory**

Run:
```bash
mkdir -p analysis/templates
```

**Step 2: Create dashboard HTML template**

Create `analysis/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OeNB Downloads - IWG Analyse</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }

        /* Summary cards */
        .summary {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            min-width: 120px;
            text-align: center;
        }
        .card .number { font-size: 2em; font-weight: bold; }
        .card .label { color: #666; font-size: 0.9em; }
        .card.high .number { color: #22c55e; }
        .card.medium .number { color: #eab308; }
        .card.low .number { color: #ef4444; }

        /* Filters */
        .filters {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filters select, .filters input {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        .filters button {
            padding: 8px 16px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        .filters button:hover { background: #2563eb; }

        /* Table */
        .table-container {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
        }
        th:hover { background: #e9ecef; }
        tr:hover { background: #f8f9fa; }

        /* Confidence badges */
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        .badge.high { background: #dcfce7; color: #166534; }
        .badge.medium { background: #fef9c3; color: #854d0e; }
        .badge.low { background: #fee2e2; color: #991b1b; }

        /* Links */
        a { color: #3b82f6; text-decoration: none; }
        a:hover { text-decoration: underline; }

        /* File type badges */
        .file-type {
            display: inline-block;
            padding: 2px 6px;
            background: #e5e7eb;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
        }

        .truncate {
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* Stats */
        .stats {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .stats h3 { margin: 0 0 10px 0; font-size: 14px; color: #666; }
        .stat-row { display: flex; gap: 20px; flex-wrap: wrap; }
        .stat-item { font-size: 13px; }
        .stat-item strong { color: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>OeNB Downloads - IWG Analyse</h1>

        <!-- Summary cards -->
        <div class="summary">
            <div class="card">
                <div class="number">{{ total_count }}</div>
                <div class="label">Gesamt</div>
            </div>
            <div class="card high">
                <div class="number">{{ high_count }}</div>
                <div class="label">🟢 Hoch</div>
            </div>
            <div class="card medium">
                <div class="number">{{ medium_count }}</div>
                <div class="label">🟡 Mittel</div>
            </div>
            <div class="card low">
                <div class="number">{{ low_count }}</div>
                <div class="label">🔴 Niedrig</div>
            </div>
        </div>

        <!-- Statistics -->
        <div class="stats">
            <h3>Dateitypen</h3>
            <div class="stat-row">
                {% for ftype, count in file_type_stats.items() %}
                <div class="stat-item"><strong>{{ ftype.upper() }}:</strong> {{ count }}</div>
                {% endfor %}
            </div>
        </div>

        <!-- Filters -->
        <div class="filters">
            <select id="filterConfidence">
                <option value="">Alle Konfidenz</option>
                <option value="high">🟢 Hoch</option>
                <option value="medium">🟡 Mittel</option>
                <option value="low">🔴 Niedrig</option>
            </select>
            <select id="filterType">
                <option value="">Alle Dateitypen</option>
                {% for ftype in file_types %}
                <option value="{{ ftype }}">{{ ftype.upper() }}</option>
                {% endfor %}
            </select>
            <select id="filterSection">
                <option value="">Alle Bereiche</option>
                {% for section in sections %}
                <option value="{{ section }}">{{ section }}</option>
                {% endfor %}
            </select>
            <input type="text" id="filterSearch" placeholder="Suche...">
            <button onclick="exportCSV()">CSV Export</button>
        </div>

        <!-- Table -->
        <div class="table-container">
            <table id="dataTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Titel</th>
                        <th onclick="sortTable(1)">Typ</th>
                        <th onclick="sortTable(2)">Bereich</th>
                        <th onclick="sortTable(3)">IWG Score</th>
                        <th onclick="sortTable(4)">Fundort</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in items %}
                    <tr data-confidence="{{ item.iwg_confidence }}"
                        data-filetype="{{ item.file_type }}"
                        data-section="{{ item.page_section }}">
                        <td>
                            <a href="{{ item.url }}" target="_blank" class="truncate" title="{{ item.title }}">
                                {{ item.title or item.url | truncate(50) }}
                            </a>
                        </td>
                        <td><span class="file-type">{{ item.file_type }}</span></td>
                        <td>{{ item.page_section }}</td>
                        <td>
                            <span class="badge {{ item.iwg_confidence }}">
                                {{ item.iwg_score }}
                            </span>
                        </td>
                        <td>
                            <a href="{{ item.found_on_page }}" target="_blank" class="truncate" title="{{ item.found_on_page }}">
                                {{ item.found_on_page | truncate(40) }}
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Data for CSV export
        const data = {{ items_json | safe }};

        // Filter functionality
        function applyFilters() {
            const confidence = document.getElementById('filterConfidence').value;
            const fileType = document.getElementById('filterType').value;
            const section = document.getElementById('filterSection').value;
            const search = document.getElementById('filterSearch').value.toLowerCase();

            const rows = document.querySelectorAll('#dataTable tbody tr');
            rows.forEach(row => {
                const matchConfidence = !confidence || row.dataset.confidence === confidence;
                const matchType = !fileType || row.dataset.filetype === fileType;
                const matchSection = !section || row.dataset.section === section;
                const matchSearch = !search || row.textContent.toLowerCase().includes(search);

                row.style.display = (matchConfidence && matchType && matchSection && matchSearch) ? '' : 'none';
            });
        }

        document.getElementById('filterConfidence').addEventListener('change', applyFilters);
        document.getElementById('filterType').addEventListener('change', applyFilters);
        document.getElementById('filterSection').addEventListener('change', applyFilters);
        document.getElementById('filterSearch').addEventListener('input', applyFilters);

        // Sort functionality
        let sortDirection = {};
        function sortTable(columnIndex) {
            const table = document.getElementById('dataTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            sortDirection[columnIndex] = !sortDirection[columnIndex];
            const dir = sortDirection[columnIndex] ? 1 : -1;

            rows.sort((a, b) => {
                const aVal = a.cells[columnIndex].textContent.trim();
                const bVal = b.cells[columnIndex].textContent.trim();

                // Try numeric sort for score column
                if (columnIndex === 3) {
                    return (parseInt(aVal) - parseInt(bVal)) * dir;
                }
                return aVal.localeCompare(bVal, 'de') * dir;
            });

            rows.forEach(row => tbody.appendChild(row));
        }

        // CSV export
        function exportCSV() {
            const headers = ['URL', 'Titel', 'Dateityp', 'Bereich', 'IWG Score', 'Konfidenz', 'Fundort', 'Maschinenlesbar'];
            const csvRows = [headers.join(';')];

            data.forEach(item => {
                const row = [
                    item.url,
                    (item.title || '').replace(/;/g, ','),
                    item.file_type,
                    item.page_section,
                    item.iwg_score,
                    item.iwg_confidence,
                    item.found_on_page,
                    item.machine_readable
                ];
                csvRows.push(row.join(';'));
            });

            const csvContent = csvRows.join('\n');
            const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'oenb_iwg_analyse.csv';
            link.click();
        }
    </script>
</body>
</html>
```

**Step 3: Create dashboard generator**

Create `analysis/dashboard.py`:

```python
"""Generate HTML dashboard from scraped data."""

import json
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from analysis.iwg_scorer import enrich_items_with_scores


def load_data(json_path: str) -> list[dict]:
    """Load scraped data from JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_dashboard(items: list[dict], output_path: str) -> None:
    """Generate HTML dashboard from items."""
    # Enrich with IWG scores
    enriched = enrich_items_with_scores(items)

    # Sort by score descending
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    # Calculate statistics
    total_count = len(enriched)
    high_count = sum(1 for i in enriched if i["iwg_confidence"] == "high")
    medium_count = sum(1 for i in enriched if i["iwg_confidence"] == "medium")
    low_count = sum(1 for i in enriched if i["iwg_confidence"] == "low")

    # File type stats
    file_type_stats = Counter(i["file_type"] for i in enriched)

    # Unique values for filters
    file_types = sorted(set(i["file_type"] for i in enriched))
    sections = sorted(set(i["page_section"] for i in enriched if i["page_section"]))

    # Setup Jinja2
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))

    # Add truncate filter
    def truncate(s, length=50):
        s = str(s) if s else ""
        return s[:length] + "..." if len(s) > length else s
    env.filters["truncate"] = truncate

    template = env.get_template("dashboard.html")

    # Render
    html = template.render(
        items=enriched,
        items_json=json.dumps(enriched, ensure_ascii=False),
        total_count=total_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        file_type_stats=dict(file_type_stats),
        file_types=file_types,
        sections=sections,
    )

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    print(f"Total items: {total_count}")
    print(f"  High relevance: {high_count}")
    print(f"  Medium relevance: {medium_count}")
    print(f"  Low relevance: {low_count}")


def generate_csv(items: list[dict], output_path: str) -> None:
    """Generate CSV export from items."""
    enriched = enrich_items_with_scores(items)
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    headers = [
        "URL", "Titel", "Typ", "Dateityp", "Größe (Bytes)", "Bereich",
        "IWG Score", "Konfidenz", "Maschinenlesbar", "Hat Tabellen", "Fundort"
    ]

    lines = [";".join(headers)]
    for item in enriched:
        row = [
            item.get("url", ""),
            (item.get("title") or "").replace(";", ","),
            item.get("type", ""),
            item.get("file_type", ""),
            str(item.get("file_size_bytes") or ""),
            item.get("page_section", ""),
            str(item.get("iwg_score", "")),
            item.get("iwg_confidence", ""),
            str(item.get("machine_readable", "")),
            str(item.get("has_tables", "")),
            item.get("found_on_page", ""),
        ]
        lines.append(";".join(row))

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    print(f"CSV generated: {output_path}")
```

**Step 4: Commit**

```bash
git add analysis/
git commit -m "feat: add dashboard generator with HTML template"
```

---

## Task 8: Create Main Analysis Script

**Files:**
- Create: `analysis/analyze.py`

**Step 1: Create the main analysis script**

Create `analysis/analyze.py`:

```python
#!/usr/bin/env python3
"""
Main analysis script for OeNB IWG audit.

Usage:
    python analysis/analyze.py [--input data/downloads.json] [--output-dir output/]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.dashboard import generate_dashboard, generate_csv, load_data


def main():
    parser = argparse.ArgumentParser(description="Analyze OeNB downloads for IWG relevance")
    parser.add_argument(
        "--input", "-i",
        default="data/downloads.json",
        help="Input JSON file from scraper (default: data/downloads.json)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Output directory (default: output/)"
    )
    args = parser.parse_args()

    # Check input exists
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run the scraper first: cd scraper && scrapy crawl oenb -o ../data/downloads.json")
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading data from {input_path}...")
    items = load_data(str(input_path))
    print(f"Loaded {len(items)} items")

    if not items:
        print("No items found. Check if the scraper ran successfully.")
        sys.exit(1)

    # Generate outputs
    dashboard_path = output_dir / "dashboard.html"
    csv_path = output_dir / "downloads.csv"

    print("\nGenerating dashboard...")
    generate_dashboard(items, str(dashboard_path))

    print("\nGenerating CSV...")
    generate_csv(items, str(csv_path))

    print(f"\nDone! Open {dashboard_path} in your browser.")


if __name__ == "__main__":
    main()
```

**Step 2: Make script executable**

Run:
```bash
chmod +x analysis/analyze.py
```

**Step 3: Commit**

```bash
git add analysis/analyze.py
git commit -m "feat: add main analysis script"
```

---

## Task 9: Create Run Script

**Files:**
- Create: `run.sh`

**Step 1: Create convenience run script**

Create `run.sh`:

```bash
#!/bin/bash
set -e

echo "=== OeNB IWG Scraper ==="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Run scraper
echo ""
echo "Starting scraper (this may take 10-30 minutes)..."
echo "Press Ctrl+C to stop early."
echo ""

cd scraper
scrapy crawl oenb -o ../data/downloads.json -t json
cd ..

# Run analysis
echo ""
echo "Running analysis..."
python analysis/analyze.py

echo ""
echo "=== Complete ==="
echo "Open output/dashboard.html in your browser"
```

**Step 2: Make script executable**

Run:
```bash
chmod +x run.sh
```

**Step 3: Commit**

```bash
git add run.sh
git commit -m "feat: add convenience run script"
```

---

## Task 10: Test Full Pipeline

**Step 1: Create test with limited pages**

Run a quick test with only 10 pages:
```bash
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd scraper && scrapy crawl oenb -o ../data/downloads.json -t json -s CLOSESPIDER_PAGECOUNT=10
cd ..
```

**Step 2: Run analysis on test data**

```bash
python analysis/analyze.py
```

Expected: Creates `output/dashboard.html` and `output/downloads.csv`

**Step 3: Verify dashboard opens**

```bash
xdg-open output/dashboard.html  # Linux
# or: open output/dashboard.html  # macOS
```

**Step 4: Commit test results (optional)**

```bash
git add -A
git commit -m "test: verify full pipeline works"
```

---

## Summary

After completing all tasks you will have:

1. **Scrapy spider** that crawls oenb.at and captures all downloads + Shiny apps
2. **PDF analyzer** that checks machine readability
3. **IWG scorer** with configurable heuristics
4. **HTML dashboard** with filtering, sorting, and CSV export
5. **Convenience scripts** for easy execution

**To run the full scrape:**
```bash
./run.sh
```

**To run analysis only (if data exists):**
```bash
python analysis/analyze.py
```
