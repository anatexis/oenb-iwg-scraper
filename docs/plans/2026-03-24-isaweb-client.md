# ISAweb Webservice Client — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Proactively fetch all ISAweb statistical datasets via the REST API, filling gaps the HTML crawl misses (M3, Mindestreserve, TARGET2, etc.)

**Architecture:** Standalone HTTP client (`isaweb_client.py`, ~300 lines) that discovers all ISAweb hierarchies and positions via the REST API, then fetches metadata + time series for each position. Uses existing XML parsers (`isaweb_service.py`) and DB persistence (`isaweb_store.py`). No Scrapy dependency.

**Tech Stack:** `requests` for HTTP, existing `isaweb_service.py` parsers, existing `isaweb_store.py` persistence, `sqlite3` via `database.py`

---

## API Discovery (from live exploration 2026-03-24)

The ISAweb REST API at `https://www.oenb.at/isadataservice/` has two content response formats:

### 1. Navigation tree: `content?report=1.1&lang=DE`
Returns `<content>/<element>` nodes — the full hierarchy tree (38 elements). Each element has `id`, `parent`, `text`. Top-level categories: 1 (OeNB/Eurosystem), 2 (Zinssätze), 3 (Finanzinstitutionen), 4 (Wertpapiere), 6 (Preise), 7 (Wirtschaft), 8 (Finanzierungsrechnung), 9 (Außenwirtschaft). Already parsed by `isaweb_resolver.parse_content_response()`.

### 2. Positions list: `content?hierid=LEAF_ID&lang=DE`
Returns `<groups>/<group>/<position>` elements — each position has `id` (= the `pos` value for data/meta queries) and `<text>` (label). Only works for leaf hierids. Non-leaf hierids return empty groups.

### Discovery flow:
```
1. content?report=1.1&lang=DE  → navigation tree (38 elements)
2. Find leaf nodes (elements whose id is never a parent)
3. content?hierid=LEAF&lang=DE → positions [{id, text}] per leaf
4. For each position:
   a. meta?hierid=LEAF&lang=DE&pos=POS  → metadata + releases
   b. data?hierid=LEAF&lang=DE&pos=POS  → time series observations
5. Persist via existing store functions
```

**Extra leaf hierids not in tree:** 11 (Spezial — has positions directly), 14 sub-elements (100140001, 100140002 — found in tree as children of 14).

---

## Task 1: Add `parse_content_positions()` to `isaweb_service.py`

**Files:**
- Modify: `scraper/oenb_scraper/isaweb_service.py`
- Test: `tests/test_isaweb_service.py`

**Step 1: Write the failing test**

```python
# In tests/test_isaweb_service.py — add at top:
from oenb_scraper.isaweb_service import parse_content_positions

def test_parse_content_positions_extracts_positions_from_groups():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header>
        <prepared>2026-03-24T22:00:00Z</prepared>
        <sender id="AT2"><name>Oesterreichische Nationalbank</name></sender>
      </header>
      <groups>
        <group name="alle Daten">
          <position id="VDBESEFAZSPIFAGAB">
            <text lang="DE">Einlagefazilität</text>
          </position>
          <position id="VDBESSPITZEREFINZRNG">
            <text lang="DE">Spitzenrefinanzierungsfazilität</text>
          </position>
        </group>
      </groups>
    </content>
    """

    result = parse_content_positions(xml)

    assert result["prepared_at"] == "2026-03-24T22:00:00Z"
    assert len(result["positions"]) == 2
    assert result["positions"][0] == {"id": "VDBESEFAZSPIFAGAB", "text": "Einlagefazilität", "group": "alle Daten"}
    assert result["positions"][1] == {"id": "VDBESSPITZEREFINZRNG", "text": "Spitzenrefinanzierungsfazilität", "group": "alle Daten"}


def test_parse_content_positions_returns_empty_for_no_positions():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups><group name="alle Daten"></group></groups>
    </content>
    """

    result = parse_content_positions(xml)

    assert result["positions"] == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_service.py::test_parse_content_positions_extracts_positions_from_groups -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `scraper/oenb_scraper/isaweb_service.py`:

```python
def parse_content_positions(xml_text: str | bytes) -> dict:
    """Parse an ISAweb content response into a list of available positions.

    The content endpoint returns positions when called with a leaf hierid:
    /isadataservice/content?hierid=LEAF_ID&lang=DE
    """
    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    positions: list[dict] = []

    for group in root.findall(".//group"):
        group_name = group.get("name")
        for position in group.findall("./position"):
            pos_id = position.get("id")
            text = _normalized_text(position.findtext("./text"))
            if pos_id and text:
                positions.append({"id": pos_id, "text": text, "group": group_name})

    return {
        "prepared_at": _normalized_text(root.findtext("./header/prepared")),
        "positions": positions,
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_isaweb_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_service.py tests/test_isaweb_service.py
git commit -m "feat: add parse_content_positions() for ISAweb position discovery"
```

---

## Task 2: Build `IsawebClient` core — session, rate limiting, fetch helpers

**Files:**
- Create: `scraper/oenb_scraper/isaweb_client.py`
- Create: `tests/test_isaweb_client.py`

**Step 1: Write the failing tests**

```python
# tests/test_isaweb_client.py
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_client import IsawebClient


def test_client_fetch_positions_parses_content_response():
    """Client fetches content?hierid=X and returns parsed positions."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups>
        <group name="alle Daten">
          <position id="VDBESEFAZSPIFAGAB">
            <text lang="DE">Einlagefazilität</text>
          </position>
        </group>
      </groups>
    </content>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = xml.encode("utf-8")

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response) as mock_get:
        positions = client.fetch_positions(hierid=22, lang="DE")

    mock_get.assert_called_once()
    assert "hierid=22" in mock_get.call_args[0][0]
    assert len(positions) == 1
    assert positions[0]["id"] == "VDBESEFAZSPIFAGAB"


def test_client_fetch_positions_returns_empty_on_http_error():
    """Client returns empty list on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(side_effect=Exception("Server error"))

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response):
        positions = client.fetch_positions(hierid=99, lang="DE")

    assert positions == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_client.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# scraper/oenb_scraper/isaweb_client.py
from __future__ import annotations

import logging
import time

import requests

from oenb_scraper.isaweb_service import (
    build_content_url,
    build_data_url,
    build_meta_url,
    parse_content_positions,
    parse_data_response,
    parse_meta_response,
)

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 0.5  # seconds between requests


class IsawebClient:
    """Standalone HTTP client for the OeNB ISAweb REST API."""

    def __init__(self, *, rate_limit: float = DEFAULT_RATE_LIMIT):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "oenb-crawler/1.0 (statistics research)"
        self._rate_limit = rate_limit
        self._last_request_time = 0.0
        self._request_count = 0
        self._error_count = 0

    def _get(self, url: str) -> bytes | None:
        """Fetch a URL with rate limiting. Returns response bytes or None on error."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)

        self._last_request_time = time.monotonic()
        self._request_count += 1
        try:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception:
            self._error_count += 1
            logger.warning("Failed to fetch %s", url, exc_info=True)
            return None

    def fetch_positions(self, *, hierid: int, lang: str = "DE") -> list[dict]:
        """Fetch available positions for a leaf hierarchy node."""
        url = build_content_url(hierid=hierid, lang=lang)
        content = self._get(url)
        if content is None:
            return []
        result = parse_content_positions(content)
        return result["positions"]

    @property
    def stats(self) -> dict:
        return {"requests": self._request_count, "errors": self._error_count}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_isaweb_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_client.py tests/test_isaweb_client.py
git commit -m "feat: add IsawebClient core with session and rate limiting"
```

---

## Task 3: Add hierarchy tree discovery to `IsawebClient`

**Files:**
- Modify: `scraper/oenb_scraper/isaweb_client.py`
- Modify: `tests/test_isaweb_client.py`

**Step 1: Write the failing test**

```python
def test_client_discover_leaf_hierids_from_tree():
    """Client fetches navigation tree, identifies leaf nodes."""
    tree_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <content>
        <element id="1" parent="0"><text lang="DE">OeNB</text></element>
        <element id="11" parent="1"><text lang="DE">Bilanzpositionen</text></element>
        <element id="13" parent="1"><text lang="DE">Geldmengenaggregate</text></element>
        <element id="2" parent="0"><text lang="DE">Zinssätze</text></element>
        <element id="22" parent="2"><text lang="DE">Geldmarktzinssätze</text></element>
      </content>
    </content>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = tree_xml.encode("utf-8")

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response):
        leaves = client.fetch_hierarchy_tree(lang="DE")

    # Leaves are elements whose id never appears as a parent
    # 11 (parent=1, not a parent), 13 (parent=1, not a parent), 22 (parent=2, not a parent)
    # 1 is parent of 11,13; 2 is parent of 22 — not leaves
    assert sorted(leaves) == [
        {"hierid": 11, "label": "Bilanzpositionen"},
        {"hierid": 13, "label": "Geldmengenaggregate"},
        {"hierid": 22, "label": "Geldmarktzinssätze"},
    ]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_client.py::test_client_discover_leaf_hierids_from_tree -v`
Expected: FAIL — `fetch_hierarchy_tree` not defined

**Step 3: Write implementation**

Add to `isaweb_client.py`:

```python
from oenb_scraper.isaweb_resolver import parse_content_response

# At the module level:
TREE_REPORT_ID = "1.1"  # Any valid report ID returns the full tree


class IsawebClient:
    # ... existing methods ...

    def fetch_hierarchy_tree(self, *, lang: str = "DE") -> list[dict]:
        """Fetch the full navigation tree and return leaf nodes."""
        url = build_content_url(hierid=1, lang=lang) + f"&report={TREE_REPORT_ID}"
        # Note: build_content_url produces hierid=X&lang=Y. We append report
        # because content?report=1.1 is what returns the full tree.
        # Actually, the URL should be built manually for the tree endpoint.
        content = self._get(f"{BASE_URL}/content?lang={lang}&report={TREE_REPORT_ID}")
        if content is None:
            return []

        parsed = parse_content_response(content)
        elements = parsed.get("elements", [])
        parent_ids = {el["parent"] for el in elements}
        leaves = [
            {"hierid": el["id"], "label": el["text"]}
            for el in elements
            if el["id"] not in parent_ids
        ]
        return sorted(leaves, key=lambda x: x["hierid"])
```

Also add import: `from oenb_scraper.isaweb_service import BASE_URL`

**Step 4: Run tests**

Run: `pytest tests/test_isaweb_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_client.py tests/test_isaweb_client.py
git commit -m "feat: add hierarchy tree discovery to IsawebClient"
```

---

## Task 4: Add meta + data fetching and persistence

**Files:**
- Modify: `scraper/oenb_scraper/isaweb_client.py`
- Modify: `tests/test_isaweb_client.py`

**Step 1: Write the failing test**

```python
def test_client_fetch_and_store_position(tmp_path):
    """Client fetches meta + data for a position and persists to DB."""
    from oenb_scraper.database import init_db

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <metainfo>
      <header><prepared>2026-03-24T10:00:00Z</prepared>
        <sender id="AT2"><name>OeNB</name></sender>
      </header>
      <meta>
        <title>Einlagefazilität</title>
        <region>-</region><unit>%</unit><comment>ECB rate</comment>
        <classification>-</classification><breaks>-</breaks>
        <frequency>Monate</frequency>
        <data_available><data>Jan. 99 - Feb. 26</data></data_available>
        <last_update>2026-03-01</last_update><source>OeNB</source><lag>-</lag>
        <releases></releases>
      </meta>
    </metainfo>
    """

    data_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <OeNBData>
      <data>
        <dataSet pos="VDBESEFAZSPIFAGAB" posTitle="Einlagefazilität" freq="M" unitMult="0" unitText="%">
          <values>
            <obs value="2.50" periode="2025-01"/>
            <obs value="2.75" periode="2025-02"/>
          </values>
        </dataSet>
      </data>
    </OeNBData>
    """

    def mock_get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "/meta?" in url:
            resp.content = meta_xml.encode("utf-8")
        else:
            resp.content = data_xml.encode("utf-8")
        return resp

    conn = init_db(tmp_path / "crawler.db")
    client = IsawebClient(rate_limit=0)

    with patch.object(client._session, "get", side_effect=mock_get_side_effect):
        result = client.fetch_and_store_position(
            conn=conn, hierid=22, pos="VDBESEFAZSPIFAGAB", lang="DE"
        )

    assert result["meta_stored"] is True
    assert result["data_stored"] == 1

    # Verify DB
    meta_row = conn.execute("SELECT title FROM isaweb_metadata WHERE pos = 'VDBESEFAZSPIFAGAB'").fetchone()
    obs_count = conn.execute("SELECT COUNT(*) AS c FROM isaweb_observations").fetchone()["c"]
    assert meta_row["title"] == "Einlagefazilität"
    assert obs_count == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_client.py::test_client_fetch_and_store_position -v`
Expected: FAIL — `fetch_and_store_position` not defined

**Step 3: Write implementation**

Add to `IsawebClient`:

```python
import sqlite3
from oenb_scraper.isaweb_store import store_isaweb_data_response, store_isaweb_meta_response


class IsawebClient:
    # ... existing ...

    def fetch_and_store_position(
        self,
        *,
        conn: sqlite3.Connection,
        hierid: int,
        pos: str,
        lang: str = "DE",
    ) -> dict:
        """Fetch metadata + data for one position and persist to DB."""
        result = {"meta_stored": False, "data_stored": 0}

        # Fetch and store metadata
        meta_url = build_meta_url(hierid=hierid, lang=lang, pos=[pos])
        meta_content = self._get(meta_url)
        if meta_content is not None:
            try:
                store_isaweb_meta_response(conn, response_url=meta_url, xml_text=meta_content)
                result["meta_stored"] = True
            except Exception:
                logger.warning("Failed to store meta for hierid=%d pos=%s", hierid, pos, exc_info=True)

        # Fetch and store data
        data_url = build_data_url(hierid=hierid, lang=lang, pos=[pos])
        data_content = self._get(data_url)
        if data_content is not None:
            try:
                result["data_stored"] = store_isaweb_data_response(
                    conn, response_url=data_url, xml_text=data_content
                )
            except Exception:
                logger.warning("Failed to store data for hierid=%d pos=%s", hierid, pos, exc_info=True)

        return result
```

**Step 4: Run tests**

Run: `pytest tests/test_isaweb_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_client.py tests/test_isaweb_client.py
git commit -m "feat: add meta+data fetching and DB persistence to IsawebClient"
```

---

## Task 5: Add `fetch_all()` orchestration + CLI

**Files:**
- Modify: `scraper/oenb_scraper/isaweb_client.py`
- Modify: `tests/test_isaweb_client.py`

**Step 1: Write the failing test**

```python
def test_client_fetch_all_discovers_and_fetches_positions(tmp_path):
    """Full orchestration: tree → leaf positions → meta+data → DB."""
    from oenb_scraper.database import init_db

    tree_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <content>
        <element id="2" parent="0"><text lang="DE">Zinssätze</text></element>
        <element id="22" parent="2"><text lang="DE">Geldmarktzinssätze</text></element>
      </content>
    </content>
    """

    positions_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups>
        <group name="alle Daten">
          <position id="POS1"><text lang="DE">Position 1</text></position>
        </group>
      </groups>
    </content>
    """

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <metainfo>
      <header><prepared>2026-03-24T10:00:00Z</prepared>
        <sender id="AT2"><name>OeNB</name></sender>
      </header>
      <meta>
        <title>Position 1</title><region>-</region><unit>%</unit>
        <comment>-</comment><classification>-</classification>
        <breaks>-</breaks><frequency>Monate</frequency>
        <data_available></data_available>
        <last_update>2026-03-01</last_update><source>OeNB</source><lag>-</lag>
        <releases></releases>
      </meta>
    </metainfo>
    """

    data_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <OeNBData>
      <data>
        <dataSet pos="POS1" posTitle="Position 1" freq="M" unitMult="0" unitText="%">
          <values><obs value="1.0" periode="2025-01"/></values>
        </dataSet>
      </data>
    </OeNBData>
    """

    call_count = {"n": 0}

    def mock_get(url, **kwargs):
        call_count["n"] += 1
        resp = MagicMock()
        resp.status_code = 200
        if "/content?" in url and "report=" in url:
            resp.content = tree_xml.encode()
        elif "/content?" in url:
            resp.content = positions_xml.encode()
        elif "/meta?" in url:
            resp.content = meta_xml.encode()
        else:
            resp.content = data_xml.encode()
        return resp

    conn = init_db(tmp_path / "crawler.db")
    client = IsawebClient(rate_limit=0)

    with patch.object(client._session, "get", side_effect=mock_get):
        report = client.fetch_all(conn=conn, lang="DE")

    assert report["hierarchies_discovered"] >= 1
    assert report["positions_discovered"] >= 1
    assert report["positions_fetched"] >= 1

    dataset_count = conn.execute("SELECT COUNT(*) AS c FROM isaweb_datasets").fetchone()["c"]
    assert dataset_count >= 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_isaweb_client.py::test_client_fetch_all_discovers_and_fetches_positions -v`
Expected: FAIL

**Step 3: Write implementation**

Add to `IsawebClient`:

```python
# Extra leaf hierids not present in the navigation tree
EXTRA_LEAF_HIERIDS = [11]


class IsawebClient:
    # ... existing ...

    def fetch_all(
        self,
        *,
        conn: sqlite3.Connection,
        lang: str = "DE",
    ) -> dict:
        """Discover all hierarchies and fetch all positions."""
        report = {
            "hierarchies_discovered": 0,
            "positions_discovered": 0,
            "positions_fetched": 0,
            "errors": 0,
        }

        # Step 1: Get the hierarchy tree
        leaves = self.fetch_hierarchy_tree(lang=lang)
        leaf_hierids = [leaf["hierid"] for leaf in leaves]

        # Add known extra leaves not in tree
        for extra in EXTRA_LEAF_HIERIDS:
            if extra not in leaf_hierids:
                leaf_hierids.append(extra)

        report["hierarchies_discovered"] = len(leaf_hierids)
        logger.info("Discovered %d leaf hierarchies", len(leaf_hierids))

        # Step 2: For each leaf, discover positions
        for hierid in leaf_hierids:
            positions = self.fetch_positions(hierid=hierid, lang=lang)
            report["positions_discovered"] += len(positions)
            logger.info("hierid=%d: %d positions", hierid, len(positions))

            # Step 3: Fetch meta+data for each position
            for pos_info in positions:
                pos_id = pos_info["id"]
                result = self.fetch_and_store_position(
                    conn=conn, hierid=hierid, pos=pos_id, lang=lang
                )
                if result["meta_stored"] or result["data_stored"] > 0:
                    report["positions_fetched"] += 1
                else:
                    report["errors"] += 1

        logger.info(
            "Done: %d hierarchies, %d positions discovered, %d fetched, %d errors",
            report["hierarchies_discovered"],
            report["positions_discovered"],
            report["positions_fetched"],
            report["errors"],
        )
        return report
```

Add `if __name__ == "__main__"` CLI block at the bottom:

```python
if __name__ == "__main__":
    import argparse
    from oenb_scraper.database import init_db

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Fetch all ISAweb datasets")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--lang", default="DE", help="Language (DE or EN)")
    parser.add_argument("--rate-limit", type=float, default=0.5, help="Seconds between requests")
    args = parser.parse_args()

    conn = init_db(args.db)
    client = IsawebClient(rate_limit=args.rate_limit)
    report = client.fetch_all(conn=conn, lang=args.lang)

    print(f"\nResults:")
    print(f"  Hierarchies: {report['hierarchies_discovered']}")
    print(f"  Positions discovered: {report['positions_discovered']}")
    print(f"  Positions fetched: {report['positions_fetched']}")
    print(f"  Errors: {report['errors']}")
```

**Step 4: Run tests**

Run: `pytest tests/test_isaweb_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add scraper/oenb_scraper/isaweb_client.py tests/test_isaweb_client.py
git commit -m "feat: add fetch_all() orchestration and CLI to ISAweb client"
```

---

## Task 6: Smoke test against live API

**NOT a unit test** — manual verification.

**Step 1: Run against a single hierarchy to verify**

```bash
cd .worktrees/feature-isaweb-client
python -m oenb_scraper.isaweb_client --db /tmp/isaweb_test.db --lang DE --rate-limit 1.0
```

**Step 2: Check results**

```bash
sqlite3 /tmp/isaweb_test.db "SELECT COUNT(*) FROM isaweb_datasets"
sqlite3 /tmp/isaweb_test.db "SELECT COUNT(*) FROM isaweb_observations"
sqlite3 /tmp/isaweb_test.db "SELECT COUNT(*) FROM isaweb_metadata"
sqlite3 /tmp/isaweb_test.db "SELECT DISTINCT hierid FROM isaweb_datasets ORDER BY hierid"
```

**Step 3: Verify the 6 missing eval cases are now covered**

```bash
sqlite3 /tmp/isaweb_test.db "SELECT title FROM isaweb_metadata WHERE title LIKE '%M3%' OR title LIKE '%Geldmenge%' OR title LIKE '%Mindestreserve%' OR title LIKE '%TARGET%' OR title LIKE '%Zahlungsverkehr%' OR title LIKE '%Einlagensicherung%'"
```

**Step 4: If all good, run against the production database**

```bash
python -m oenb_scraper.isaweb_client --db data/statistics_production/crawler.db --lang DE
```

**Step 5: Commit final state**

```bash
git add -A
git commit -m "feat: ISAweb Webservice Client complete — full hierarchy discovery"
```

---

## Task 7: Add `requests` to requirements.txt

**Files:**
- Modify: `requirements.txt`

**Step 1:** Check if `requests` is already in requirements.txt

**Step 2:** If not, add it

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requests to requirements.txt"
```

**Note:** Do this in Task 2 when first creating `isaweb_client.py`, before running its tests.
