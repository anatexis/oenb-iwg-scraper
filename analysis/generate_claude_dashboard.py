"""Generate Claude Dashboard - IWG Review Dashboard with persistence."""

import json
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from analysis.iwg_scorer import enrich_items_with_scores
from analysis.sitemap_parser import parse_sitemap_html, get_default_sitemap_path


def load_data(json_path: str) -> list[dict]:
    """Load scraped data from JSON file.

    Handles files with multiple concatenated JSON arrays (from multiple scraper runs).
    """
    with open(json_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Try to parse directly first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Find the end of the first valid JSON array
    depth = 0
    in_string = False
    escape = False
    end_pos = 0

    for i, c in enumerate(content):
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break

    if end_pos > 0:
        return json.loads(content[:end_pos])

    raise ValueError(f"Could not parse JSON from {json_path}")


def generate_claude_dashboard(items: list[dict], output_path: str) -> None:
    """Generate the Claude Dashboard HTML from items."""
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
    file_type_stats = dict(Counter(i["file_type"] for i in enriched))

    # Section stats (top 10)
    section_counts = Counter(i["page_section"] for i in enriched if i.get("page_section"))
    section_stats = dict(section_counts.most_common(10))

    # Unique values for filters
    file_types = sorted(set(i["file_type"] for i in enriched))
    sections = sorted(set(i["page_section"] for i in enriched if i.get("page_section")))

    # Setup Jinja2
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))

    # Add truncate filter
    def truncate(s, length=50):
        s = str(s) if s else ""
        return s[:length] + "..." if len(s) > length else s
    env.filters["truncate"] = truncate

    template = env.get_template("claude_dashboard.html")

    # Parse sitemap for visualization
    sitemap_path = get_default_sitemap_path()
    if sitemap_path.exists():
        sitemap_data = parse_sitemap_html(str(sitemap_path))
        # Add download counts per section
        section_downloads = Counter(i["page_section"] for i in enriched if i.get("page_section"))
        for section in sitemap_data:
            section_key = section["name"].replace(" ", "-")
            # Try various key formats
            download_count = 0
            for key in [section["name"], section_key, section["url"].split("/")[-1].replace(".html", "")]:
                if key in section_downloads:
                    download_count = section_downloads[key]
                    break
            section["download_count"] = download_count
    else:
        sitemap_data = []

    # Render
    html = template.render(
        items=enriched,
        items_json=json.dumps(enriched, ensure_ascii=False),
        total_count=total_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        file_type_stats=file_type_stats,
        section_stats=section_stats,
        file_types=file_types,
        sections=sections,
        sitemap_data=sitemap_data,
    )

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Claude Dashboard generated: {output_path}")
    print(f"Total items: {total_count}")
    print(f"  High relevance: {high_count}")
    print(f"  Medium relevance: {medium_count}")
    print(f"  Low relevance: {low_count}")


def main():
    """Main entry point."""
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(description="Generate Claude Dashboard for IWG review")
    parser.add_argument(
        "--input", "-i",
        help="Input JSON file (default: latest in data/)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output HTML file (default: data/<timestamp>_claude_dashboard.html)"
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Skip Deep Scan (use if analyze.py already ran)"
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    # Find input file
    if args.input:
        json_path = Path(args.input)
    else:
        # Find latest JSON file in data/
        json_files = sorted(data_dir.glob("*_downloads.json"), reverse=True)
        if json_files:
            json_path = json_files[0]
        else:
            json_path = data_dir / "downloads.json"

    if not json_path.exists():
        print(f"Error: Data file not found: {json_path}")
        print("Run the scraper first to generate data.")
        return

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output_path = data_dir / f"{timestamp}_claude_dashboard.html"

    # Load data
    print(f"Loading data from {json_path}...")
    items = load_data(str(json_path))
    print(f"Loaded {len(items)} items")

    # Run Deep Scan (False Hope Detector) unless skipped
    if not args.skip_scan:
        from analysis.deep_scan import DeepScanner
        print("\nRunning Deep Scan (validates top-scoring files)...")
        scanner = DeepScanner(limit_percent=0.1, min_items=5)
        items = scanner.scan_items(items)
    else:
        print("\nSkipping Deep Scan (--skip-scan flag set)")

    # Generate dashboard
    print("\nGenerating Claude Dashboard...")
    generate_claude_dashboard(items, str(output_path))


if __name__ == "__main__":
    main()
