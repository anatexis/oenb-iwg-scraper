# OeNB Crawler Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the OeNB crawler into a chatbot-ready knowledge-base pipeline that crawls the full OeNB web presence, captures all relevant open-data resources including ISAweb and Shiny surfaces, and supports incremental recrawls that revisit only changed or newly discovered resources.

**Architecture:** Keep broad discovery from the current spider, but split the new crawler into resource-specific pipelines: full-site HTML discovery, asset/resource classification, structured statistics handling, ISAweb webservice harvesting, and persistent incremental scheduling. Persist both navigation documents and structured dataset entities so the later chatbot can answer both website and numeric/statistics questions with provenance. Incremental crawling is handled through a persistent frontier plus HTTP validators and body-hash invalidation instead of reprocessing every page on every run.

**Tech Stack:** Python, Scrapy, SQLite, pytest, existing `analysis` export pipeline, OeNB ISAweb webservice (`isadataservice/*`)

### Task 1: Freeze the target data model

**Files:**
- Modify: `scraper/oenb_scraper/items.py`
- Create: `scraper/oenb_scraper/resource_types.py`
- Test: `tests/test_resource_types.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.resource_types import ResourceKind


def test_resource_kinds_cover_site_and_statistics_scope():
    assert ResourceKind.PAGE_DOCUMENT.value == "page_document"
    assert ResourceKind.SHINY_APP.value == "shiny_app"
    assert ResourceKind.ISAWEB_DATASET.value == "isaweb_dataset"
    assert ResourceKind.RELEASE_EVENT.value == "release_event"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_resource_types.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing enum members.

**Step 3: Write minimal implementation**

Create a resource-kind enum plus a small compatibility layer in `items.py`. The target model should cover:

- `page_document`
- `asset_document`
- `html_table`
- `standardized_table_topic`
- `dataset_metadata`
- `isaweb_entry`
- `isaweb_dataset`
- `isaweb_observation_batch`
- `release_event`
- `shiny_app`
- `external_app`

Keep `DownloadItem` only as a short-lived compatibility wrapper if needed.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_resource_types.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/items.py scraper/oenb_scraper/resource_types.py tests/test_resource_types.py
git commit -m "refactor: define crawler resource model"
```

### Task 2: Extract URL normalization into a single reusable module

**Files:**
- Create: `scraper/oenb_scraper/urlnorm.py`
- Modify: `scraper/oenb_scraper/pipelines.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_urlnorm.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.urlnorm import normalize_url


def test_normalize_url_removes_session_and_fragment():
    url = "https://www.oenb.at/isawebstat/dynabfrage/defineParams;jsessionid=ABC?hierarchieId=11&lang=DE#foo"
    assert normalize_url(url) == "https://www.oenb.at/isawebstat/dynabfrage/defineParams?hierarchieId=11&lang=DE"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_urlnorm.py -q`
Expected: FAIL because module/function does not exist.

**Step 3: Write minimal implementation**

Move normalization logic out of the dedup pipeline into `urlnorm.py` and make both the spider and the pipeline call the same function.

Normalization rules:

- drop fragments
- strip `jsessionid` path segments
- remove session-like query params
- sort query params
- preserve semantically relevant parameters like `lang`, `hierid`, `pos`, `dval*`, `freq`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_urlnorm.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/urlnorm.py scraper/oenb_scraper/pipelines.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_urlnorm.py
git commit -m "refactor: centralize url normalization"
```

### Task 3: Replace flat resource detection with an explicit classifier

**Files:**
- Create: `scraper/oenb_scraper/resource_classifier.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_resource_classifier.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.resource_classifier import classify_url


def test_classify_isaweb_chart():
    result = classify_url("https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1")
    assert result.kind == "isaweb_entry"
    assert result.subtype == "chart"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_resource_classifier.py -q`
Expected: FAIL because classifier does not exist.

**Step 3: Write minimal implementation**

Create a classifier that returns structured results for:

- internal HTML page
- asset download
- standardized table topic
- explanatory note
- publication schedule
- ISAweb `dynabfrage`
- ISAweb `defineParams`
- ISAweb `showResult`
- ISAweb chart
- ISAweb release page
- Shiny app
- external app
- possible API/export endpoint

Refactor the spider to call the classifier instead of manual nested `if/elif` checks.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_resource_classifier.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/resource_classifier.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_resource_classifier.py
git commit -m "refactor: classify crawler resources explicitly"
```

### Task 4: Expand crawl scope to full OeNB web presence

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Create: `scraper/oenb_scraper/scope.py`
- Test: `tests/test_scope.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.scope import CrawlScope


def test_oenb_owned_subdomain_is_primary_scope():
    scope = CrawlScope(primary_hosts={"oenb.at", "www.oenb.at", "finanzbildung.oenb.at"})
    assert scope.classify_host("www.oenb.at") == "primary"
    assert scope.classify_host("shiny.oenb.at") == "primary"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scope.py -q`
Expected: FAIL because scope module does not exist.

**Step 3: Write minimal implementation**

Introduce a dedicated scope module that distinguishes:

- `primary` OeNB hosts
- `secondary` externally hosted app surfaces linked by OeNB
- `out_of_scope`

Replace hardcoded `allowed_domains` assumptions with configuration-friendly scope handling.

The default primary scope should cover:

- `oenb.at`
- `www.oenb.at`
- `finanzbildung.oenb.at`
- `shiny.oenb.at` if confirmed reachable

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scope.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/scope.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_scope.py
git commit -m "feat: define full-site crawl scope"
```

### Task 5: Add a persistent crawl frontier for incremental recrawls

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Create: `scraper/oenb_scraper/frontier.py`
- Test: `tests/test_frontier.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from oenb_scraper.database import init_db
from oenb_scraper.frontier import upsert_frontier_url, get_due_frontier_urls


def test_frontier_returns_due_urls(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")
    upsert_frontier_url(conn, "https://www.oenb.at/test.html", priority=50, revisit_after="2026-03-18T10:00:00Z")
    rows = get_due_frontier_urls(conn, now="2026-03-18T10:00:00Z", limit=10)
    assert rows[0]["url"] == "https://www.oenb.at/test.html"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontier.py -q`
Expected: FAIL because frontier tables/helpers do not exist.

**Step 3: Write minimal implementation**

Extend the database schema with frontier-oriented tables, for example:

- `frontier_urls`
- `resource_links`
- `resource_versions`

The frontier should track:

- normalized URL
- discovered_at
- last_seen_at
- last_crawled_at
- priority
- scope class
- resource class
- revisit_after
- active flag
- referring URL count

`get_due_frontier_urls()` should return only URLs that are due for fetch, so the crawler does not re-read the entire site every run.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontier.py tests/test_database.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py scraper/oenb_scraper/frontier.py tests/test_frontier.py
git commit -m "feat: add persistent incremental frontier"
```

### Task 6: Add HTTP freshness and content-change tracking

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Create: `scraper/oenb_scraper/freshness.py`
- Test: `tests/test_freshness.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.freshness import should_reextract_content


def test_same_body_hash_skips_reextraction():
    assert should_reextract_content(previous_hash="abc", current_hash="abc") is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_freshness.py -q`
Expected: FAIL because helper does not exist.

**Step 3: Write minimal implementation**

Add freshness helpers and schema support for:

- `etag`
- `last_modified`
- `body_hash`
- fetch outcome
- extraction invalidation on change

Use current `store_page()` behavior as the base, but make it explicit and reusable so both HTML and structured resources can decide whether downstream extraction is necessary.

Incremental policy:

- if `304 Not Modified`, update crawl metadata only
- if body hash unchanged, skip text/table re-extraction
- if body hash changed, invalidate derived artifacts and re-extract

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_freshness.py tests/test_database.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py scraper/oenb_scraper/freshness.py tests/test_freshness.py
git commit -m "feat: add change-aware extraction invalidation"
```

### Task 7: Split HTML storage from derived content extraction

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Modify: `analysis/extract_text.py`
- Create: `analysis/extract_page_documents.py`
- Test: `tests/test_extract_text.py`
- Test: `tests/test_page_documents.py`

**Step 1: Write the failing test**

```python
def test_changed_page_is_marked_pending_for_reextraction():
    # Arrange: store initial page, then changed body
    # Assert: derived page document row is invalidated or marked stale
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_page_documents.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Separate:

- raw HTML/body storage
- text extraction
- page-document serialization

Store per page document:

- canonical URL
- final URL
- title
- cleaned text
- headings
- language
- section
- crawl timestamp
- body hash
- source page metadata

Only regenerate derived page-document output when the source version changes.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract_text.py tests/test_page_documents.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py analysis/extract_text.py analysis/extract_page_documents.py tests/test_page_documents.py
git commit -m "refactor: separate raw html from page document extraction"
```

### Task 8: Capture the graph of discovered links and app embeddings

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Modify: `scraper/oenb_scraper/database.py`
- Create: `tests/test_resource_links.py`

**Step 1: Write the failing test**

```python
def test_isaweb_link_is_stored_with_parent_context():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_resource_links.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Persist resource-link edges for every discovered link:

- `source_url`
- `target_url`
- normalized target URL
- link text
- section heading
- resource classification
- embed type (`a`, `iframe`, etc.)

This is required so frequently linked ISAweb pages can be prioritized without storing duplicate canonical resources.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_resource_links.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_spider.py scraper/oenb_scraper/database.py tests/test_resource_links.py
git commit -m "feat: persist resource link graph"
```

### Task 9: Build dedicated handlers for standardized-table topic bundles

**Files:**
- Create: `scraper/oenb_scraper/standardized_tables.py`
- Modify: `scraper/oenb_scraper/resource_classifier.py`
- Test: `tests/test_standardized_tables.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.standardized_tables import classify_standardized_table_page


def test_detect_topic_bundle_members():
    result = classify_standardized_table_page(
        "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators.html"
    )
    assert result.bundle_kind == "topic"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_standardized_tables.py -q`
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

Add a standardized-tables helper that maps pages into bundle members:

- topic page
- explanatory note
- publication schedule
- chart entry
- table entry

Persist a `dataset_family_id` so these related representations stay linked.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_standardized_tables.py tests/test_resource_classifier.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/standardized_tables.py scraper/oenb_scraper/resource_classifier.py tests/test_standardized_tables.py
git commit -m "feat: model standardized table bundles"
```

### Task 9a: Build a first-class source attribution extractor

**Files:**
- Create: `scraper/oenb_scraper/source_extraction.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Modify: `scraper/oenb_scraper/database.py`
- Test: `tests/test_source_extraction_v2.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.source_extraction import extract_source_metadata


def test_extract_source_and_reporting_institutions_from_english_text():
    html = """
    <div>
      <p>Source: OeNB, Statistics Austria</p>
      <p>Reporting institutions: Statistics Austria</p>
    </div>
    """
    result = extract_source_metadata(html)
    assert "OeNB" in result.sources
    assert "Statistics Austria" in result.sources
    assert "Statistics Austria" in result.reporting_institutions
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extraction_v2.py -q`
Expected: FAIL because extractor does not exist.

**Step 3: Write minimal implementation**

Create a dedicated source extraction module that:

- searches case-insensitively for:
  - `Quelle:`
  - `Quellen:`
  - `Source:`
  - `Sources:`
  - `Datenquelle:`
  - `Data source:`
  - `Reporting institutions:`
- parses multi-source lists separated by:
  - comma
  - semicolon
  - slash
  - `und`
  - `and`
- stores:
  - normalized source names
  - raw matched source text
  - `reporting_institutions`
  - extraction method

Persist source metadata as dedicated fields instead of leaving it buried inside raw text extraction.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_source_extraction_v2.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/source_extraction.py scraper/oenb_scraper/spiders/oenb_spider.py scraper/oenb_scraper/database.py tests/test_source_extraction_v2.py
git commit -m "feat: add structured source attribution extraction"
```

### Task 9b: Add hidden chart-source extraction for Highcharts and accessibility text

**Files:**
- Modify: `scraper/oenb_scraper/source_extraction.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_chart_source_extraction.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.source_extraction import extract_source_metadata


def test_extract_source_from_chart_aria_label():
    html = '<div aria-label="Chart showing inflation. source: ECB, Eurostat"></div>'
    result = extract_source_metadata(html)
    assert "ECB" in result.sources
    assert "Eurostat" in result.sources
    assert result.source_extraction_method in {"aria-label", "chart-accessibility"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chart_source_extraction.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Extend source extraction to inspect:

- `aria-label`
- `aria-describedby`
- Highcharts-generated hidden accessibility descriptions
- elements matched by selectors such as `.highcharts-data-source`

Also capture linked source URLs found inside chart descriptions or adjacent source blocks.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chart_source_extraction.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/source_extraction.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_chart_source_extraction.py
git commit -m "feat: extract sources from chart accessibility text"
```

### Task 10: Add ISAweb discovery separate from ISAweb extraction

**Files:**
- Create: `scraper/oenb_scraper/isaweb_discovery.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Test: `tests/test_isaweb_discovery.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.isaweb_discovery import classify_isaweb_url


def test_detect_show_result_as_transient_view():
    result = classify_isaweb_url("https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11")
    assert result.kind == "show_result"
    assert result.canonicalizable is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_discovery.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Create a dedicated ISAweb discovery helper that distinguishes:

- landing
- `dynabfrage`
- `defineParams`
- `showResult`
- `createChart`
- release page
- export endpoint

It should mark `showResult` and session-shaped URLs as transient and route them to the webservice-based extractor instead of treating them as final datasets.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_isaweb_discovery.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_discovery.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_isaweb_discovery.py
git commit -m "feat: separate isaweb discovery from extraction"
```

### Task 11: Implement the ISAweb webservice client

**Files:**
- Create: `scraper/oenb_scraper/isaweb_service.py`
- Create: `tests/test_isaweb_service.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.isaweb_service import build_data_url


def test_build_data_url_preserves_pos_and_dimensions():
    url = build_data_url(
        hierid=11,
        lang="DE",
        pos=["VDBFKBSC217000"],
        dimensions={"dval1": ["AT"], "dval2": ["00100KI"]},
        starttime="2000-01-01",
    )
    assert "hierid=11" in url
    assert "pos=VDBFKBSC217000" in url
    assert "dval1=AT" in url
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_service.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Add a small client around:

- `isadataservice/content`
- `isadataservice/meta`
- `isadataservice/datafrequency`
- `isadataservice/data`

The first implementation can focus on deterministic URL construction and response parsing hooks.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_isaweb_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_service.py tests/test_isaweb_service.py
git commit -m "feat: add isaweb webservice client"
```

### Task 12: Materialize ISAweb metadata and datasets into the database

**Files:**
- Modify: `scraper/oenb_scraper/database.py`
- Create: `scraper/oenb_scraper/isaweb_store.py`
- Test: `tests/test_isaweb_store.py`

**Step 1: Write the failing test**

```python
def test_store_isaweb_dataset_with_canonical_key():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_store.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Add tables for normalized ISAweb entities, for example:

- `isaweb_datasets`
- `isaweb_dimensions`
- `isaweb_observations`
- `dataset_metadata`

Canonical dataset keys should be derived from:

- `hierid`
- `pos`
- `dval*`
- `freq`
- `lang`

Do not key datasets by `showResult` page URL.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_isaweb_store.py tests/test_database.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/database.py scraper/oenb_scraper/isaweb_store.py tests/test_isaweb_store.py
git commit -m "feat: persist canonical isaweb datasets"
```

### Task 13: Persist publication schedules as structured release events

**Files:**
- Create: `scraper/oenb_scraper/release_calendar.py`
- Modify: `scraper/oenb_scraper/database.py`
- Test: `tests/test_release_calendar.py`

**Step 1: Write the failing test**

```python
def test_release_event_links_back_to_dataset_family():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_release_calendar.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Add parsing and persistence for release schedules, capturing:

- title
- scheduled date
- page URL
- dataset family or hierarchy reference
- language
- crawl timestamp

Release events should also feed revisit scheduling for the incremental crawler.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_release_calendar.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/release_calendar.py scraper/oenb_scraper/database.py tests/test_release_calendar.py
git commit -m "feat: store release events"
```

### Task 14: Add Shiny and external-app capture with provenance

**Files:**
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Create: `scraper/oenb_scraper/apps.py`
- Test: `tests/test_apps.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.apps import classify_app_url


def test_external_shiny_app_is_marked_secondary_scope():
    result = classify_app_url("https://example.shinyapps.io/oenb-dashboard")
    assert result.kind == "shiny_app"
    assert result.scope_class == "secondary"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_apps.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Persist app-specific metadata:

- host
- app type
- embed URL
- parent OeNB page
- externally hosted flag
- source attribution

Keep Shiny and other embedded apps in the corpus, but clearly distinguish them from native OeNB HTML pages.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_apps.py tests/test_spider.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/apps.py scraper/oenb_scraper/spiders/oenb_spider.py tests/test_apps.py
git commit -m "feat: track shiny and external data apps"
```

### Task 15: Add selective PDF processing instead of unconditional deep extraction

**Files:**
- Create: `scraper/oenb_scraper/pdf_priority.py`
- Modify: `scraper/oenb_scraper/pipelines.py`
- Test: `tests/test_pdf_priority.py`

**Step 1: Write the failing test**

```python
from oenb_scraper.pdf_priority import should_extract_pdf_text


def test_statistik_pdf_is_prioritized():
    item = {"url": "https://www.oenb.at/Statistik/report.pdf", "page_section": "Statistik"}
    assert should_extract_pdf_text(item) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_priority.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Create a scoring helper that prioritizes PDF extraction when the PDF is:

- inside statistics sections
- linked from methodology or explanatory-note pages
- table-heavy
- clearly relevant to chatbot knowledge quality

Non-priority PDFs remain inventoried with metadata but can skip expensive deep extraction.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_pdf_priority.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/pdf_priority.py scraper/oenb_scraper/pipelines.py tests/test_pdf_priority.py
git commit -m "feat: prioritize statistical pdf extraction"
```

### Task 16: Export a chatbot-ready knowledge-base snapshot

**Files:**
- Create: `analysis/export_knowledge_base.py`
- Modify: `analysis/export_parquet.py`
- Test: `tests/test_export_knowledge_base.py`

**Step 1: Write the failing test**

```python
def test_export_contains_page_documents_and_isaweb_datasets():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_knowledge_base.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Export separate datasets for downstream chatbot training and retrieval:

- page documents
- assets
- HTML tables
- dataset metadata
- ISAweb datasets
- ISAweb observations
- release events

Include provenance fields in every export row.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_knowledge_base.py tests/test_integration.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add analysis/export_knowledge_base.py analysis/export_parquet.py tests/test_export_knowledge_base.py
git commit -m "feat: export chatbot-ready knowledge base"
```

### Task 17: Add an end-to-end incremental-crawl integration test

**Files:**
- Create: `tests/test_incremental_crawl.py`
- Modify: `scraper/oenb_scraper/database.py`
- Modify: `scraper/oenb_scraper/frontier.py`

**Step 1: Write the failing test**

```python
def test_second_run_only_reprocesses_changed_page():
    # 1. store page version A
    # 2. simulate second crawl where one page is unchanged and one changed
    # 3. assert unchanged page skips extraction and changed page is requeued
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_incremental_crawl.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Cover the exact behavior you requested:

- the crawler must not re-read the entire site every run
- unchanged pages should stay in inventory and update freshness metadata only
- changed pages should invalidate derived artifacts and re-enter extraction
- newly discovered links should be added to the frontier

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_incremental_crawl.py tests/test_database.py tests/test_integration.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_incremental_crawl.py scraper/oenb_scraper/database.py scraper/oenb_scraper/frontier.py
git commit -m "test: verify incremental recrawl behavior"
```

### Task 18: Wire the new crawler entry points and preserve the old one as fallback

**Files:**
- Create: `scraper/oenb_scraper/spiders/oenb_site_spider.py`
- Modify: `scraper/oenb_scraper/spiders/oenb_spider.py`
- Modify: `run.sh`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
def test_new_site_spider_can_be_selected_from_cli():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Introduce a new primary spider, for example `oenb_site`, and keep the current spider as fallback until migration is complete.

CLI behavior should support:

- full crawl
- incremental crawl
- section-restricted crawl for debugging
- optional ISAweb harvest phase

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/spiders/oenb_site_spider.py scraper/oenb_scraper/spiders/oenb_spider.py run.sh tests/test_cli.py
git commit -m "feat: add new crawler entry point"
```

### Task 19: Verify the rebuilt pipeline end to end

**Files:**
- Modify: `tests/test_integration.py`
- Create: `tests/test_crawler_rebuild_integration.py`

**Step 1: Write the failing test**

```python
def test_rebuild_pipeline_produces_chatbot_ready_outputs():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crawler_rebuild_integration.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

Cover an end-to-end happy path:

- discover pages and resources
- normalize URLs
- persist frontier and versions
- extract one standardized-table bundle
- persist one ISAweb dataset and observations
- export chatbot-ready outputs

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crawler_rebuild_integration.py tests/test_incremental_crawl.py tests/test_export_knowledge_base.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_integration.py tests/test_crawler_rebuild_integration.py
git commit -m "test: verify crawler rebuild end to end"
```

## Implementation Notes

- The existing `pages`, `page_bodies` and `page_content` tables already provide a useful base for change-aware storage. Extend them instead of discarding them.
- The existing URL normalization in `pipelines.py` is a proven starting point and should be extracted, not rewritten ad hoc.
- The current spider’s broad detection logic for downloads, Shiny apps, ISAweb links and HTML tables is directionally useful. Keep the discovery behavior, replace the storage model.
- Incremental crawling should rely on both scheduling and change detection:
  - persistent frontier decides what to fetch
  - `etag` / `last_modified` / `body_hash` decide what to re-extract
- For ISAweb, discovery and extraction must stay separate:
  - discovery from links and pages
  - canonical data acquisition from `isadataservice/*`

## Verification Checklist

- Full OeNB pages are crawled without losing Shiny and embedded app surfaces.
- ISAweb links are deduplicated but keep all parent-page relations.
- Unchanged pages are not fully reprocessed on subsequent runs.
- Changed pages invalidate derived artifacts and get re-extracted.
- Standardized tables stay linked to explanations, schedules and chart/export surfaces.
- ISAweb datasets are keyed canonically, not by session URLs.
- Final export contains provenance and data-vintage fields suitable for chatbot answers.
