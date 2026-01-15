# IWG-Compliance + Sitemap-Visualisierung Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the OeNB crawler for full IWG compliance (more formats, HTML tables, APIs) and add an interactive sitemap visualization to the dashboard.

**Architecture:** Spider gets new detection methods for tables and APIs, items.py gets new fields. Dashboard template gets a 5th tab with SVG-based Tufte-style visualization. A new sitemap_parser.py extracts structure from saved HTML sitemap.

**Tech Stack:** Python/Scrapy, Jinja2, HTML/CSS/SVG, BeautifulSoup

---

## Task 1: Add New File Formats to Spider

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py:19-22`
- Test: `tests/test_spider.py`

**Step 1: Write failing tests for new formats**

Add to `tests/test_spider.py` in `TestDownloadDetection` class:

```python
def test_detects_txt_as_download(self):
    assert self.spider._is_download("https://example.com/file.txt")

def test_detects_odt_as_download(self):
    assert self.spider._is_download("https://example.com/doc.odt")

def test_detects_geojson_as_download(self):
    assert self.spider._is_download("https://example.com/map.geojson")

def test_detects_rdf_as_download(self):
    assert self.spider._is_download("https://example.com/data.rdf")

def test_detects_ttl_as_download(self):
    assert self.spider._is_download("https://example.com/data.ttl")
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spider.py -v -k "txt or odt or geojson or rdf or ttl"`
Expected: FAIL (5 failures)

**Step 3: Update DOWNLOAD_EXTENSIONS**

In `scraper/oenb_scraper/spiders/oenb_spider.py`, change:

```python
DOWNLOAD_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".xml", ".zip",
    ".doc", ".docx", ".ppt", ".pptx", ".json",
    # IWG additions
    ".txt", ".odt", ".rtf", ".epub",      # Text/Docs
    ".geojson", ".kml", ".gml",            # Geo
    ".rdf", ".ttl", ".ods"                 # Structured data
}
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_spider.py -v -k "txt or odt or geojson or rdf or ttl"`
Expected: PASS (5 passed)

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py tests/test_spider.py
git commit -m "feat: add IWG-required file formats (txt, odt, rtf, epub, geojson, kml, gml, rdf, ttl, ods)"
```

---

## Task 2: Add Items Field for HTML Tables

**Files:**
- Modify: `scraper/oenb_scraper/items.py`

**Step 1: Add new field to DownloadItem**

In `scraper/oenb_scraper/items.py`, add after line 20:

```python
has_html_tables = scrapy.Field()  # For webpages: True if page has data tables
table_count = scrapy.Field()  # Number of substantial tables on page
```

**Step 2: Commit**

```bash
git add scraper/oenb_scraper/items.py
git commit -m "feat: add has_html_tables and table_count fields to DownloadItem"
```

---

## Task 3: Implement HTML Table Detection

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_spider.py`

**Step 1: Write failing test**

Add new test class to `tests/test_spider.py`:

```python
class TestTableDetection:
    """Test HTML table detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_substantial_table(self):
        """Table with 3+ rows should be detected."""
        html = """
        <table>
            <tr><th>A</th><th>B</th></tr>
            <tr><td>1</td><td>2</td></tr>
            <tr><td>3</td><td>4</td></tr>
            <tr><td>5</td><td>6</td></tr>
        </table>
        """
        assert self.spider._count_data_tables(html) == 1

    def test_ignores_small_table(self):
        """Table with <3 rows should be ignored."""
        html = "<table><tr><td>X</td></tr></table>"
        assert self.spider._count_data_tables(html) == 0

    def test_ignores_layout_table(self):
        """Tables with layout classes should be ignored."""
        html = '<table class="layout"><tr><td>X</td><td>Y</td></tr><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>'
        assert self.spider._count_data_tables(html) == 0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spider.py::TestTableDetection -v`
Expected: FAIL (method not found)

**Step 3: Implement _count_data_tables method**

Add to `oenb_spider.py` after `_extract_sources_from_shiny`:

```python
def _count_data_tables(self, html: str) -> int:
    """Count substantial data tables in HTML.

    A substantial table has at least 3 rows and is not a layout table.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    count = 0
    for table in soup.find_all("table"):
        # Skip layout tables
        table_class = table.get("class", [])
        if any(c in ["layout", "nav", "menu", "navigation"] for c in table_class):
            continue

        # Count rows
        rows = table.find_all("tr")
        if len(rows) >= 3:
            count += 1

    return count
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_spider.py::TestTableDetection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py tests/test_spider.py
git commit -m "feat: add HTML table detection method"
```

---

## Task 4: Integrate Table Detection into Parse

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`

**Step 1: Update parse method to detect and yield webpage items**

Add after the iframe loop in `parse()` method (around line 100):

```python
# Check for data tables on this page
table_count = self._count_data_tables(response.text)
if table_count > 0:
    yield self._create_webpage_item(
        url=page_url,
        title=response.css("title::text").get() or "",
        page_section=page_section,
        page_date=page_date,
        language=page_language,
        table_count=table_count,
    )
```

**Step 2: Add _create_webpage_item method**

Add after `_create_shiny_item`:

```python
def _create_webpage_item(self, **kwargs) -> DownloadItem:
    """Create a DownloadItem for a webpage with data tables."""
    item = DownloadItem()
    item["url"] = kwargs["url"]
    item["type"] = "webpage_with_data"
    item["file_type"] = "html"
    item["file_size_bytes"] = None
    item["title"] = kwargs["title"]
    item["found_on_page"] = kwargs["url"]
    item["page_section"] = kwargs["page_section"]
    item["section_heading"] = ""
    item["page_date"] = kwargs["page_date"]
    item["scraped_at"] = datetime.utcnow().isoformat() + "Z"
    item["machine_readable"] = True
    item["has_tables"] = True
    item["has_html_tables"] = True
    item["table_count"] = kwargs["table_count"]
    item["language"] = kwargs["language"]
    item["found_in_languages"] = None
    item["sources"] = []
    return item
```

**Step 3: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py
git commit -m "feat: integrate table detection into spider parse"
```

---

## Task 5: Implement API Endpoint Detection

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_spider.py`

**Step 1: Write failing tests**

Add to `tests/test_spider.py`:

```python
class TestApiDetection:
    """Test API endpoint detection."""

    def setup_method(self):
        self.spider = OenbSpider()

    def test_detects_api_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/api/data")

    def test_detects_rest_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/rest/v1/rates")

    def test_detects_oearb_path(self):
        assert self.spider._is_potential_api("https://www.oenb.at/oearb/zinssatzwechselkurse/download")

    def test_regular_page_is_not_api(self):
        assert not self.spider._is_potential_api("https://www.oenb.at/Statistik/data.html")
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spider.py::TestApiDetection -v`
Expected: FAIL

**Step 3: Implement _is_potential_api method**

Add to spider:

```python
# API path patterns
API_PATTERNS = ["/api/", "/rest/", "/oearb/", "/data/export", "/export/"]

def _is_potential_api(self, url: str) -> bool:
    """Check if URL looks like an API endpoint."""
    path = urlparse(url).path.lower()
    return any(pattern in path for pattern in self.API_PATTERNS)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_spider.py::TestApiDetection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py tests/test_spider.py
git commit -m "feat: add API endpoint detection"
```

---

## Task 6: Create Sitemap Parser

**Files:**
- Create: `analysis/sitemap_parser.py`
- Test: `tests/test_sitemap_parser.py`

**Step 1: Create sitemap parser module**

Create `analysis/sitemap_parser.py`:

```python
"""Parse OeNB HTML sitemap to extract site structure."""

from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup


def parse_sitemap(html_path: str) -> dict:
    """Parse OeNB sitemap HTML and return structure.

    Returns dict with:
    - sections: list of {name, url, page_count, subsections}
    """
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    sections = defaultdict(lambda: {"url": "", "page_count": 0, "subsections": []})

    for link in soup.find_all("a", class_=lambda x: x and "navigation_link" in x):
        href = link.get("href", "")
        if "oenb.at/" not in href:
            continue

        path = href.split("oenb.at/")[-1].strip("/")
        parts = path.split("/")

        if not parts or not parts[0]:
            continue

        main_section = parts[0]

        # Skip English section marker
        if main_section.lower() == "en":
            continue

        if not sections[main_section]["url"]:
            sections[main_section]["url"] = f"https://www.oenb.at/{main_section}"

        sections[main_section]["page_count"] += 1

    # Convert to list sorted by page count
    result = []
    for name, data in sorted(sections.items(), key=lambda x: -x[1]["page_count"]):
        if data["page_count"] > 0 and not name.endswith(".html"):
            result.append({
                "name": name.replace("-", " ").title(),
                "url": data["url"],
                "page_count": data["page_count"],
            })

    return {"sections": result}


def get_sitemap_path() -> Path:
    """Get path to saved sitemap HTML."""
    return Path(__file__).parent.parent / "scraper" / "sitemap" / "Sitemap - Oesterreichische Nationalbank (OeNB).html"
```

**Step 2: Create test file**

Create `tests/test_sitemap_parser.py`:

```python
"""Tests for sitemap parser."""

import pytest
from analysis.sitemap_parser import parse_sitemap, get_sitemap_path


class TestSitemapParser:
    def test_parses_sitemap_structure(self):
        path = get_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap file not found")

        result = parse_sitemap(str(path))

        assert "sections" in result
        assert len(result["sections"]) > 0

        # Check structure of first section
        first = result["sections"][0]
        assert "name" in first
        assert "url" in first
        assert "page_count" in first
        assert first["page_count"] > 0

    def test_sections_have_valid_urls(self):
        path = get_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap file not found")

        result = parse_sitemap(str(path))

        for section in result["sections"]:
            assert section["url"].startswith("https://www.oenb.at/")
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_sitemap_parser.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add analysis/sitemap_parser.py tests/test_sitemap_parser.py
git commit -m "feat: add sitemap parser for dashboard visualization"
```

---

## Task 7: Update Dashboard Generator

**Files:**
- Modify: `analysis/generate_claude_dashboard.py`

**Step 1: Import sitemap parser and add data**

Add import at top:

```python
from analysis.sitemap_parser import parse_sitemap, get_sitemap_path
```

**Step 2: Add sitemap data to template rendering**

In `generate_claude_dashboard()` function, before `template.render()`, add:

```python
# Parse sitemap for visualization
sitemap_path = get_sitemap_path()
if sitemap_path.exists():
    sitemap_data = parse_sitemap(str(sitemap_path))
    # Add download counts per section
    section_downloads = Counter(i["page_section"] for i in enriched if i.get("page_section"))
    for section in sitemap_data["sections"]:
        section_key = section["name"].replace(" ", "-").replace("Ue", "Ue")
        # Try various key formats
        download_count = 0
        for key in [section["name"], section_key, section["url"].split("/")[-1]]:
            if key in section_downloads:
                download_count = section_downloads[key]
                break
        section["download_count"] = download_count
else:
    sitemap_data = {"sections": []}
```

**Step 3: Add sitemap_data to template.render()**

Add `sitemap_data=sitemap_data` to the render call.

**Step 4: Commit**

```bash
git add analysis/generate_claude_dashboard.py
git commit -m "feat: integrate sitemap data into dashboard generator"
```

---

## Task 8: Add Sitemap Tab to Dashboard Template

**Files:**
- Modify: `analysis/templates/claude_dashboard.html`

**Step 1: Add tab button**

After line 429 (rejected tab button), add:

```html
<button class="tab" data-tab="sitemap">Sitemap</button>
```

**Step 2: Add tab content section**

After the "Nicht IWG Relevant" tab content div, add:

```html
<!-- Tab 5: Sitemap -->
<div id="tab-sitemap" class="tab-content">
    <div class="card">
        <h2>OeNB Website-Struktur</h2>
        <p class="text-muted">Klicken Sie auf einen Bereich, um die OeNB-Seite zu öffnen.</p>

        <div class="sitemap-viz" style="margin-top: 2rem;">
            {% for section in sitemap_data.sections %}
            <a href="{{ section.url }}" target="_blank" class="sitemap-bar" style="text-decoration: none; display: block; margin-bottom: 0.5rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span style="width: 120px; font-size: 0.85rem; color: #333;">{{ section.name }}</span>
                    <div style="flex: 1; background: #f0f0f0; height: 24px; position: relative;">
                        <div style="background: #2c5282; height: 100%; width: {{ (section.page_count / sitemap_data.sections[0].page_count * 100)|round }}%;"></div>
                    </div>
                    <span style="width: 60px; text-align: right; font-size: 0.8rem; color: #666;">{{ section.page_count }}</span>
                    <span style="width: 80px; text-align: right; font-size: 0.8rem; color: #2c5282; font-weight: 500;">{{ section.download_count }} DL</span>
                </div>
            </a>
            {% endfor %}
        </div>

        <p style="margin-top: 2rem; font-size: 0.75rem; color: #888;">
            Balkenbreite = Anzahl Seiten im Bereich | DL = gefundene Downloads
        </p>
    </div>
</div>
```

**Step 3: Add hover effect CSS**

Add in the `<style>` section:

```css
/* Sitemap visualization */
.sitemap-bar:hover div > div {
    background: #4a7ab8 !important;
}
.sitemap-bar:hover {
    background: #fafafa;
}
```

**Step 4: Commit**

```bash
git add analysis/templates/claude_dashboard.html
git commit -m "feat: add sitemap visualization tab to dashboard"
```

---

## Task 9: Run Full Test Suite

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Commit if any fixes needed**

---

## Task 10: Generate and Verify Dashboard

**Step 1: Generate dashboard**

Run: `PYTHONPATH=. python analysis/generate_claude_dashboard.py --input data/2026-01-14_1122_downloads.json --skip-scan`

**Step 2: Open in browser and verify**

- All 5 tabs visible
- Sitemap tab shows bars
- Clicking bars opens OeNB pages
- Download counts shown

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete IWG compliance extensions and sitemap visualization"
```

---

## Verification Checklist

- [ ] New file formats detected (.txt, .odt, .geojson, etc.)
- [ ] HTML tables detected on pages
- [ ] API patterns detected
- [ ] Sitemap tab visible in dashboard
- [ ] Bars are proportional to page count
- [ ] Clicking bars opens OeNB sections
- [ ] Download counts shown per section
- [ ] All tests pass
