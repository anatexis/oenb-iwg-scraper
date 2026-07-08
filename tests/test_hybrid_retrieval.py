import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.hybrid_retrieval import retrieve_hybrid


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_retrieve_hybrid_prefers_structured_family_chunks_within_same_domain(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:10.4",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Key interest rates",
                "text": "Latest observation: 2025. Euro area = 2.15 %.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=10.4"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:page:rates-overview",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Interest rates overview page",
                "text": "General page about current rates.",
                "retrieval_score": 600,
                "retrieval_tier": "secondary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../interest-rates-overview.html"],
            },
        ],
    )
    _write_jsonl(secondary_path, [])

    result = retrieve_hybrid(
        "Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
    )

    assert result["hits"][0]["id"] == "stats:family:10.4"
    assert result["confidence"] > 0
    assert result["routing"]["domains"] == ["monetary_policy", "interest_rates"]


def test_retrieve_hybrid_merges_subquery_results_without_duplicates(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

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
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../real-estate/residential-property-price-index.html"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Gold price in EUR.",
                "retrieval_score": 980,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:gold",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Commodity prices - gold",
                "text": "Gold price in EUR.",
                "retrieval_score": 980,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/.../commodity-prices/gold.html"],
            },
        ],
    )
    _write_jsonl(secondary_path, [])

    result = retrieve_hybrid(
        "Mich interessieren Immobilienpreise und Gold",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
    )

    assert {hit["id"] for hit in result["hits"][:2]} == {"stats:family:rppi", "stats:family:gold"}
    assert len(result["subquery_results"]) == 2


def test_retrieve_hybrid_exposes_zero_confidence_for_empty_hits(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"
    _write_jsonl(primary_path, [])
    _write_jsonl(secondary_path, [])

    result = retrieve_hybrid(
        "Vollkommen unbekannte Anfrage",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
    )

    assert result["hits"] == []
    assert result["confidence"] == 0.0


def test_retrieve_hybrid_prefers_full_site_for_rag_first_routes(tmp_path: Path):
    stats_path = tmp_path / "stats.jsonl"
    full_path = tmp_path / "full.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:atm",
                "parent_id": "dataset_family:atm",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Automated Teller Machines (ATMs)",
                "text": "ATM statistics.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.4.1"],
            }
        ],
    )
    _write_jsonl(
        full_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:page:art-collection",
                "parent_id": "page_document:art-collection",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "The OeNB art collection",
                "text": "The OeNB art collection explains why the bank has a collection.",
                "retrieval_score": 400,
                "retrieval_tier": "secondary",
                "reference_urls": ["https://www.oenb.at/en/About-Us/art-collection.html"],
            }
        ],
    )

    result = retrieve_hybrid(
        "Warum hat die OeNB eine Kunstsammlung?",
        primary_path=stats_path,
        secondary_path=full_path,
        limit=5,
        routed_query={
            "intent": "topic_overview",
            "domains": ["corporate_topics"],
            "entities": ["Kunstsammlung"],
            "freshness_need": "low",
            "subqueries": [],
            "strategy": "rag_first",
            "confidence": 0.8,
            "reasoning_hint": "corporate site question",
        },
    )

    assert result["hits"][0]["id"] == "full:page:art-collection"
    assert result["routing"]["strategy"] == "rag_first"


def test_retrieve_hybrid_routes_from_kb_candidates_without_explicit_routed_query(tmp_path: Path):
    stats_path = tmp_path / "stats.jsonl"
    full_path = tmp_path / "full.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:reserve-assets",
                "title": "Official reserve assets and other foreign currency assets",
                "source_page": {"url": "https://www.oenb.at/en/Statistics/.../reserve-assets.html"},
                "isaweb_dataset": {"source_url": "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1"},
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:reserve-assets:summary",
                "parent_id": "dataset_family:reserve-assets",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Official reserve assets and other foreign currency assets",
                "text": "gold (including gold deposits and gold swapped) = 38,385 EUR million.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=11.1"],
            },
        ],
    )
    _write_jsonl(
        full_path,
        [
            {
                "record_type": "page_document",
                "id": "page_document:art-collection",
                "title": "The OeNB art collection",
                "source_page": {"url": "https://www.oenb.at/en/About-Us/art-collection.html"},
                "text": "The OeNB art collection.",
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:page_document:art-collection:summary",
                "parent_id": "page_document:art-collection",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "The OeNB art collection",
                "text": "The OeNB art collection explains why the bank has a collection.",
                "retrieval_score": 450,
                "retrieval_tier": "secondary",
                "reference_urls": ["https://www.oenb.at/en/About-Us/art-collection.html"],
            },
        ],
    )

    result = retrieve_hybrid(
        "Warum hat die OeNB eine Kunstsammlung?",
        primary_path=stats_path,
        secondary_path=full_path,
        limit=5,
    )

    assert result["routing"]["domains"] == ["corporate_topics"]
    assert result["routing"]["strategy"] == "rag_first"
    assert result["hits"][0]["id"] == "chatbot_chunk:page_document:art-collection:summary"


def test_retrieve_hybrid_rejects_out_of_scope_route_without_hits(tmp_path: Path):
    stats_path = tmp_path / "stats.jsonl"
    full_path = tmp_path / "full.jsonl"
    _write_jsonl(stats_path, [])
    _write_jsonl(full_path, [])

    result = retrieve_hybrid(
        "Wie viel Taschengeld soll ich meinen Kindern geben?",
        primary_path=stats_path,
        secondary_path=full_path,
        limit=5,
        routed_query={
            "intent": "topic_overview",
            "domains": ["financial_education"],
            "entities": ["Taschengeld"],
            "freshness_need": "low",
            "subqueries": [],
            "strategy": "reject_or_clarify",
            "confidence": 0.6,
            "reasoning_hint": "needs dedicated financial education handling",
        },
    )

    assert result["hits"] == []
    assert result["routing"]["strategy"] == "reject_or_clarify"


def test_retrieve_hybrid_adds_website_subquery_for_release_lookup_domains(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:inflation",
                "parent_id": "dataset_family:inflation",
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
                "id": "full:release-calendar",
                "parent_id": "page_document:release-calendar",
                "parent_record_type": "page_document",
                "chunk_kind": "page_summary",
                "title": "Release calendar for inflation statistics",
                "text": "Next release date for inflation statistics.",
                "retrieval_score": 850,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/releasekalender/showReleaseForReport?lang=EN&report=6.1"],
            }
        ],
    )

    result = retrieve_hybrid(
        "Wann werden die naechsten Inflationsdaten veroeffentlicht?",
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
            "confidence": 0.8,
            "reasoning_hint": "release lookup",
        },
    )

    assert [item["domain"] for item in result["subquery_results"]] == ["website_general", "commodity_prices"]


def test_retrieve_hybrid_adds_website_subquery_for_navigation_domains(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:bargeld",
                "parent_id": "dataset_family:bargeld",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Cash in circulation",
                "text": "Latest observation: 2025 = 42.0 EUR million.",
                "retrieval_score": 980,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=5.1"],
            }
        ],
    )
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:bargeld-download",
                "parent_id": "page_document:bargeld-download",
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

    result = retrieve_hybrid(
        "Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?",
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
            "confidence": 0.8,
            "reasoning_hint": "navigation lookup",
        },
    )

    assert result["hits"][0]["id"] == "full:bargeld-download"


def test_retrieve_hybrid_splits_comparison_into_subject_subqueries(tmp_path: Path):
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"
    _write_jsonl(primary_path, [])
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:hvpi",
                "parent_id": "page_document:hvpi",
                "parent_record_type": "page_document",
                "title": "HVPI - Harmonisierter Verbraucherpreisindex",
                "text": "Der HVPI ist der europaeisch harmonisierte Preisindex.",
                "retrieval_score": 100,
                "reference_urls": ["https://www.oenb.at/statistik/hvpi.html"],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "full:vpi",
                "parent_id": "page_document:vpi",
                "parent_record_type": "page_document",
                "title": "VPI - Verbraucherpreisindex",
                "text": "Der VPI ist der nationale oesterreichische Preisindex.",
                "retrieval_score": 100,
                "reference_urls": ["https://www.oenb.at/statistik/vpi.html"],
            },
        ],
    )

    result = retrieve_hybrid(
        "Was ist der Unterschied zwischen HVPI und VPI?",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
        routed_query={
            "intent": "comparison",
            "query_intent": "comparison",
            "domains": ["commodity_prices"],
            "entities": [],
            "subqueries": [],
            "strategy": "hybrid",
            "confidence": 0.6,
        },
    )

    # One subquery per compared subject, searching for that subject term.
    assert [item["query"] for item in result["subquery_results"]] == ["HVPI", "VPI"]
    hit_ids = {h["id"] for h in result["hits"]}
    assert {"full:hvpi", "full:vpi"} <= hit_ids


def test_retrieve_hybrid_splits_comparison_even_when_router_says_topic_overview(tmp_path: Path):
    # The LLM router often mislabels "Was unterscheidet X von Y" as
    # topic_overview. The lexical subject extractor is authoritative.
    primary_path = tmp_path / "stats.jsonl"
    secondary_path = tmp_path / "full.jsonl"
    _write_jsonl(primary_path, [])
    _write_jsonl(
        secondary_path,
        [
            {
                "record_type": "chatbot_chunk", "id": "full:fdi",
                "parent_id": "pd:fdi", "parent_record_type": "page_document",
                "title": "Direktinvestitionen", "text": "Direktinvestitionen sind langfristig.",
                "retrieval_score": 100, "reference_urls": ["https://www.oenb.at/statistik/direktinvestitionen.html"],
            },
            {
                "record_type": "chatbot_chunk", "id": "full:portfolio",
                "parent_id": "pd:portfolio", "parent_record_type": "page_document",
                "title": "Portfolioinvestitionen", "text": "Portfolioinvestitionen sind Wertpapiere.",
                "retrieval_score": 100, "reference_urls": ["https://www.oenb.at/statistik/portfolioinvestitionen.html"],
            },
        ],
    )

    result = retrieve_hybrid(
        "Was unterscheidet Direktinvestitionen von Portfolioinvestitionen?",
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=5,
        routed_query={
            "intent": "topic_overview", "query_intent": "topic_overview",
            "domains": ["external_sector"], "entities": [], "subqueries": [],
            "strategy": "hybrid", "confidence": 0.5,
        },
    )
    assert [item["query"] for item in result["subquery_results"]] == [
        "Direktinvestitionen", "Portfolioinvestitionen",
    ]
    assert result["routing"]["query_intent"] == "comparison"
