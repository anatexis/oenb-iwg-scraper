"""Extract clean text from HTML pages."""
from bs4 import BeautifulSoup
import re


def extract_text_from_html(html: str) -> dict:
    """Extract title and clean text from HTML.

    Returns:
        {"title": str, "text": str}
    """
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    return {"title": title, "text": text}
