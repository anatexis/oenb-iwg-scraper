"""Extract clean text from HTML pages.

NOTE: After re-extraction, check if analysis/chart_synonyms.json needs
updating with new chart titles. That file is NOT auto-generated.
"""
import sqlite3
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import re

try:
    from analysis.extract_chart_data import extract_chart_data, chart_data_to_text
except ModuleNotFoundError:
    from extract_chart_data import extract_chart_data, chart_data_to_text


def extract_text_from_html(html: str) -> dict:
    """Extract title and clean text from HTML.

    For isawebstat chart pages, also extracts embedded time-series data
    from <script> tags before they are removed.

    Returns:
        {"title": str, "text": str}
    """
    # Extract chart data BEFORE stripping scripts
    chart_data = extract_chart_data(html)
    chart_text = chart_data_to_text(chart_data) if chart_data else ""

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    # Append chart data if present
    if chart_text:
        text = f"{text}\n\n{chart_text}"

    return {"title": title, "text": text}


def get_section_from_url(url: str) -> str:
    """Extract section from URL path."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0].lower() == "en":
        parts = parts[1:]
    return parts[0] if parts else "Startseite"


def get_language_from_url(url: str) -> str:
    """Extract language from URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    return "en" if parts and parts[0].lower() == "en" else "de"


def run_extraction(db_path: Path, extractor_version: str = "v1") -> int:
    """Extract text from all pages without content. Returns count."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT p.id, p.url, pb.body_blob, pb.compression
        FROM pages p
        JOIN page_bodies pb ON pb.page_id = p.id
        LEFT JOIN page_content pc ON pc.page_id = p.id
        WHERE pc.page_id IS NULL AND p.content_type LIKE '%html%'
    """)

    count = 0
    for row in cursor:
        body = row["body_blob"]
        if row["compression"] == "gzip":
            body = gzip.decompress(body)

        html = body.decode("utf-8", errors="ignore")
        result = extract_text_from_html(html)

        conn.execute(
            """INSERT INTO page_content
               (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], result["title"], result["text"],
             get_section_from_url(row["url"]), get_language_from_url(row["url"]),
             datetime.utcnow().isoformat() + "Z", extractor_version)
        )
        count += 1

    conn.commit()
    conn.close()
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract text from crawled pages")
    parser.add_argument("db_path", type=Path, help="Path to SQLite database")
    parser.add_argument("--version", default="v1", help="Extractor version tag")
    args = parser.parse_args()

    count = run_extraction(args.db_path, args.version)
    print(f"Extracted text from {count} pages")