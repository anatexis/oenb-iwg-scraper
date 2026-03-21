import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.domain_gating import classify_record_domains, filter_records_for_route


def test_classify_record_domains_detects_real_estate_family():
    record = {
        "title": "Residential property price index",
        "text": "Latest observation for RPPI in Austria.",
        "reference_urls": [
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/residential-property-price-index.html"
        ],
    }

    assert "real_estate" in classify_record_domains(record)


def test_filter_records_for_route_keeps_only_matching_domains():
    records = [
        {
            "id": "real-estate",
            "title": "Residential property price index",
            "text": "RPPI Austria.",
            "reference_urls": ["https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"],
        },
        {
            "id": "commodity",
            "title": "Commodity prices - gold",
            "text": "Gold price for Austria.",
            "reference_urls": ["https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"],
        },
    ]

    filtered = filter_records_for_route(
        records,
        {
            "domains": ["commodity_prices"],
            "intent": "fact_lookup",
            "entities": ["Goldpreis"],
            "freshness_need": "high",
            "subqueries": [],
        },
    )

    assert [record["id"] for record in filtered] == ["commodity"]


def test_classify_record_domains_ignores_supporting_page_reference_noise():
    record = {
        "title": "Negotiated standard wage rate index",
        "text": "Latest observation: 2025 = 140.0 Index.",
        "reference_urls": [
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/wages/Negotiated-Standard-Wage-Rate-Index.html",
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/Commodity-Prices/World-Commodity-Prices.html",
        ],
    }

    assert "commodity_prices" not in classify_record_domains(record)
