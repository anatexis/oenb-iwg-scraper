import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.query_knowledge_base import search_knowledge_base, _query_intent_record_boost


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


# ---------------------------------------------------------------------------
# Unit tests for _query_intent_record_boost — navigation intent new boosts
# ---------------------------------------------------------------------------


def _make_routed(intent: str) -> dict:
    return {"query_intent": intent, "domains": ["website_general"]}


def test_navigation_page_document_secondary_gets_unconditional_500_boost():
    """page_document in secondary KB gets +500 for navigation, even without download terms."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "page_document"},
        title="zahlungsbilanz übersicht",
        text="allgemeine informationen zur zahlungsbilanz",
        primary_url="https://www.oenb.at/statistik/zahlungsbilanz.html",
        source_preference="secondary",
    )
    # Existing +200 (secondary page_document) + new +500 = 700
    assert boost == 700


def test_navigation_page_document_secondary_with_download_terms_stacks():
    """page_document with download terms stacks existing +700 and +200 with new +500."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "page_document"},
        title="bargeldumlauf csv download",
        text="download als csv oder excel",
        primary_url="https://www.oenb.at/statistik/bargeld/download-csv.html",
        source_preference="secondary",
    )
    # +700 (download terms) + +200 (secondary) + +500 (new unconditional) = 1400
    assert boost == 1400


def test_navigation_page_document_primary_kb_gets_no_page_boost():
    """page_document in primary (statistics) KB must NOT get page boosts."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "page_document"},
        title="isawebstat portal page",
        text="some portal content",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    assert boost == 0


def test_navigation_section_navigation_gets_300_boost():
    """section_navigation chunks get +300 for navigation intent."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "section_navigation"},
        title="statistik navigation",
        text="links zu statistik-seiten",
        primary_url="https://www.oenb.at/statistik/",
        source_preference="secondary",
    )
    assert boost == 300


def test_navigation_dataset_family_gets_minus_200_penalty():
    """dataset_family gets -200 unconditional penalty in navigation (on top of any download-term penalty)."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "dataset_family"},
        title="key interest rates",
        text="latest observation: 2025 = 2.15 %",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    # No download terms, so only the new -200
    assert boost == -200


def test_navigation_dataset_family_with_download_terms_gets_both_penalties():
    """dataset_family with download terms gets +700 (download terms, not page in primary)
    -300 (existing download-term dataset_family penalty) -200 (new unconditional) = +200."""
    boost = _query_intent_record_boost(
        _make_routed("navigation"),
        {"parent_record_type": "dataset_family"},
        title="download csv data",
        text="csv export of interest rates",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    # +700 (download terms, not is_page_in_primary_kb) - 300 (download-term penalty) - 200 (new unconditional) = 200
    assert boost == 200


# ---------------------------------------------------------------------------
# Unit tests for _query_intent_record_boost — explanation intent (new block)
# ---------------------------------------------------------------------------


def test_explanation_page_document_secondary_gets_400_boost():
    """page_document in secondary KB gets +400 for explanation intent."""
    boost = _query_intent_record_boost(
        _make_routed("explanation"),
        {"parent_record_type": "page_document"},
        title="was ist die zahlungsbilanz",
        text="die zahlungsbilanz erfasst alle wirtschaftlichen transaktionen",
        primary_url="https://www.oenb.at/statistik/zahlungsbilanz/erklaerung.html",
        source_preference="secondary",
    )
    assert boost == 400


def test_explanation_page_document_primary_kb_gets_no_boost():
    """page_document in primary KB must NOT get explanation boost."""
    boost = _query_intent_record_boost(
        _make_routed("explanation"),
        {"parent_record_type": "page_document"},
        title="isawebstat portal",
        text="portal content",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    assert boost == 0


def test_explanation_section_navigation_gets_300_boost():
    """section_navigation gets +300 for explanation intent."""
    boost = _query_intent_record_boost(
        _make_routed("explanation"),
        {"parent_record_type": "section_navigation"},
        title="statistik übersicht",
        text="überblick über statistikbereiche",
        primary_url="https://www.oenb.at/statistik/",
        source_preference="secondary",
    )
    assert boost == 300


def test_explanation_dataset_family_gets_minus_200_penalty():
    """dataset_family gets -200 penalty for explanation intent."""
    boost = _query_intent_record_boost(
        _make_routed("explanation"),
        {"parent_record_type": "dataset_family"},
        title="key interest rates",
        text="latest observation: 2025 = 2.15 %",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    assert boost == -200


def test_topic_overview_boosts_page_no_dataset_penalty():
    """topic_overview boosts pages but does NOT penalize datasets."""
    page_boost = _query_intent_record_boost(
        _make_routed("topic_overview"),
        {"parent_record_type": "page_document"},
        title="was ist die zahlungsbilanz",
        text="erklaerung",
        primary_url="https://www.oenb.at/statistik/erklaerung.html",
        source_preference="secondary",
    )
    family_boost = _query_intent_record_boost(
        _make_routed("topic_overview"),
        {"parent_record_type": "dataset_family"},
        title="services trade",
        text="observation",
        primary_url="https://www.oenb.at/isawebstat/...",
        source_preference="primary",
    )
    secnav_boost = _query_intent_record_boost(
        _make_routed("topic_overview"),
        {"parent_record_type": "section_navigation"},
        title="statistik",
        text="überblick",
        primary_url="https://www.oenb.at/statistik/",
        source_preference="secondary",
    )
    assert page_boost == 250
    assert family_boost == 0  # No penalty for topic_overview
    assert secnav_boost == 150


# ---------------------------------------------------------------------------
# Ensure existing behavior is preserved
# ---------------------------------------------------------------------------


def test_release_lookup_unchanged():
    """release_lookup intent is not affected by the new boosts."""
    boost = _query_intent_record_boost(
        _make_routed("release_lookup"),
        {"parent_record_type": "page_document"},
        title="release calendar for inflation statistics",
        text="next release date for inflation",
        primary_url="https://www.oenb.at/isawebstat/releasekalender/...",
        source_preference="secondary",
    )
    # Existing: +900 (release in title) + +250 (secondary page_document)
    assert boost == 1150


def test_no_routed_query_returns_zero():
    """No routed query means zero boost."""
    boost = _query_intent_record_boost(
        None,
        {"parent_record_type": "page_document"},
        title="anything",
        text="anything",
        primary_url="https://example.com",
        source_preference="secondary",
    )
    assert boost == 0
