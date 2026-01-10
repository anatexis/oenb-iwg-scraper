#!/usr/bin/env python3
"""
Main analysis script for OeNB IWG audit.

Usage:
    python analysis/analyze.py [--input data/downloads.json] [--output-dir output/]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.dashboard import generate_dashboard, generate_csv, load_data


def main():
    parser = argparse.ArgumentParser(description="Analyze OeNB downloads for IWG relevance")
    parser.add_argument(
        "--input", "-i",
        default="data/downloads.json",
        help="Input JSON file from scraper (default: data/downloads.json)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Output directory (default: output/)"
    )
    args = parser.parse_args()

    # Check input exists
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run the scraper first: cd scraper && scrapy crawl oenb -o ../data/downloads.json")
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading data from {input_path}...")
    items = load_data(str(input_path))
    print(f"Loaded {len(items)} items")

    if not items:
        print("No items found. Check if the scraper ran successfully.")
        sys.exit(1)

    # Generate outputs
    dashboard_path = output_dir / "dashboard.html"
    csv_path = output_dir / "downloads.csv"

    print("\nGenerating dashboard...")
    generate_dashboard(items, str(dashboard_path))

    print("\nGenerating CSV...")
    generate_csv(items, str(csv_path))

    print(f"\nDone! Open {dashboard_path} in your browser.")


if __name__ == "__main__":
    main()
