"""Parse OeNB sitemap HTML to extract section structure."""

from pathlib import Path

from bs4 import BeautifulSoup


def parse_sitemap_html(html_path: str) -> list[dict]:
    """Parse OeNB sitemap HTML and extract sections.

    Args:
        html_path: Path to the OeNB sitemap HTML file.

    Returns:
        List of dicts with:
        - name: Section name (e.g., "Statistik")
        - url: Full URL to section
        - subsections: List of subsection dicts (optional)
    """
    path = Path(html_path)
    html_content = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_content, "html.parser")

    sections = []

    # Find all top-level navigation sections
    # These are identified by the class "navigation_link--first"
    first_level_links = soup.find_all("a", class_="navigation_link--first")

    for link in first_level_links:
        section_name = link.get_text(strip=True)
        section_url = link.get("href", "")

        # Ensure URL is absolute
        if section_url and not section_url.startswith("https://"):
            section_url = f"https://www.oenb.at{section_url}"

        section_dict = {
            "name": section_name,
            "url": section_url,
        }

        # Find subsections (navigation_link--second) for this section
        # They are typically siblings in the navigation structure
        subsections = _find_subsections(link, soup)
        if subsections:
            section_dict["subsections"] = subsections

        sections.append(section_dict)

    return sections


def _find_subsections(parent_link, soup: BeautifulSoup) -> list[dict]:
    """Find subsections for a given parent section link.

    Args:
        parent_link: The BeautifulSoup tag of the parent section link.
        soup: The full BeautifulSoup object for context.

    Returns:
        List of subsection dicts with name and url.
    """
    subsections = []

    # Get the parent container
    parent_container = parent_link.find_parent("div", class_="navigation_toggle-container--first")
    if not parent_container:
        return subsections

    # Find the navigation item that contains this section
    nav_item = parent_container.find_parent("li", class_="navigation_item")
    if not nav_item:
        return subsections

    # Find all second-level links within this navigation item
    second_level_links = nav_item.find_all("a", class_="navigation_link--second")

    for link in second_level_links:
        subsection_name = link.get_text(strip=True)
        subsection_url = link.get("href", "")

        # Ensure URL is absolute
        if subsection_url and not subsection_url.startswith("https://"):
            subsection_url = f"https://www.oenb.at{subsection_url}"

        subsections.append({
            "name": subsection_name,
            "url": subsection_url,
        })

    return subsections


def get_default_sitemap_path() -> Path:
    """Return path to bundled sitemap HTML.

    Returns:
        Path object pointing to the bundled sitemap HTML file.
    """
    return (
        Path(__file__).parent.parent
        / "scraper"
        / "sitemap"
        / "Sitemap - Oesterreichische Nationalbank (OeNB).html"
    )
