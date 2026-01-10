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


def generate_usage_snippets(item: dict) -> dict:
    """Generate usage snippets for a download item."""
    url = item.get("url", "")
    base_name = url.split("/")[-1] or "data"
    file_type = item.get("file_type", "").lower()
    
    snippets = {}
    
    # Python
    if file_type == "csv":
        snippets["python"] = f"import pandas as pd\n# Requires: pip install pandas\ndf = pd.read_csv('{url}')\nprint(df.head())"
    elif file_type in ["xlsx", "xls"]:
        snippets["python"] = f"import pandas as pd\n# Requires: pip install pandas openpyxl\ndf = pd.read_excel('{url}')\nprint(df.head())"
    elif file_type == "xml":
        snippets["python"] = f"import pandas as pd\n# Requires: pip install pandas lxml\ndf = pd.read_xml('{url}')\nprint(df.head())"
    elif file_type == "json":
        snippets["python"] = f"import pandas as pd\n# Requires: pip install pandas\ndf = pd.read_json('{url}')\nprint(df.head())"
    else:
        snippets["python"] = f"import requests\n# Requires: pip install requests\nr = requests.get('{url}')\nwith open('{base_name}', 'wb') as f:\n    f.write(r.content)"

    # R
    if file_type == "csv":
        snippets["r"] = f"# R script\ndf <- read.csv('{url}')\nhead(df)"
    elif file_type in ["xlsx", "xls"]:
        snippets["r"] = f"# R script\nlibrary(readxl)\ndownload.file('{url}', destfile='temp.xlsx', mode='wb')\ndf <- read_excel('temp.xlsx')\nhead(df)"
    else:
        snippets["r"] = f"# R script\ndownload.file('{url}', destfile='{base_name}', mode='wb')"

    # cURL
    snippets["curl"] = f"curl -O {url}"

    return snippets


def generate_dashboard(items: list[dict], output_path: str) -> None:
    """Generate HTML dashboard from items."""
    # Enrich with IWG scores
    enriched = enrich_items_with_scores(items)

    # Sort by score descending
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    # Add usage snippets
    for item in enriched:
        item["snippets"] = generate_usage_snippets(item)

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
        "Sprache", "Bilingual", "IWG Score", "Konfidenz", "Maschinenlesbar",
        "Hat Tabellen", "Fundort"
    ]

    lines = [";".join(headers)]
    for item in enriched:
        langs = item.get("found_in_languages") or [item.get("language", "de")]
        is_bilingual = "de" in langs and "en" in langs
        row = [
            item.get("url", ""),
            (item.get("title") or "").replace(";", ","),
            item.get("type", ""),
            item.get("file_type", ""),
            str(item.get("file_size_bytes") or ""),
            item.get("page_section", ""),
            item.get("language", "de"),
            "Ja" if is_bilingual else "Nein",
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
