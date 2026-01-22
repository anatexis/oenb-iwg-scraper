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
