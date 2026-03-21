import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.chatbot_answering import _is_grounded_top_hit, answer_chatbot_question, build_arg_parser


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_answer_chatbot_question_returns_structured_family_answer(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:hierid=2|lang=EN|pos=REPORT:2.1",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "latest_observation": {
                    "period": "11.06.25",
                    "value": "1.53",
                    "unit": "% per annum",
                    "series_label": "Base rate",
                },
                "latest_observations": [
                    {
                        "period": "11.06.25",
                        "value": "1.53",
                        "unit": "% per annum",
                        "series_label": "Base rate",
                    },
                    {
                        "period": "11.06.25",
                        "value": "2.65",
                        "unit": "% per annum",
                        "series_label": "Reference rate",
                    },
                ],
                "sources": ["OeNB", "ECB"],
                "release_events": [
                    {"release_date_text": "at the latest 30.06.2026", "reference_text": "June 2026"}
                ],
                "isaweb_dataset": {
                    "source_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.1"
                },
                "isaweb_metadata": {
                    "meta_url": "https://www.oenb.at/isadataservice/meta?hierid=2&lang=EN&pos=REPORT:2.1"
                },
                "source_page": {
                    "url": "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Base-and-Reference-Rates/Base-and-Reference-Rates-of-the-Oesterreichische-Nationalbank.html",
                    "title": "Base and reference rates of the Oesterreichische Nationalbank - Oesterreichische Nationalbank (OeNB)",
                },
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:hierid=2|lang=EN|pos=REPORT:2.1:summary",
                "parent_id": "dataset_family:hierid=2|lang=EN|pos=REPORT:2.1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Dataset family summary.",
                "sources": ["OeNB", "ECB"],
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Base-and-Reference-Rates/Base-and-Reference-Rates-of-the-Oesterreichische-Nationalbank.html"
                ],
                "retrieval_score": 1070,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("aktueller Leitzins", base_dir=tmp_path)

    assert answer["answer_type"] == "dataset_family"
    assert "11.06.25" in answer["answer"]
    assert "Base rate = 1.53 % per annum" in answer["answer"]
    assert "Reference rate = 2.65 % per annum" in answer["answer"]
    assert answer["citations"][0]["url"].startswith("https://www.oenb.at/en/Statistics/")
    assert answer["sources"] == ["OeNB", "ECB"]
    assert answer["release_dates"] == ["at the latest 30.06.2026"]
    assert len(answer["citations"]) == 3
    assert answer["citations"][1]["url"] == "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.1"
    assert "hits" not in answer
    assert "parent_record" not in answer


def test_answer_chatbot_question_returns_not_found_when_no_hit(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"
    _write_jsonl(stats_path, [])
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("vollkommen unbekannte frage", base_dir=tmp_path)

    assert answer["answer_type"] == "not_found"
    assert answer["citations"] == []
    assert "keine passende" in answer["answer"].lower()


def test_answer_chatbot_question_ignores_placeholder_release_dates_and_limits_citations(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:hierid=324|lang=EN|pos=REPORT:3.24.15",
                "title": "Financial Soundness Indicators",
                "latest_observation": {
                    "period": "Q3 25",
                    "value": "19.52",
                    "unit": "in %",
                    "series_label": "Tier 1 capital",
                },
                "sources": ["OeNB"],
                "release_events": [
                    {"release_date_text": "no date available", "reference_text": "n/a"},
                    {"release_date_text": "", "reference_text": "n/a"},
                ],
                "source_page": {
                    "url": "https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions/banks/aggregated-regulatory-capital-requirements-and-liquidity-financial-and-income-statements/financial-soundness-indicators-acc.-imf.html",
                    "title": "Financial Soundness Indicators acc. IMF - Oesterreichische Nationalbank (OeNB)",
                },
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:hierid=324|lang=EN|pos=REPORT:3.24.15:summary",
                "parent_id": "dataset_family:hierid=324|lang=EN|pos=REPORT:3.24.15",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Financial Soundness Indicators",
                "text": "Dataset family summary.",
                "sources": ["OeNB"],
                "reference_urls": [
                    "https://www.oenb.at/one",
                    "https://www.oenb.at/two",
                    "https://www.oenb.at/three",
                    "https://www.oenb.at/four",
                    "https://www.oenb.at/five",
                    "https://www.oenb.at/six",
                ],
                "retrieval_score": 1070,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Financial Soundness Indicators", base_dir=tmp_path)

    assert "Nächste Veröffentlichung" not in answer["answer"]
    assert answer["release_dates"] == []
    assert len(answer["citations"]) == 1


def test_answer_chatbot_question_can_include_debug_payload(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"
    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:hierid=2|lang=EN|pos=REPORT:2.1",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "latest_observation": {"period": "11.06.25", "value": "1.53", "unit": "% per annum"},
                "sources": ["OeNB", "ECB"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/..."},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:hierid=2|lang=EN|pos=REPORT:2.1:summary",
                "parent_id": "dataset_family:hierid=2|lang=EN|pos=REPORT:2.1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Dataset family summary.",
                "sources": ["OeNB", "ECB"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
                "retrieval_score": 1070,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("aktueller Leitzins", base_dir=tmp_path, include_debug=True)

    assert "hits" in answer
    assert "parent_record" in answer


def test_answer_chatbot_question_summarizes_large_multi_series_tables_with_euro_area_focus(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:hierid=10|lang=EN|pos=REPORT:10.4",
                "title": "Key interest rates",
                "latest_observation": {
                    "period": "2025",
                    "value": "2.15",
                    "unit": "%",
                    "series_label": "Euro area",
                },
                "latest_observations": [
                    {"period": "2025", "value": "3.50", "unit": "%", "series_label": "Czech Republic"},
                    {"period": "2025", "value": "1.75", "unit": "%", "series_label": "Denmark"},
                    {"period": "2025", "value": "2.15", "unit": "%", "series_label": "Euro area"},
                    {"period": "2025", "value": "6.50", "unit": "%", "series_label": "Hungary"},
                    {"period": "2025", "value": "0.75", "unit": "%", "series_label": "Japan"},
                    {"period": "2025", "value": "4.00", "unit": "%", "series_label": "Norway"},
                ],
                "sources": ["ECB", "Eurostat"],
                "release_events": [],
                "isaweb_dataset": {
                    "source_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"
                },
                "isaweb_metadata": {
                    "meta_url": "https://www.oenb.at/isawebstat/showMetadatenStAbfrage?lang=EN&report=10.4"
                },
                "source_page": {
                    "url": "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates/international-key-interest-rates.html",
                    "title": "International key interest rates - Oesterreichische Nationalbank (OeNB)",
                },
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:hierid=10|lang=EN|pos=REPORT:10.4:summary",
                "parent_id": "dataset_family:hierid=10|lang=EN|pos=REPORT:10.4",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Dataset family summary.",
                "sources": ["ECB", "Eurostat"],
                "reference_urls": [
                    "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/Euro-Area-Money-Market-Interest-Rates-and-Eurosystem-Interest-Rates/international-key-interest-rates.html"
                ],
                "retrieval_score": 1100,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("aktueller Leitzins", base_dir=tmp_path)

    assert "Euro area = 2.15 %" in answer["answer"]
    assert "weitere Reihen" in answer["answer"]
    assert "Czech Republic = 3.50 %" not in answer["answer"]


def test_build_arg_parser_accepts_base_dir_without_value():
    parser = build_arg_parser()

    args = parser.parse_args(["aktueller Leitzins", "--base-dir"])

    assert args.query == "aktueller Leitzins"
    assert args.base_dir == Path.cwd()


def test_answer_chatbot_question_prefers_gold_family_for_gold_query(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:commodity:gold",
                "title": "Commodity prices - gold",
                "latest_observation": {
                    "period": "2025-03",
                    "value": "2150.4",
                    "unit": "USD",
                    "series_label": "Gold",
                },
                "sources": ["Macrobond"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:commodity:gold:summary",
                "parent_id": "dataset_family:commodity:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Latest observation: 2025-03 = 2150.4 USD. Gold price.",
                "sources": ["Macrobond"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
            {
                "record_type": "dataset_family",
                "id": "dataset_family:rppi",
                "title": "Residential property price index",
                "latest_observation": {"period": "2025", "value": "266.9", "unit": "Index"},
                "sources": ["OeNB"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:rppi:summary",
                "parent_id": "dataset_family:rppi",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Residential property price index",
                "text": "Latest observation: 2025 = 266.9 Index.",
                "sources": ["OeNB"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Wie hoch ist der Goldpreis aktuell?", base_dir=tmp_path)

    assert answer["answer_type"] == "dataset_family"
    assert "Commodity prices - gold" in answer["answer"]
    assert "2150.4 USD" in answer["answer"]


def test_answer_chatbot_question_keeps_deposit_facility_in_monetary_policy_domain(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:key-rates",
                "title": "Key interest rates",
                "latest_observations": [
                    {"period": "2025", "value": "2.15", "unit": "%", "series_label": "Euro area"},
                    {"period": "2025", "value": "4.50", "unit": "%", "series_label": "United States"},
                ],
                "sources": ["ECB"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../international-key-interest-rates.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:key-rates:summary",
                "parent_id": "dataset_family:key-rates",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Latest observation: 2025. Euro area = 2.15 %.",
                "sources": ["ECB"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../international-key-interest-rates.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
            {
                "record_type": "dataset_family",
                "id": "dataset_family:services",
                "title": "Internationaler Dienstleistungsverkehr - Regional",
                "latest_observation": {"period": "2025", "value": "286", "unit": "Mio EUR"},
                "sources": ["OeNB"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=9.2.02"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:services:summary",
                "parent_id": "dataset_family:services",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Internationaler Dienstleistungsverkehr - Regional",
                "text": "Dienstleistungen, Netto, Euroraum 19.",
                "sources": ["OeNB"],
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=9.2.02"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Wie hoch ist der Zinssatz für die Einlagenfazilität?", base_dir=tmp_path)

    assert "Key interest rates" in answer["answer"]
    assert "Euro area = 2.15 %" in answer["answer"]


def test_answer_chatbot_question_returns_split_answer_for_multi_topic_query(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:rppi",
                "title": "Residential property price index",
                "latest_observation": {"period": "2025", "value": "266.9", "unit": "Index"},
                "sources": ["OeNB"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:rppi:summary",
                "parent_id": "dataset_family:rppi",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Residential property price index",
                "text": "Latest observation: 2025 = 266.9 Index.",
                "sources": ["OeNB"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
            {
                "record_type": "dataset_family",
                "id": "dataset_family:gold",
                "title": "Commodity prices - gold",
                "latest_observation": {"period": "2025-03", "value": "2150.4", "unit": "USD"},
                "sources": ["Macrobond"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:gold:summary",
                "parent_id": "dataset_family:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Latest observation: 2025-03 = 2150.4 USD.",
                "sources": ["Macrobond"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"],
                "retrieval_score": 980,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Mich interessieren Immobilienpreise und Gold", base_dir=tmp_path)

    assert "Immobilienpreise" in answer["answer"]
    assert "Gold" in answer["answer"]
    assert len(answer["subanswers"]) == 2


def test_answer_chatbot_question_focuses_gold_row_inside_multi_series_commodity_table(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:commodity-world",
                "title": "World commodity prices",
                "latest_observations": [
                    {"period": "2025", "value": "69.3", "unit": "Crude oil prices", "series_label": "North Sea, Brent FOB"},
                    {"period": "2025", "value": "2150.4", "unit": "USD", "series_label": "Gold"},
                ],
                "sources": ["Macrobond"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../Commodity-Prices/World-Commodity-Prices.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:commodity-world:summary",
                "parent_id": "dataset_family:commodity-world",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "World commodity prices",
                "text": "Latest observation: 2025. Gold = 2150.4 USD; North Sea, Brent FOB = 69.3 Crude oil prices.",
                "sources": ["Macrobond"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../Commodity-Prices/World-Commodity-Prices.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Wie hoch ist der Goldpreis aktuell?", base_dir=tmp_path)

    assert "Gold = 2150.4 USD" in answer["answer"]
    assert "North Sea, Brent FOB = 69.3" not in answer["answer"]


def test_answer_chatbot_question_admits_missing_gold_row_in_materialized_family(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:commodity-world",
                "title": "World commodity prices",
                "latest_observation": {
                    "period": "2025",
                    "value": "69.3",
                    "unit": "Crude oil prices",
                    "series_label": "North Sea, Brent FOB",
                },
                "sources": ["Macrobond"],
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../Commodity-Prices/World-Commodity-Prices.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:commodity-world:summary",
                "parent_id": "dataset_family:commodity-world",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "World commodity prices",
                "text": "Latest observation: 2025 = 69.3 Crude oil prices.",
                "sources": ["Macrobond"],
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../Commodity-Prices/World-Commodity-Prices.html"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    answer = answer_chatbot_question("Wie hoch ist der Goldpreis aktuell?", base_dir=tmp_path)

    assert "kein expliziter Gold-Wert" in answer["answer"]


def test_is_grounded_top_hit_rejects_irrelevant_asset_for_rag_first():
    routing = {
        "strategy": "rag_first",
        "domains": ["financial_education"],
        "entities": ["Taschengeld"],
        "confidence": 0.68,
    }
    hit = {
        "title": "Arbeitsblatt 5 - Euro-Banknoten (PDF, 987 kB)",
        "text": "Asset document: Arbeitsblätter für Volksschulkinder. Male Euro-Banknoten.",
        "reference_urls": [
            "https://finanzbildung.oenb.at/dam/jcr:5deb8953-72ee-4bc6-b8b6-b0cf34d6cecf/AB5_Arbeitsblatt%205_Euro-Banknoten.pdf"
        ],
        "parent_record_type": "asset_document",
    }

    assert not _is_grounded_top_hit(
        "Wie viel Taschengeld soll ich meinen Kindern geben? Sie sind 9 und 14 Jahre alt.",
        routing,
        hit,
    )


def test_is_grounded_top_hit_accepts_structured_dataset_family_hits():
    routing = {
        "strategy": "rag_first",
        "domains": ["reserves_assets"],
        "entities": ["Goldreserven"],
        "confidence": 0.73,
    }
    hit = {
        "title": "I. Official reserve assets and other foreign currency assets (market value)",
        "text": "Gold reserves and other reserve assets.",
        "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1"],
        "parent_record_type": "dataset_family",
    }

    assert _is_grounded_top_hit("Wie viele Goldreserven hat die OeNB?", routing, hit)


def test_is_grounded_top_hit_rejects_asset_hits_for_website_general_routes():
    routing = {
        "strategy": "rag_first",
        "domains": ["website_general"],
        "entities": ["OeNB Women's Forum"],
        "confidence": 0.64,
    }
    hit = {
        "title": "stat 2009 q4 analyse wagner tcm14 143144.pdf",
        "text": "Asset document: Immobilienvermögen der privaten Haushalte.",
        "reference_urls": ["https://www.oenb.at/dam/jcr:7337b987-de8a-444a-9924-acf379d3cd86/stat_2009_q4_analyse_wagner_tcm14-143144.pdf"],
        "parent_record_type": "asset_document",
    }

    assert not _is_grounded_top_hit("Was schreibt die OeNB zu Frauen in Führungsfunktionen?", routing, hit)


def test_answer_chatbot_question_prioritizes_website_release_subanswer(monkeypatch, tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:inflation",
                "title": "Selected inflation indicators",
                "latest_observation": {"period": "2025", "value": "116.3", "unit": "Index", "series_label": "1"},
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:inflation:summary",
                "parent_id": "dataset_family:inflation",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Selected inflation indicators",
                "text": "Latest observation: 2025 = 116.3 Index.",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1"],
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(
        full_path,
        [
            {
                "record_type": "page_document",
                "id": "page_document:release-calendar",
                "title": "Release calendar for inflation statistics",
                "text": "Next release date for inflation statistics.",
                "release_events": [{"release_date_text": "at the latest 30.06.2026", "reference_text": "June 2026"}],
                "source_page": {"url": "https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:page_document:release-calendar:summary",
                "parent_id": "page_document:release-calendar",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Release calendar for inflation statistics",
                "text": "Next release date for inflation statistics.",
                "reference_urls": ["https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"],
                "retrieval_score": 850,
                "retrieval_tier": "primary",
            },
        ],
    )

    def fake_retrieve(*args, **kwargs):
        return {
            "hits": [
                {
                    "id": "chatbot_chunk:dataset_family:inflation:summary",
                    "parent_id": "dataset_family:inflation",
                    "parent_record_type": "dataset_family",
                    "title": "Selected inflation indicators",
                    "text": "Latest observation: 2025 = 116.3 Index.",
                    "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1"],
                    "source_preference": "primary",
                    "match_score": 1800,
                },
                {
                    "id": "chatbot_chunk:page_document:release-calendar:summary",
                    "parent_id": "page_document:release-calendar",
                    "parent_record_type": "page_document",
                    "title": "Release calendar for inflation statistics",
                    "text": "Next release date for inflation statistics.",
                    "reference_urls": ["https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"],
                    "source_preference": "secondary",
                    "match_score": 1750,
                },
            ],
            "confidence": 0.9,
            "routing": {
                "intent": "topic_overview",
                "query_intent": "release_lookup",
                "domains": ["commodity_prices", "website_general"],
                "entities": ["Inflation"],
                "freshness_need": "low",
                "subqueries": [],
                "strategy": "hybrid",
                "confidence": 0.9,
            },
            "subquery_results": [
                {
                    "domain": "commodity_prices",
                    "query": "Inflation",
                    "hits": [
                        {
                            "id": "chatbot_chunk:dataset_family:inflation:summary",
                            "parent_id": "dataset_family:inflation",
                            "parent_record_type": "dataset_family",
                            "title": "Selected inflation indicators",
                            "text": "Latest observation: 2025 = 116.3 Index.",
                            "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1"],
                            "source_preference": "primary",
                            "match_score": 1800,
                        }
                    ],
                },
                {
                    "domain": "website_general",
                    "query": "Wann werden die naechsten Inflationsdaten veroeffentlicht?",
                    "hits": [
                        {
                            "id": "chatbot_chunk:page_document:release-calendar:summary",
                            "parent_id": "page_document:release-calendar",
                            "parent_record_type": "page_document",
                            "title": "Release calendar for inflation statistics",
                            "text": "Next release date for inflation statistics.",
                            "reference_urls": ["https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"],
                            "source_preference": "secondary",
                            "match_score": 1750,
                        }
                    ],
                },
            ],
        }

    monkeypatch.setattr("analysis.chatbot_answering.retrieve_chatbot_knowledge", fake_retrieve)
    monkeypatch.setattr("analysis.chatbot_answering.maybe_run_agentic_search", lambda **kwargs: None)

    answer = answer_chatbot_question("Wann werden die naechsten Inflationsdaten veroeffentlicht?", base_dir=tmp_path)

    assert answer["answer_type"] == "multi_part"
    assert answer["answer"].startswith("Release calendar for inflation statistics.")
    assert "Nächste Veröffentlichung: at the latest 30.06.2026." in answer["answer"]


def test_answer_chatbot_question_prioritizes_website_navigation_subanswer(monkeypatch, tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:bargeld",
                "title": "Cash in circulation",
                "latest_observation": {"period": "2025", "value": "42.0", "unit": "EUR million", "series_label": "Austria"},
                "release_events": [],
                "source_page": {"url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:bargeld:summary",
                "parent_id": "dataset_family:bargeld",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Cash in circulation",
                "text": "Latest observation: 2025 = 42.0 EUR million.",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1"],
                "retrieval_score": 980,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(
        full_path,
        [
            {
                "record_type": "page_document",
                "id": "page_document:bargeld-download",
                "title": "Bargeldumlauf CSV Download",
                "text": "Cash in circulation data can be downloaded as CSV or Excel.",
                "source_page": {"url": "https://www.oenb.at/statistik/bargeld/download-csv.html"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:page_document:bargeld-download:summary",
                "parent_id": "page_document:bargeld-download",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Bargeldumlauf CSV Download",
                "text": "Cash in circulation data can be downloaded as CSV or Excel.",
                "reference_urls": ["https://www.oenb.at/statistik/bargeld/download-csv.html"],
                "retrieval_score": 820,
                "retrieval_tier": "primary",
            },
        ],
    )

    def fake_retrieve(*args, **kwargs):
        return {
            "hits": [
                {
                    "id": "chatbot_chunk:dataset_family:bargeld:summary",
                    "parent_id": "dataset_family:bargeld",
                    "parent_record_type": "dataset_family",
                    "title": "Cash in circulation",
                    "text": "Latest observation: 2025 = 42.0 EUR million.",
                    "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1"],
                    "source_preference": "primary",
                    "match_score": 1700,
                },
                {
                    "id": "chatbot_chunk:page_document:bargeld-download:summary",
                    "parent_id": "page_document:bargeld-download",
                    "parent_record_type": "page_document",
                    "title": "Bargeldumlauf CSV Download",
                    "text": "Cash in circulation data can be downloaded as CSV or Excel.",
                    "reference_urls": ["https://www.oenb.at/statistik/bargeld/download-csv.html"],
                    "source_preference": "secondary",
                    "match_score": 1650,
                },
            ],
            "confidence": 0.86,
            "routing": {
                "intent": "topic_overview",
                "query_intent": "navigation",
                "domains": ["website_general"],
                "entities": ["Bargeldumlauf"],
                "freshness_need": "low",
                "subqueries": [],
                "strategy": "rag_first",
                "confidence": 0.86,
            },
            "subquery_results": [
                {
                    "domain": "commodity_prices",
                    "query": "Bargeldumlauf",
                    "hits": [
                        {
                            "id": "chatbot_chunk:dataset_family:bargeld:summary",
                            "parent_id": "dataset_family:bargeld",
                            "parent_record_type": "dataset_family",
                            "title": "Cash in circulation",
                            "text": "Latest observation: 2025 = 42.0 EUR million.",
                            "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1"],
                            "source_preference": "primary",
                            "match_score": 1700,
                        }
                    ],
                },
                {
                    "domain": "website_general",
                    "query": "Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?",
                    "hits": [
                        {
                            "id": "chatbot_chunk:page_document:bargeld-download:summary",
                            "parent_id": "page_document:bargeld-download",
                            "parent_record_type": "page_document",
                            "title": "Bargeldumlauf CSV Download",
                            "text": "Cash in circulation data can be downloaded as CSV or Excel.",
                            "reference_urls": ["https://www.oenb.at/statistik/bargeld/download-csv.html"],
                            "source_preference": "secondary",
                            "match_score": 1650,
                        }
                    ],
                },
            ],
        }

    monkeypatch.setattr("analysis.chatbot_answering.retrieve_chatbot_knowledge", fake_retrieve)
    monkeypatch.setattr("analysis.chatbot_answering.maybe_run_agentic_search", lambda **kwargs: None)

    answer = answer_chatbot_question("Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?", base_dir=tmp_path)

    assert answer["answer_type"] == "multi_part"
    assert answer["answer"].startswith("Bargeldumlauf CSV Download.")
