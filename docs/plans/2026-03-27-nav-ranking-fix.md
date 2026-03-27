# Navigation & Ranking Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the chatbot's ~15% eval score by rebalancing ranking for NAV/explanation queries, adding section navigation records, and relaxing the grounding gate for navigation intent.

**Architecture:** Three surgical changes to the existing RAG pipeline: (1) intent-aware scoring adjustments in `_query_intent_record_boost`, (2) auto-generated section navigation KB records from the crawl DB, (3) grounding gate bypass for page_document/section_navigation on navigation intent.

**Tech Stack:** Python, SQLite, existing KB export + retrieval pipeline

---

### Task 1: Ranking rebalance — boost page_document for NAV/explanation intents

**Files:**
- Modify: `analysis/query_knowledge_base.py:272-300` (`_query_intent_record_boost`)
- Test: `tests/test_query_knowledge_base.py`

**Step 1: Write failing tests**

```python
def test_navigation_intent_boosts_page_document():
    routed = {"query_intent": "navigation"}
    record_page = {"parent_record_type": "page_document"}
    record_family = {"parent_record_type": "dataset_family"}
    record_secnav = {"parent_record_type": "section_navigation"}

    page_boost = _query_intent_record_boost(routed, record_page, title="statistik", text="", primary_url="", source_preference="secondary")
    family_boost = _query_intent_record_boost(routed, record_family, title="statistik", text="", primary_url="", source_preference="primary")
    secnav_boost = _query_intent_record_boost(routed, record_secnav, title="statistik", text="", primary_url="", source_preference="primary")

    assert page_boost >= 400
    assert family_boost < 0
    assert secnav_boost >= 500


def test_explanation_intent_boosts_page_document():
    routed = {"query_intent": "explanation"}
    record_page = {"parent_record_type": "page_document"}
    record_family = {"parent_record_type": "dataset_family"}

    page_boost = _query_intent_record_boost(routed, record_page, title="zahlungsbilanz", text="", primary_url="", source_preference="secondary")
    family_boost = _query_intent_record_boost(routed, record_family, title="services trade", text="", primary_url="", source_preference="primary")

    assert page_boost >= 300
    assert family_boost < 0
```

**Step 2: Implement the boost changes**

In `_query_intent_record_boost`, add after the existing `navigation` block:

```python
    if query_intent == "navigation":
        # ... existing download-term boosts ...
        # Boost page_document and section_navigation for navigation queries
        if parent_record_type == "page_document" and not is_page_in_primary_kb:
            boost += 500
        if parent_record_type == "section_navigation":
            boost += 600
        if parent_record_type == "dataset_family":
            boost -= 200
    if query_intent == "explanation":
        if parent_record_type == "page_document" and not is_page_in_primary_kb:
            boost += 400
        if parent_record_type == "section_navigation":
            boost += 400
        if parent_record_type == "dataset_family":
            boost -= 300
```

**Step 3: Run tests, commit**

---

### Task 2: Grounding gate — auto-accept page_document for navigation intent

**Files:**
- Modify: `analysis/chatbot_answering.py:202-238` (`_is_grounded_top_hit`)
- Test: `tests/test_chatbot_answering.py`

**Step 1: Write failing test**

```python
def test_grounded_nav_intent_accepts_page_document():
    routing = {"query_intent": "navigation", "strategy": "rag_first",
               "domains": ["website_general"], "confidence": 0.25}
    hit = {"parent_record_type": "page_document", "title": "Statistik", "text": "Datenangebot"}
    assert _is_grounded_top_hit("wo finde ich statistik", routing, hit) is True


def test_grounded_nav_intent_accepts_section_navigation():
    routing = {"query_intent": "navigation", "strategy": "rag_first",
               "domains": ["website_general"], "confidence": 0.25}
    hit = {"parent_record_type": "section_navigation", "title": "Bereich: Statistik", "text": "..."}
    assert _is_grounded_top_hit("wo finde ich statistik", routing, hit) is True
```

**Step 2: Implement**

In `_is_grounded_top_hit`, after the `dataset_family` auto-accept (line 210), add:

```python
    if hit.get("parent_record_type") == "dataset_family":
        return True
    # Auto-accept page/section_navigation for navigation intent
    if routing.get("query_intent") == "navigation" and hit.get("parent_record_type") in ("page_document", "section_navigation"):
        return True
```

**Step 3: Run tests, commit**

---

### Task 3: Section navigation records — generate from crawl DB

**Files:**
- Modify: `analysis/export_knowledge_base_jsonl.py` (add `_section_navigation_records`)
- Test: `tests/test_export_knowledge_base_jsonl.py`

**Step 1: Write test**

```python
def test_section_navigation_records_from_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, url TEXT, ...)")
    conn.execute("CREATE TABLE page_content (page_id INTEGER, title TEXT, page_section TEXT, ...)")
    # Insert sample pages for "Statistik" section
    conn.execute("INSERT INTO pages VALUES (1, 'https://www.oenb.at/Statistik/Standardisierte-Tabellen.html', ...)")
    conn.execute("INSERT INTO page_content VALUES (1, 'Datenangebot', 'Statistik', ...)")
    # ... more pages
    conn.commit()
    records = _section_navigation_records(conn)
    assert len(records) >= 1
    stat_rec = [r for r in records if "Statistik" in r["title"]]
    assert len(stat_rec) == 1
    assert stat_rec[0]["parent_record_type"] == "section_navigation"
    assert "datenangebot" in stat_rec[0]["text"].lower()
```

**Step 2: Implement `_section_navigation_records(conn)`**

Query `page_content` grouped by `page_section`. For each section with >= 3 pages:
1. Get all pages sorted by URL depth (shallowest first)
2. Build section hierarchy from URL paths
3. Generate text: section name + sub-sections + page titles
4. Return chatbot_chunk with parent_record_type "section_navigation", retrieval_score 200

**Step 3: Wire into `export_knowledge_base_jsonl()`**

Add after `_page_chatbot_chunk_records`:
```python
        for r in _section_navigation_records(conn):
            _write(r)
```

**Step 4: Run tests, commit**

---

### Task 4: Re-export KB, run eval

**Step 1:** Re-export the statistics KB:
```bash
PYTHONPATH=scraper python -m analysis.export_knowledge_base_jsonl data/statistics_production/pages.db data/statistics_production/knowledge_base_active.jsonl
```

**Step 2:** Re-export the full_site KB:
```bash
PYTHONPATH=scraper python -m analysis.export_knowledge_base_jsonl data/full_site_production/pages.db data/full_site_production/knowledge_base_active.jsonl
```

**Step 3:** Run 60-case eval:
```bash
PYTHONPATH=scraper python -m analysis.run_chatbot_eval tests/fixtures/chatbot_eval_v2.json data/statistics_production/eval_v2_report_post_fix.json --base-dir . --debug
```
