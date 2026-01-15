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
echo "Starting scraper (estimated: 12-15 hours for full crawl)..."
echo "Press Ctrl+C to stop early."
echo ""

TIMESTAMP=$(date +%Y-%m-%d_%H%M)
OUTPUT_FILE="data/${TIMESTAMP}_downloads.json"
LOG_FILE="data/${TIMESTAMP}_scraper.log"
echo "Output: $OUTPUT_FILE"
echo "Log: $LOG_FILE"

cd scraper
scrapy crawl oenb -O "../$OUTPUT_FILE" 2>&1 | tee "../$LOG_FILE"
cd ..

# Run analysis
echo ""
echo "Running analysis..."
python analysis/analyze.py --input "$OUTPUT_FILE"

echo ""
echo "=== Complete ==="
echo "Open output/dashboard.html in your browser"
