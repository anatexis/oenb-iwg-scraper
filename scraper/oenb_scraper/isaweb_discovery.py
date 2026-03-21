from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

STATIC_ASSET_EXTENSIONS = (
    ".css", ".js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
)
ACTION_PATH_MARKERS = (
    "downloadresult",
    "exportchart",
    "defineparamsajax",
    "loaddefinition",
    "showmetadaten",
)
SESSION_ROOT_PATHS = {
    "/isawebstat/dynabfrage",
    "/isawebstat/stabfrage",
    "/dynabfrage",
    "/stabfrage",
}


@dataclass(frozen=True)
class IsawebUrlInfo:
    kind: str
    canonicalizable: bool


def classify_isaweb_url(url: str) -> IsawebUrlInfo | None:
    url_lower = urlparse(url).path.lower()
    canonical_path = url_lower.split(";", 1)[0].rstrip("/")

    if "/isawebstat/" not in url_lower and "/dynabfrage/" not in url_lower and "/isaweb/" not in url_lower:
        return None

    if canonical_path in SESSION_ROOT_PATHS:
        return None
    if url_lower.endswith(STATIC_ASSET_EXTENSIONS):
        return None
    if any(marker in url_lower for marker in ACTION_PATH_MARKERS):
        return None

    if "showresult" in url_lower:
        return IsawebUrlInfo(kind="show_result", canonicalizable=False)
    if "defineparams" in url_lower:
        return IsawebUrlInfo(kind="define_params", canonicalizable=False)
    if "createreport" in url_lower:
        return IsawebUrlInfo(kind="report", canonicalizable=True)
    if "createchart" in url_lower:
        return IsawebUrlInfo(kind="chart", canonicalizable=True)
    if "showrelease" in url_lower or "releasekalender" in url_lower:
        return IsawebUrlInfo(kind="release", canonicalizable=True)
    if "dynabfrage" in url_lower:
        return IsawebUrlInfo(kind="dynabfrage", canonicalizable=False)

    return IsawebUrlInfo(kind="landing", canonicalizable=True)
