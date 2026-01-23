#!/bin/bash
set -e

echo "=== OeNB IWG Scraper ==="
echo ""

# Parse arguments
RAG_MODE=false
for arg in "$@"; do
    case $arg in
        --rag)
            RAG_MODE=true
            shift
            ;;
    esac
done

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
if [ "$RAG_MODE" = true ]; then
    echo "Starting scraper WITH RAG (SQLite + HTML storage)..."
    PIPELINES="oenb_scraper.pipelines.DeduplicationPipeline:100,oenb_scraper.pipelines.FileSizePipeline:200,oenb_scraper.pipelines.SQLitePipeline:400"
else
    echo "Starting scraper (standard mode)..."
    PIPELINES=""
fi
echo "Press Ctrl+C to stop early."
echo ""

TIMESTAMP=$(date +%Y-%m-%d_%H%M)
OUTPUT_FILE="data/${TIMESTAMP}_downloads.json"
LOG_FILE="data/${TIMESTAMP}_scraper.log"
DB_FILE="data/pages.db"
echo "Output: $OUTPUT_FILE"
echo "Log: $LOG_FILE"
if [ "$RAG_MODE" = true ]; then
    echo "SQLite DB: $DB_FILE"
fi

cd scraper
if [ "$RAG_MODE" = true ]; then
    scrapy crawl oenb -O "../$OUTPUT_FILE" \
        -s "ITEM_PIPELINES={'oenb_scraper.pipelines.DeduplicationPipeline': 100, 'oenb_scraper.pipelines.FileSizePipeline': 200, 'oenb_scraper.pipelines.SQLitePipeline': 400}" \
        -s "SQLITE_DB_PATH=../$DB_FILE" \
        2>&1 | tee "../$LOG_FILE"
else
    scrapy crawl oenb -O "../$OUTPUT_FILE" 2>&1 | tee "../$LOG_FILE"
fi
cd ..

# Generate Claude Dashboard
echo ""
echo "Generating Claude Dashboard..."
PYTHONPATH="$PWD" python analysis/generate_claude_dashboard.py --input "$OUTPUT_FILE"

echo ""
echo "=== Complete ==="
echo "Dashboard generated in data/ directory"
