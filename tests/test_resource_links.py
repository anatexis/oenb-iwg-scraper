import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.database import init_db, list_resource_links_for_target, store_resource_link


def test_store_resource_link_persists_parent_context(tmp_path: Path):
    conn = init_db(tmp_path / "crawler.db")

    store_resource_link(
        conn,
        source_url="https://www.oenb.at/Statistik/start.html",
        target_url="https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11",
        normalized_target_url="https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11",
        link_text="Leitzins",
        section_heading="Zinssätze",
        resource_kind="isaweb_entry",
        embed_type="a",
        discovered_at="2026-03-19T10:00:00Z",
    )

    rows = list_resource_links_for_target(
        conn,
        "https://www.oenb.at/isawebstat/dynabfrage/showResult?hierarchieId=11",
    )

    assert rows[0]["source_url"] == "https://www.oenb.at/Statistik/start.html"
    assert rows[0]["link_text"] == "Leitzins"
    assert rows[0]["section_heading"] == "Zinssätze"
