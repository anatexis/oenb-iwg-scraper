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
    sections = sorted(set(i["page_section"] for i in enriched if i.get("page_section")), key=str.lower)

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

        # Separate isaweb items from rest
        isaweb_items = [i for i in enriched if "isaweb" in i.get("page_section", "").lower()]
        non_isaweb_items = [i for i in enriched if "isaweb" not in i.get("page_section", "").lower()]

        # Build lookup: normalize page_section to match sitemap
        def normalize_section(s):
            """Normalize section name for matching: lowercase, remove hyphens/spaces/underscores."""
            if not s:
                return ""
            # Convert German umlauts for matching
            s = s.lower()
            s = s.replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss")
            s = s.replace("-", "").replace(" ", "").replace("_", "")
            return s

        # Group non-isaweb items by their original page_section (for direct lookup)
        # and also by normalized form
        section_items_by_original = {}
        section_items_by_norm = {}
        for item in non_isaweb_items:
            ps = item.get("page_section", "")
            # Store by original (lowercase)
            ps_lower = ps.lower()
            if ps_lower not in section_items_by_original:
                section_items_by_original[ps_lower] = []
            section_items_by_original[ps_lower].append(item)
            # Store by normalized
            norm = normalize_section(ps)
            if norm not in section_items_by_norm:
                section_items_by_norm[norm] = []
            section_items_by_norm[norm].append(item)

        # Calculate stats per sitemap section (excluding isaweb)
        for section in sitemap_data:
            section_norm = normalize_section(section["name"])
            # Extract URL slug (e.g., "Ueber-Uns" from "https://www.oenb.at/Ueber-Uns.html")
            url_slug = section["url"].split("/")[-1].replace(".html", "")
            url_slug_lower = url_slug.lower()
            url_slug_norm = normalize_section(url_slug)

            # Find matching items using multiple strategies
            matched_items = []
            matched_keys = set()

            # Strategy 1: Direct match on original page_section (lowercase)
            if url_slug_lower in section_items_by_original:
                for item in section_items_by_original[url_slug_lower]:
                    key = id(item)
                    if key not in matched_keys:
                        matched_keys.add(key)
                        matched_items.append(item)

            # Strategy 2: Normalized match
            if url_slug_norm in section_items_by_norm:
                for item in section_items_by_norm[url_slug_norm]:
                    key = id(item)
                    if key not in matched_keys:
                        matched_keys.add(key)
                        matched_items.append(item)

            section["item_count"] = len(matched_items)

            # Count by file type for color coding
            type_counts = Counter(i.get("file_type", "unknown") for i in matched_items)
            section["type_counts"] = dict(type_counts)

            # Calculate "quality" score (% machine-readable: csv, xlsx, xml, json)
            machine_readable = sum(type_counts.get(t, 0) for t in ["csv", "xlsx", "xls", "xml", "json"])
            section["machine_readable_count"] = machine_readable
            section["machine_readable_pct"] = round(machine_readable / len(matched_items) * 100) if matched_items else 0

            # Also calculate subsection stats
            if section.get("subsections"):
                for sub in section["subsections"]:
                    sub_url_slug = sub["url"].split("/")[-1].replace(".html", "")
                    sub_url_slug_lower = sub_url_slug.lower()
                    sub_url_slug_norm = normalize_section(sub_url_slug)

                    sub_items = []
                    sub_matched_keys = set()

                    # Direct match
                    if sub_url_slug_lower in section_items_by_original:
                        for item in section_items_by_original[sub_url_slug_lower]:
                            key = id(item)
                            if key not in sub_matched_keys:
                                sub_matched_keys.add(key)
                                sub_items.append(item)

                    # Normalized match
                    if sub_url_slug_norm in section_items_by_norm:
                        for item in section_items_by_norm[sub_url_slug_norm]:
                            key = id(item)
                            if key not in sub_matched_keys:
                                sub_matched_keys.add(key)
                                sub_items.append(item)

                    sub["item_count"] = len(sub_items)
                    sub_type_counts = Counter(i.get("file_type", "unknown") for i in sub_items)
                    sub["type_counts"] = dict(sub_type_counts)

        # Add isaweb as special section
        isaweb_section = {
            "name": "isaweb",
            "url": "https://www.oenb.at/isawebstat/",
            "item_count": len(isaweb_items),
            "type_counts": dict(Counter(i.get("file_type", "unknown") for i in isaweb_items)),
            "machine_readable_count": 0,
            "machine_readable_pct": 0,
            "subsections": [],
            "is_isaweb": True,
        }
        sitemap_data.insert(0, isaweb_section)

        # Calculate percentages based on TOTAL (with isaweb)
        total_all = len(enriched)
        total_without_isaweb = len(non_isaweb_items)
        for section in sitemap_data:
            section["item_pct"] = round(section["item_count"] / total_all * 100, 1) if total_all else 0
            section["item_pct_no_isaweb"] = round(section["item_count"] / total_without_isaweb * 100, 1) if total_without_isaweb and not section.get("is_isaweb") else 0

        # Store totals for template
        sitemap_total = total_all
        sitemap_total_no_isaweb = total_without_isaweb
    else:
        sitemap_data = []
        sitemap_total = 0
        sitemap_total_no_isaweb = 0

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
        sitemap_total=sitemap_total,
        sitemap_total_no_isaweb=sitemap_total_no_isaweb,
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
