def test_extract_text_from_html():
    """Test extracting clean text from HTML."""
    from analysis.extract_text import extract_text_from_html

    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation here</nav>
        <main>
            <h1>Main Content</h1>
            <p>This is the important text.</p>
        </main>
        <footer>Footer stuff</footer>
        <script>var x = 1;</script>
    </body>
    </html>
    """

    result = extract_text_from_html(html)

    assert result["title"] == "Test Page"
    assert "Main Content" in result["text"]
    assert "important text" in result["text"]
    assert "Navigation here" not in result["text"]
    assert "var x = 1" not in result["text"]


import sqlite3
import tempfile
import gzip
from pathlib import Path

def test_batch_extraction():
    """Test extracting text from all pages in database."""
    from analysis.extract_text import extract_text_from_html, run_extraction
    from oenb_scraper.database import init_db, start_crawl_run, store_page

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://test.at/", "Test/1.0")

        html = b"<html><head><title>Test</title></head><body><p>Content here</p></body></html>"
        store_page(conn, run_id, "https://test.at/page1.html", "https://test.at/page1.html", 200, "text/html", html)
        conn.close()

        run_extraction(db_path, extractor_version="test-v1")

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT title, text_content, extractor_version FROM page_content").fetchone()
        assert row[0] == "Test"
        assert "Content here" in row[1]
        assert row[2] == "test-v1"
        conn.close()


def test_extract_text_includes_chart_data():
    """Test that isawebstat chart data is included in extracted text."""
    from analysis.extract_text import extract_text_from_html

    html = '''
    <html><head><title>DATA Chart - Leitzinssätze</title></head>
    <body>
    <script>
    $scope.data = [
        {
            key: "Euroraum",
            color: "#607EA9",
            values: [{"x": "0", "label": "2024", "value": 3.15}, {"x": "1", "label": "2025", "value": 2.15}]
        }
    ];
    </script>
    <div>Chart wählen Leitzinssätze</div>
    </body></html>
    '''

    result = extract_text_from_html(html)

    assert "Leitzinssätze" in result["text"]
    assert "Euroraum" in result["text"]
    assert "2025: 2.15" in result["text"]