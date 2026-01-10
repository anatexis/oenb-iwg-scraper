#!/bin/bash
set -e

echo "=== OeNB IWG Scraper ==="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Run scraper
echo ""
echo "Starting scraper (this may take 10-30 minutes)..."
echo "Press Ctrl+C to stop early."
echo ""

cd scraper
rm -f ../data/downloads.json
scrapy crawl oenb -O ../data/downloads.json
cd ..

# Run analysis
echo ""
echo "Running analysis..."
python analysis/analyze.py

echo ""
echo "=== Complete ==="
echo "Open output/dashboard.html in your browser"
