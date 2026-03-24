import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.query_knowledge_base import search_knowledge_base


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_search_knowledge_base_prefers_primary_statistics_hits(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum. Base rate.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
            }
        ],
    )
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:pdf:1",
                "parent_record_type": "asset_document",
                "chunk_kind": "asset_document_summary",
                "title": "Historisches PDF zu Leitzinsen",
                "text": "Leitzins Leitzins Leitzins in einem alten PDF.",
                "retrieval_score": 250,
                "retrieval_tier": "background",
                "reference_urls": ["https://www.oenb.at/downloads/old.pdf"],
            }
        ],
    )

    results = search_knowledge_base(
        query="aktueller Leitzins",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
    )

    assert results[0]["id"] == "stats:family:1"
    assert results[0]["source_preference"] == "primary"


def test_search_knowledge_base_falls_back_to_secondary_when_primary_has_no_hit(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum. Base rate.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
            }
        ],
    )
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:page:1",
                "parent_record_type": "page_document",
                "chunk_kind": "family_summary",
                "title": "Hackathon",
                "text": "Die OeNB veranstaltet einen Hackathon.",
                "retrieval_score": 800,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/hackathon"],
            }
        ],
    )

    results = search_knowledge_base(
        query="hackathon",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
    )

    assert results[0]["id"] == "full:page:1"
    assert results[0]["source_preference"] == "secondary"


def test_search_knowledge_base_uses_retrieval_score_inside_same_source(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:asset:1",
                "parent_record_type": "asset_document",
                "chunk_kind": "asset_document_summary",
                "title": "Download CSV",
                "text": "Base rate table as CSV.",
                "retrieval_score": 700,
                "retrieval_tier": "secondary",
                "reference_urls": ["https://www.oenb.at/downloads/base.csv"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum. Base rate.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
            },
        ],
    )

    results = search_knowledge_base(
        query="base rate",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert [result["id"] for result in results[:2]] == ["stats:family:1", "stats:asset:1"]


def test_search_knowledge_base_prefers_exact_title_match_over_supporting_page_noise(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:2.1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": (
                    "Latest observation: 11.06.25 = 1.53 % per annum. "
                    "Base rate and reference rate. "
                    "Supporting pages: International key interest rates, International long-term government bond yields."
                ),
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../Base-and-Reference-Rates.html"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:10.4",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Latest observation: 2025 = 2.15 %. Euro area.",
                "retrieval_score": 950,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../international-key-interest-rates.html"],
            },
        ],
    )

    results = search_knowledge_base(
        query="aktueller Leitzins",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results[0]["id"] == "stats:family:10.4"


def test_search_knowledge_base_does_not_return_real_estate_for_gold_query(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:rppi",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Residential property price index",
                "text": "Latest observation: 2025 = 266.9 Index.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/residential-property-price-index.html"
                ],
            }
        ],
    )

    results = search_knowledge_base(
        query="Wie hoch ist der Goldpreis aktuell?",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results == []


def test_search_knowledge_base_blocks_services_trade_for_deposit_facility_query(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:9.2.02",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Internationaler Dienstleistungsverkehr - Regional",
                "text": "Dienstleistungen, Netto, Euroraum 19.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=9.2.02"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:10.4",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Latest observation: 2025. Euro area = 2.15 %.",
                "retrieval_score": 950,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=10.4"],
            },
        ],
    )

    results = search_knowledge_base(
        query="Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results[0]["id"] == "stats:family:10.4"


def test_search_knowledge_base_allows_multi_domain_hits_for_multi_topic_query(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:rppi",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Residential property price index",
                "text": "Latest observation: 2025 = 266.9 Index.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/residential-property-price-index.html"
                ],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Gold price in EUR.",
                "retrieval_score": 950,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/commodity-prices/gold.html"
                ],
            },
        ],
    )

    results = search_knowledge_base(
        query="Mich interessieren Immobilienpreise und Gold",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert {result["id"] for result in results[:2]} == {"stats:family:rppi", "stats:family:gold"}


def test_search_knowledge_base_ignores_stopword_and_supporting_page_noise_for_gold_query(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:wages",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Negotiated standard wage rate index",
                "text": (
                    "Dataset family: Negotiated standard wage rate index. "
                    "Latest observation: 2025 = 140.0 Index. "
                    "Supporting pages: World commodity prices, Residential property price index."
                ),
                "retrieval_score": 1100,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/wages/Negotiated-Standard-Wage-Rate-Index.html",
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/Commodity-Prices/World-Commodity-Prices.html",
                ],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Latest observation: 2025-03 = 2150.4 USD. Gold price.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/commodity-prices/gold.html"
                ],
            },
        ],
    )

    results = search_knowledge_base(
        query="Wie hoch ist der Goldpreis aktuell?",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results[0]["id"] == "stats:family:gold"


def test_search_knowledge_base_requires_stronger_match_for_deposit_facility_than_generic_interest_section(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:fx",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Currencies and foreign exchange rates in other countries",
                "text": "Latest observation: Oct. 25. Cambodia KHR Riel = 4,691.0000 national currency unit per EUR.",
                "retrieval_score": 1150,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Exchange-Rates/Currencies-and-Foreign-Exchange-Rates-in-Other-Countries-Pakistan-to-Vietnam.html"
                ],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:key-rates",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Latest observation: 2025. Euro area = 2.15 %.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates/international-key-interest-rates.html"
                ],
            },
        ],
    )

    results = search_knowledge_base(
        query="Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results[0]["id"] == "stats:family:key-rates"


def test_search_knowledge_base_prefers_key_interest_rates_for_deposit_facility_over_base_reference_rates(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:2.1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum. Base rate and reference rate.",
                "retrieval_score": 1005,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Base-and-Reference-Rates/Base-and-Reference-Rates-of-the-Oesterreichische-Nationalbank.html"
                ],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:dataset:10.4",
                "parent_record_type": "isaweb_dataset",
                "chunk_kind": "isaweb_dataset_summary",
                "title": "Key interest rates",
                "text": "ISAweb dataset: Key interest rates. Latest observation: 2025 = 2.15 %. Dimensions: report_id=10.4.",
                "retrieval_score": 930,
                "retrieval_tier": "primary",
                "reference_urls": [
                    "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"
                ],
            },
        ],
    )

    results = search_knowledge_base(
        query="Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        primary_path=primary_path,
        secondary_path=None,
        limit=5,
    )

    assert results[0]["id"] == "stats:dataset:10.4"


def test_search_knowledge_base_can_prioritize_secondary_release_page_for_release_queries(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:inflation",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Selected inflation indicators",
                "text": "Latest observation: 2025 = 116.3 Index.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1"],
            }
        ],
    )
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "page:release-calendar",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Release calendar for inflation statistics",
                "text": "Next release date for inflation and consumer price index tables.",
                "retrieval_score": 850,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"],
            }
        ],
    )

    results = search_knowledge_base(
        query="Wann werden die naechsten Inflationsdaten veroeffentlicht?",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
        routed_query={
            "intent": "topic_overview",
            "query_intent": "release_lookup",
            "domains": ["commodity_prices", "website_general"],
            "entities": ["Inflation"],
            "freshness_need": "low",
            "subqueries": [],
            "strategy": "hybrid",
        },
    )

    assert results[0]["id"] == "page:release-calendar"


def test_search_knowledge_base_can_prioritize_secondary_download_page_for_navigation_queries(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:commodity",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "World commodity prices",
                "text": "Latest observation: 2025 = 69.3 Crude oil prices.",
                "retrieval_score": 1100,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.9"],
            }
        ],
    )
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "page:bargeld-download",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Bargeldumlauf CSV Download",
                "text": "Cash in circulation data can be downloaded as CSV or Excel.",
                "retrieval_score": 820,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/statistik/bargeld/download-csv.html"],
            }
        ],
    )

    results = search_knowledge_base(
        query="Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
        routed_query={
            "intent": "topic_overview",
            "query_intent": "navigation",
            "domains": ["website_general"],
            "entities": ["Bargeldumlauf"],
            "freshness_need": "low",
            "subqueries": [],
            "strategy": "rag_first",
        },
    )

    assert results[0]["id"] == "page:bargeld-download"
