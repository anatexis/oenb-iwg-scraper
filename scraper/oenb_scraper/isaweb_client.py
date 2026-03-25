from __future__ import annotations

import logging
import sqlite3
import time

import requests

from oenb_scraper.isaweb_resolver import parse_content_response
from oenb_scraper.isaweb_service import (
    BASE_URL,
    build_content_url,
    build_data_url,
    build_meta_url,
    parse_content_positions,
)
from oenb_scraper.isaweb_store import (
    store_isaweb_data_response,
    store_isaweb_meta_response,
)

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 0.5
TREE_REPORT_ID = "1.1"  # Any valid report ID returns the full hierarchy tree
EXTRA_LEAF_HIERIDS = [11]  # Leaf hierids not present in the navigation tree


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
        try:
            result = parse_content_positions(content)
            return result["positions"]
        except Exception:
            logger.warning("Failed to parse positions for hierid=%d", hierid, exc_info=True)
            return []

    def fetch_hierarchy_tree(self, *, lang: str = "DE") -> list[dict]:
        """Fetch the full navigation tree and return leaf nodes."""
        url = f"{BASE_URL}/content?lang={lang}&report={TREE_REPORT_ID}"
        content = self._get(url)
        if content is None:
            return []

        try:
            parsed = parse_content_response(content)
        except Exception:
            logger.warning("Failed to parse hierarchy tree", exc_info=True)
            return []

        elements = parsed.get("elements", [])
        parent_ids = {el["parent"] for el in elements}
        return sorted(
            [
                {"hierid": el["id"], "label": el["text"]}
                for el in elements
                if el["id"] not in parent_ids
            ],
            key=lambda x: x["hierid"],
        )

    def fetch_and_store_position(
        self,
        *,
        conn: sqlite3.Connection,
        hierid: int,
        pos: str,
        lang: str = "DE",
    ) -> dict:
        """Fetch metadata + data for one position and persist to DB."""
        result: dict = {"meta_stored": False, "data_stored": 0}

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

    @property
    def stats(self) -> dict:
        return {"requests": self._request_count, "errors": self._error_count}


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
    try:
        client = IsawebClient(rate_limit=args.rate_limit)
        report = client.fetch_all(conn=conn, lang=args.lang)

        print(f"\nResults:")
        print(f"  Hierarchies: {report['hierarchies_discovered']}")
        print(f"  Positions discovered: {report['positions_discovered']}")
        print(f"  Positions fetched: {report['positions_fetched']}")
        print(f"  Errors: {report['errors']}")
        print(f"  HTTP requests: {client.stats['requests']}")
    finally:
        conn.close()
