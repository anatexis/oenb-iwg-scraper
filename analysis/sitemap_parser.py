"""Parse OeNB sitemap HTML to extract section structure."""

from pathlib import Path

from parsel import Selector


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
    selector = Selector(text=html_content)

    sections = []

    # Find all top-level navigation sections
    # These are identified by the class "navigation_link--first"
    first_level_links = selector.css("a.navigation_link--first")

    for link in first_level_links:
        section_name = link.css("::text").get(default="").strip()
        section_url = link.css("::attr(href)").get(default="")

        # Ensure URL is absolute
        if section_url and not section_url.startswith("https://"):
            section_url = f"https://www.oenb.at{section_url}"

        section_dict = {
            "name": section_name,
            "url": section_url,
        }

        # Find subsections (navigation_link--second) for this section
        # They are typically siblings in the navigation structure
        subsections = _find_subsections(link, selector)
        if subsections:
            section_dict["subsections"] = subsections

        sections.append(section_dict)

    return sections


def _find_subsections(parent_link: Selector, full_selector: Selector) -> list[dict]:
    """Find subsections for a given parent section link.

    Args:
        parent_link: The parsel Selector of the parent section link.
        full_selector: The full Selector object for context.

    Returns:
        List of subsection dicts with name and url.
    """
    subsections = []

    # Navigate up to find the navigation item container
    # We need to find the li.navigation_item that contains this link
    # Since parsel doesn't have find_parent, we use XPath ancestor axis
    nav_item = parent_link.xpath(
        "ancestor::li[contains(@class, 'navigation_item')]"
    )
    if not nav_item:
        return subsections

    # Find all second-level links within this navigation item
    second_level_links = nav_item.css("a.navigation_link--second")

    for link in second_level_links:
        subsection_name = link.css("::text").get(default="").strip()
        subsection_url = link.css("::attr(href)").get(default="")

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
