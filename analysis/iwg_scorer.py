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
    "catalog": 35,  # Standardized data catalog pages
    "portal": 30,   # Interactive data portals
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

    # Special item type bonuses
    item_type = item.get("type")
    if item_type == "shiny_app":
        score += 30
        factors.append(("Shiny App (visualisierte Daten)", 30))
    elif item_type == "standardized_tables":
        score += 35
        factors.append(("Datenkatalog (strukturierte Daten)", 35))
    elif item_type == "interactive_data":
        score += 30
        factors.append(("Interaktives Datenportal", 30))

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
