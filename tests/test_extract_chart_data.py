"""Tests for isawebstat chart data extraction."""


def test_extract_chart_json_from_script():
    """Test extracting chart data JSON from isawebstat <script> tag."""
    from analysis.extract_chart_data import extract_chart_data

    html = '''
    <html><head><title>DATA Chart - Leitzinssätze</title></head>
    <body>
    <script>
    $scope.data = [
        {
            key: "Euroraum",
            color: "#607EA9",
            values: [{"x": "0", "label": "2023", "value": 4.5}, {"x": "1", "label": "2024", "value": 3.15}, {"x": "2", "label": "2025", "value": 2.15}]
        },
        {
            key: "USA",
            color: "#CD3482",
            values: [{"x": "0", "label": "2023", "value": 5.5}, {"x": "1", "label": "2024", "value": 4.5}, {"x": "2", "label": "2025", "value": 3.75}]
        }
    ];
    </script>
    </body></html>
    '''

    result = extract_chart_data(html)

    assert result is not None
    assert result["title"] == "Leitzinssätze"
    assert len(result["series"]) == 2
    assert result["series"][0]["key"] == "Euroraum"
    assert result["series"][0]["values"][-1] == {"label": "2025", "value": 2.15}
    assert result["series"][1]["key"] == "USA"


def test_extract_chart_json_returns_none_for_non_chart():
    """Test that non-chart HTML returns None."""
    from analysis.extract_chart_data import extract_chart_data

    html = '<html><body><p>Normal page</p></body></html>'
    result = extract_chart_data(html)
    assert result is None


def test_chart_data_to_text():
    """Test converting chart data to searchable text."""
    from analysis.extract_chart_data import chart_data_to_text

    chart_data = {
        "title": "Leitzinssätze",
        "source": "Macrobond",
        "series": [
            {
                "key": "Euroraum",
                "values": [
                    {"label": "2024", "value": 3.15},
                    {"label": "2025", "value": 2.15},
                ]
            },
            {
                "key": "USA",
                "values": [
                    {"label": "2024", "value": 4.5},
                    {"label": "2025", "value": 3.75},
                ]
            }
        ]
    }

    text = chart_data_to_text(chart_data)

    assert "Leitzinssätze" in text
    assert "Euroraum" in text
    assert "2025: 2.15" in text
    assert "USA" in text
    assert "2025: 3.75" in text
    assert "Macrobond" in text
