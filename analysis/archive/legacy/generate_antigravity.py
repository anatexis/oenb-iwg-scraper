#!/usr/bin/env python3
"""
Generate the Antigravity Dashboard (Static HTML Reviewer).
Leaves the legacy dashboard intact.
"""

import json
import argparse
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.dashboard import load_data, generate_usage_snippets
from analysis.iwg_scorer import enrich_items_with_scores
from analysis.deep_scan import DeepScanner

def generate_antigravity_dashboard(items: list[dict], output_path: str) -> None:
    """Generate Antigravity Dashboard (Static HTML) from items."""
    
    # --- DEEP SCAN (False Hope Detector) ---
    print("Running Deep Scan (False Hope Detector)...")
    # Low limit_percent ensures quick runs for demo, usually you'd want more
    scanner = DeepScanner(limit_percent=0.1, min_items=5)
    items = scanner.scan_items(items)
    # ---------------------------------------

    print("Enriching items with scores...")
    enriched = enrich_items_with_scores(items)

    print("Sorting by score...")
    enriched.sort(key=lambda x: x["iwg_score"], reverse=True)

    print("Generating code snippets...")
    for item in enriched:
        item["snippets"] = generate_usage_snippets(item)

    # Setup Jinja2
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Use the reviewer template
    template_name = "reviewer.html"
    try:
        template = env.get_template(template_name)
    except Exception as e:
        print(f"Error loading template '{template_name}': {e}")
        return

    # Render - we only need to pass the JSON string
    print("Rendering HTML...")
    items_json = json.dumps(enriched, ensure_ascii=False)
    
    html = template.render(
        items_json=items_json
    )

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Antigravity Dashboard generated: {output_path}")
    print(f"   Total items embedded: {len(enriched)}")


def main():
    parser = argparse.ArgumentParser(description="Generate Antigravity Dashboard")
    parser.add_argument(
        "--input", "-i",
        default="data/downloads.json",
        help="Input JSON file from scraper"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Output directory"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading data from {input_path}...")
    items = load_data(str(input_path))

    output_file = output_dir / "antigravity_dashboard.html"
    generate_antigravity_dashboard(items, str(output_file))


if __name__ == "__main__":
    main()
