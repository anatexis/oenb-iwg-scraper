"""Bounded ISAweb live lookup helpers."""

from __future__ import annotations

from urllib.parse import urlparse


def is_allowed_live_lookup_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc != "www.oenb.at":
        return False
    return parsed.path.startswith("/isadataservice/") or parsed.path.startswith("/isawebstat/")


def default_live_lookup(query: str, hits: list[dict], routing: dict) -> dict | None:
    """Placeholder for future bounded live ISAweb lookups."""

    return None
