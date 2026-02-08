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
