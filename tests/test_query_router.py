import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.llm.base import LLMProvider
from analysis.query_router import _candidate_from_record, _query_tokens, build_arg_parser, route_query


class StubProvider(LLMProvider):
    def __init__(self, payload: dict):
        super().__init__(provider_name="stub", base_url="http://stub", model="stub")
        self.payload = payload

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(self.payload)

    def invoke_json(self, system_prompt: str, user_prompt: str, schema_hint: str | None = None) -> dict:
        return self.payload


def test_route_query_maps_deposit_facility_question_to_monetary_policy_domain():
    result = route_query("Wie hoch ist der Zinssatz für die Einlagenfazilität?")

    assert result["intent"] == "fact_lookup"
    assert "monetary_policy" in result["domains"]
    assert "interest_rates" in result["domains"]
    assert "Einlagenfazilität" in result["entities"]
    assert result["freshness_need"] == "high"
    assert result["strategy"] == "sql_first"
    assert result["subqueries"] == []


def test_route_query_maps_gold_question_to_commodity_prices():
    result = route_query("Wie hoch ist der Goldpreis aktuell?")

    assert result["intent"] == "fact_lookup"
    assert result["domains"] == ["commodity_prices"]
    assert result["entities"] == ["Goldpreis"]
    assert result["freshness_need"] == "high"
    assert result["strategy"] == "sql_first"


def test_route_query_splits_multi_topic_question_into_subqueries():
    result = route_query("Mich interessieren Immobilienpreise und Gold.")

    assert set(result["domains"]) == {"real_estate", "commodity_prices"}
    assert result["strategy"] == "hybrid"
    assert len(result["subqueries"]) == 2
    assert result["subqueries"][0]["domain"] == "real_estate"
    assert result["subqueries"][1]["domain"] == "commodity_prices"


def test_route_query_uses_llm_fallback_for_unknown_questions():
    provider = StubProvider(
        {
            "intent": "topic_overview",
            "domains": ["corporate_topics"],
            "entities": ["Hackathon"],
            "freshness_need": "low",
            "subqueries": [],
            "strategy": "rag_first",
            "confidence": 0.82,
            "reasoning_hint": "corporate website topic",
        }
    )

    result = route_query("Was gibt es bei der OeNB zum Hackathon?", llm_provider=provider)

    assert result["intent"] == "topic_overview"
    assert result["domains"] == ["corporate_topics"]
    assert result["entities"] == ["Hackathon"]
    assert result["freshness_need"] == "low"
    assert result["strategy"] == "rag_first"
    assert result["confidence"] == 0.82


def test_route_query_maps_corporate_topic_question_to_rag_first():
    result = route_query("Was schreibt die OeNB zu Frauen in Führungsfunktionen?")

    assert result["domains"] == ["corporate_topics"]
    assert result["strategy"] == "rag_first"
    assert result["intent"] == "topic_overview"


def test_route_query_maps_financial_education_question_to_rag_first():
    result = route_query("Wie viel Taschengeld soll ich meinen Kindern geben? Sie sind 9 und 14 Jahre alt.")

    assert result["domains"] == ["financial_education"]
    assert result["strategy"] == "rag_first"
    assert result["intent"] == "topic_overview"


def test_route_query_distinguishes_gold_reserves_from_gold_price():
    result = route_query("Wie viele Goldreserven hat die OeNB?")

    assert result["domains"] == ["reserves_assets"]
    assert result["strategy"] == "hybrid"
    assert "Goldreserven" in result["entities"]


def test_route_query_can_keep_specific_and_generic_gold_intents_when_both_are_asked():
    result = route_query("Wie viele Goldreserven hat die OeNB und wie hoch ist der Goldpreis?")

    assert result["strategy"] == "hybrid"
    assert set(result["domains"]) == {"reserves_assets", "commodity_prices"}
    assert len(result["subqueries"]) == 2


def test_route_query_uses_candidate_records_for_corporate_topic_routing():
    candidates = [
        {
            "id": "page_document:frauen-fuehrungsfunktionen",
            "title": "Frauen in Führungsfunktionen bei der OeNB",
            "record_type": "page_document",
            "domains": ["corporate_topics"],
            "source_preference": "secondary",
            "score": 900,
            "reference_url": "https://www.oenb.at/ueber-uns/frauen-in-fuehrungsfunktionen.html",
            "text_preview": "Die OeNB berichtet über Frauen in Führungsfunktionen.",
        }
    ]

    result = route_query(
        "Was schreibt die OeNB zu Frauen in Führungsfunktionen?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["domains"] == ["corporate_topics"]
    assert result["strategy"] == "rag_first"
    assert result["confidence"] >= 0.7


def test_route_query_uses_candidate_records_to_split_gold_reserves_and_gold_price():
    candidates = [
        {
            "id": "dataset_family:reserve-assets",
            "title": "Official reserve assets and other foreign currency assets",
            "record_type": "dataset_family",
            "domains": ["reserves_assets"],
            "source_preference": "primary",
            "score": 980,
            "reference_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1",
            "text_preview": "gold (including gold deposits and gold swapped)",
        },
        {
            "id": "dataset_family:commodity-gold",
            "title": "World commodity prices - Gold",
            "record_type": "dataset_family",
            "domains": ["commodity_prices"],
            "source_preference": "primary",
            "score": 930,
            "reference_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.9",
            "text_preview": "Gold price in USD.",
        },
    ]

    result = route_query(
        "Wie viele Goldreserven hat die OeNB und wie hoch ist der Goldpreis?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["strategy"] == "hybrid"
    assert set(result["domains"]) == {"reserves_assets", "commodity_prices"}


def test_build_arg_parser_accepts_query_argument():
    args = build_arg_parser().parse_args(["Wie hoch ist der Goldpreis aktuell?"])

    assert args.query == "Wie hoch ist der Goldpreis aktuell?"


def test_candidate_from_record_uses_source_text_raw_lists_for_grounded_structured_matches():
    record = {
        "id": "dataset_family:reserve-assets",
        "record_type": "dataset_family",
        "title": "I. Official reserve assets and other foreign currency assets (market value)",
        "source_text_raw": [
            "A. Official reserve assets 50,359 EUR million (4) gold (including gold deposits and gold swapped) 38,385"
        ],
        "source_page": {
            "url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1",
            "title": "DATA - I. Official reserve assets and other foreign currency assets (market value)",
        },
        "isaweb_dataset": {
            "source_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1"
        },
    }

    candidate = _candidate_from_record(
        record,
        query="Wie viele Goldreserven hat die OeNB?",
        tokens=_query_tokens("Wie viele Goldreserven hat die OeNB?"),
        source_preference="primary",
    )

    assert candidate is not None
    assert candidate["reference_url"] == "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1"


def test_candidate_from_record_rejects_generic_preview_only_matches():
    record = {
        "id": "page:bargeld",
        "record_type": "page_document",
        "title": "Bargeld - Oesterreichische Nationalbank (OeNB)",
        "url": "https://www.oenb.at/bargeld.html",
        "text_content": "Was ist Bargeld? Welche Stückelungen gibt es bei Euro-Banknoten und Münzen?",
    }

    candidate = _candidate_from_record(
        record,
        query="Warum hat die OeNB eine Kunstsammlung? Was ist das wertvollste Stück?",
        tokens=_query_tokens("Warum hat die OeNB eine Kunstsammlung? Was ist das wertvollste Stück?"),
        source_preference="secondary",
    )

    assert candidate is None


def test_route_query_prefers_query_aligned_domain_when_candidate_has_multiple_domains():
    candidates = [
        {
            "id": "page:goldreserven",
            "title": "Gold-Reserven - Oesterreichische Nationalbank (OeNB)",
            "record_type": "page_document",
            "domains": ["commodity_prices", "reserves_assets"],
            "source_preference": "secondary",
            "score": 465,
            "reference_url": "https://www.oenb.at/Barrierefreiheit/leicht-lesen/goldreserven.html",
            "text_preview": "Gold-Reserven. Die OeNB kümmert sich um die österreichischen Gold-Reserven.",
        }
    ]

    result = route_query(
        "Wie viele Goldreserven hat die OeNB?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["domains"] == ["reserves_assets"]


def test_route_query_falls_back_to_general_website_for_low_confidence_rag_candidates():
    candidates = [
        {
            "id": "page:kindergarten-evaluation",
            "title": "Evaluation of the pilot project for kindergartens “Geldwert – Wertvoll” - OeNB Finanzbildung",
            "record_type": "page_document",
            "domains": ["financial_education"],
            "source_preference": "secondary",
            "score": 125,
            "reference_url": "https://finanzbildung.oenb.at/en/insights-evaluation/Projekte/evaluation-kindergarten.html",
            "text_preview": "Evaluation of the pilot project for kindergartens “Geldwert – Wertvoll”.",
        }
    ]

    result = route_query(
        "Warum hat die OeNB eine Kunstsammlung? Was ist das wertvollste Stück?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["domains"] == ["website_general"]
    assert result["entities"] == []


def test_route_query_marks_isaweb_as_website_explanation_query():
    result = route_query("Was ist ISAweb und wie kann ich damit Daten abrufen?", llm_provider=None, candidate_records=[])

    assert result["domains"] == ["website_general"]
    assert result["strategy"] == "rag_first"
    assert "ISAweb" in result["entities"]


def test_route_query_routes_inflation_release_questions_to_stats_and_website():
    result = route_query("Wann werden die naechsten Inflationsdaten veroeffentlicht?", llm_provider=None, candidate_records=[])

    assert set(result["domains"]) == {"commodity_prices", "website_general"}
    assert result["strategy"] == "hybrid"


def test_route_query_routes_savings_rate_table_navigation_to_interest_rates_and_website():
    result = route_query("Wo finde ich die Tabelle zu Sparzinsen?", llm_provider=None, candidate_records=[])

    assert set(result["domains"]) == {"interest_rates", "website_general"}
    assert result["strategy"] == "hybrid"


def test_route_query_keeps_cash_in_circulation_download_questions_on_website_navigation():
    result = route_query("Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?", llm_provider=None, candidate_records=[])

    assert result["domains"] == ["website_general"]
    assert result["strategy"] == "rag_first"
    assert "Bargeldumlauf" in result["entities"]


def test_route_query_routes_bank_health_questions_to_financial_soundness():
    result = route_query("Wie geht es den oesterreichischen Banken?", llm_provider=None, candidate_records=[])

    assert result["domains"] == ["financial_soundness"]
    assert result["strategy"] == "hybrid"
    assert "Oesterreichische Banken" in result["entities"]


def test_route_query_exposes_release_lookup_as_generic_query_intent():
    result = route_query("Wann werden die naechsten Inflationsdaten veroeffentlicht?", llm_provider=None, candidate_records=[])

    assert result["query_intent"] == "release_lookup"


def test_route_query_exposes_navigation_as_generic_query_intent():
    result = route_query("Wo finde ich eine Zeitreihe zu Wohnbaukreditzinsen?", llm_provider=None, candidate_records=[])

    assert result["query_intent"] == "navigation"


def test_route_query_exposes_explanation_as_generic_query_intent():
    result = route_query("Was misst der Wohnimmobilienpreisindex genau?", llm_provider=None, candidate_records=[])

    assert result["query_intent"] == "explanation"


def test_route_query_exposes_trend_as_generic_query_intent():
    result = route_query(
        "Wie hat sich die Inflation in Oesterreich in den letzten 12 Monaten entwickelt?",
        llm_provider=None,
        candidate_records=[],
    )

    assert result["query_intent"] == "trend_over_time"


def test_route_query_classifies_release_paraphrases_generically():
    queries = [
        "Wann ist die naechste Veroeffentlichung zum Verbraucherpreisindex?",
        "Zu welchem Termin erscheinen die naechsten FSI-Daten?",
    ]

    for query in queries:
        result = route_query(query, llm_provider=None, candidate_records=[])
        assert result["query_intent"] == "release_lookup"


def test_route_query_classifies_navigation_paraphrases_generically():
    queries = [
        "Auf welcher Seite finde ich die Tabelle zu Wohnbaukreditzinsen?",
        "Kann ich mir den Verbraucherpreisindex irgendwo als Zeitreihe herunterladen?",
    ]

    for query in queries:
        result = route_query(query, llm_provider=None, candidate_records=[])
        assert result["query_intent"] == "navigation"


def test_route_query_classifies_statistical_explanations_generically():
    queries = [
        "Was misst der Verbraucherpreisindex genau?",
        "Wie funktioniert der Wohnimmobilienpreisindex?",
    ]

    for query in queries:
        result = route_query(query, llm_provider=None, candidate_records=[])
        assert result["query_intent"] == "explanation"


def test_route_query_classifies_trend_paraphrases_generically():
    queries = [
        "Wie hat sich der Verbraucherpreisindex in den letzten Jahren entwickelt?",
        "Wie war der Trend bei den Immobilienpreisen in Oesterreich?",
    ]

    for query in queries:
        result = route_query(query, llm_provider=None, candidate_records=[])
        assert result["query_intent"] == "trend_over_time"


def test_route_query_rejects_clearly_out_of_scope_weather_question():
    result = route_query("Wie wird das Wetter morgen in Wien?", llm_provider=None, candidate_records=[])

    assert result["strategy"] == "reject_or_clarify"
    assert result["domains"] == ["website_general"]


def test_route_query_rejects_clearly_out_of_scope_sports_question():
    result = route_query("Wer hat die Champions League 2013 gewonnen?", llm_provider=None, candidate_records=[])

    assert result["strategy"] == "reject_or_clarify"
    assert result["domains"] == ["website_general"]


def test_route_query_keeps_statistical_release_questions_away_from_financial_education_candidates():
    candidates = [
        {
            "id": "page:fin-ed-pdf",
            "title": "Arbeitsblatt Euro-Banknoten",
            "record_type": "page_document",
            "domains": ["financial_education"],
            "source_preference": "secondary",
            "score": 180,
            "reference_url": "https://finanzbildung.oenb.at/arbeitsblatt-euro-banknoten.pdf",
            "text_preview": "Unterrichtsmaterial zu Euro-Banknoten und Finanzbildung.",
        }
    ]

    result = route_query(
        "Wann werden die naechsten Inflationsdaten veroeffentlicht?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert "financial_education" not in result["domains"]
    assert set(result["domains"]) == {"commodity_prices", "website_general"}


def test_route_query_rejects_clearly_out_of_scope_question_even_with_candidates():
    candidates = [
        {
            "id": "dataset_family:vienna-house-prices",
            "title": "Immobilienpreisindex Wien, 2000=100",
            "record_type": "dataset_family",
            "domains": ["real_estate"],
            "source_preference": "primary",
            "score": 220,
            "reference_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?report=7.1",
            "text_preview": "Residential property price index for Vienna.",
        }
    ]

    result = route_query(
        "Wie wird das Wetter morgen in Wien?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["strategy"] == "reject_or_clarify"
    assert result["domains"] == ["website_general"]


def test_route_query_keeps_exact_dataset_titles_from_being_marked_out_of_scope():
    candidates = [
        {
            "id": "dataset_family:fsi",
            "title": "Financial Soundness Indicators",
            "record_type": "dataset_family",
            "domains": ["financial_soundness"],
            "source_preference": "primary",
            "score": 910,
            "reference_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",
            "text_preview": "Tier 1 capital and other financial soundness indicators.",
        }
    ]

    result = route_query(
        "Financial Soundness Indicators",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["strategy"] != "reject_or_clarify"
    assert result["domains"] == ["financial_soundness"]


def test_route_query_keeps_website_fallback_for_generic_tool_navigation_when_candidates_are_statistical():
    candidates = [
        {
            "id": "dataset_family:fsi",
            "title": "Financial Soundness Indicators",
            "record_type": "dataset_family",
            "domains": ["financial_soundness"],
            "source_preference": "primary",
            "score": 420,
            "reference_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",
            "text_preview": "ISAweb dataset and report access.",
        }
    ]

    result = route_query(
        "Was ist ISAweb und wie kann ich damit Daten abrufen?",
        llm_provider=None,
        candidate_records=candidates,
    )

    assert result["domains"] == ["website_general"]
    assert result["strategy"] == "rag_first"
