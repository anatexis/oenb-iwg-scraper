"""Generate HTML dashboard from scraped data."""

import json
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from analysis.iwg_scorer import enrich_items_with_scores


def load_data(json_path: str) -> list[dict]:
    """Load scraped data from JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_dashboard(items: list[dict], output_path: str) -> None:
    """Generate HTML dashboard from items."""
    # Enrich with IWG scores
    enriched = enrich_items_with_scores(items)

    # Sort by score descending
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    # Calculate statistics
    total_count = len(enriched)
    high_count = sum(1 for i in enriched if i["iwg_confidence"] == "high")
    medium_count = sum(1 for i in enriched if i["iwg_confidence"] == "medium")
    low_count = sum(1 for i in enriched if i["iwg_confidence"] == "low")

    # File type stats
    file_type_stats = Counter(i["file_type"] for i in enriched)

    # Unique values for filters
    file_types = sorted(set(i["file_type"] for i in enriched))
    sections = sorted(set(i["page_section"] for i in enriched if i["page_section"]))

    # Setup Jinja2
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))

    # Add truncate filter
    def truncate(s, length=50):
        s = str(s) if s else ""
        return s[:length] + "..." if len(s) > length else s
    env.filters["truncate"] = truncate

    template = env.get_template("dashboard.html")

    # Render
    html = template.render(
        items=enriched,
        items_json=json.dumps(enriched, ensure_ascii=False),
        total_count=total_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        file_type_stats=dict(file_type_stats),
        file_types=file_types,
        sections=sections,
    )

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    print(f"Total items: {total_count}")
    print(f"  High relevance: {high_count}")
    print(f"  Medium relevance: {medium_count}")
    print(f"  Low relevance: {low_count}")


def generate_csv(items: list[dict], output_path: str) -> None:
    """Generate CSV export from items."""
    enriched = enrich_items_with_scores(items)
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    headers = [
        "URL", "Titel", "Typ", "Dateityp", "Größe (Bytes)", "Bereich",
        "IWG Score", "Konfidenz", "Maschinenlesbar", "Hat Tabellen", "Fundort"
    ]

    lines = [";".join(headers)]
    for item in enriched:
        row = [
            item.get("url", ""),
            (item.get("title") or "").replace(";", ","),
            item.get("type", ""),
            item.get("file_type", ""),
            str(item.get("file_size_bytes") or ""),
            item.get("page_section", ""),
            str(item.get("iwg_score", "")),
            item.get("iwg_confidence", ""),
            str(item.get("machine_readable", "")),
            str(item.get("has_tables", "")),
            item.get("found_on_page", ""),
        ]
        lines.append(";".join(row))

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    print(f"CSV generated: {output_path}")
