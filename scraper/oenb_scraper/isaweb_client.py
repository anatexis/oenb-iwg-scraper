from __future__ import annotations

import logging
import time

import requests

from oenb_scraper.isaweb_resolver import parse_content_response
from oenb_scraper.isaweb_service import (
    BASE_URL,
    build_content_url,
    build_data_url,
    build_meta_url,
    parse_content_positions,
    parse_data_response,
    parse_meta_response,
)

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 0.5
TREE_REPORT_ID = "1.1"  # Any valid report ID returns the full hierarchy tree


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

    def fetch_hierarchy_tree(self, *, lang: str = "DE") -> list[dict]:
        """Fetch the full navigation tree and return leaf nodes."""
        url = f"{BASE_URL}/content?lang={lang}&report={TREE_REPORT_ID}"
        content = self._get(url)
        if content is None:
            return []

        parsed = parse_content_response(content)
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

    @property
    def stats(self) -> dict:
        return {"requests": self._request_count, "errors": self._error_count}
