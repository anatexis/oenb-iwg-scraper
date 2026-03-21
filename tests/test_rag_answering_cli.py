import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.rag_answering import run_rag_answering
from analysis.router_demo import run_router_demo


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_run_rag_answering_returns_answer_with_configured_kb(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:key-rates",
                "title": "Key interest rates",
                "latest_observations": [{"period": "2025", "value": "2.15", "unit": "%", "series_label": "Euro area"}],
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
        ],
    )
    _write_jsonl(full_path, [])

    result = run_rag_answering("aktueller Leitzins", base_dir=tmp_path)

    assert "Key interest rates" in result["answer"]


def test_run_rag_answering_can_include_routing_debug_info(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"
    _write_jsonl(stats_path, [])
    _write_jsonl(full_path, [])

    result = run_rag_answering("aktueller Leitzins", base_dir=tmp_path, debug=True)

    assert "routing" in result


def test_run_rag_answering_runs_without_agentic_step(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"
    _write_jsonl(stats_path, [])
    _write_jsonl(full_path, [])

    result = run_rag_answering("unbekannte Frage", base_dir=tmp_path, agentic_enabled=False)

    assert result["answer_type"] == "not_found"


def test_run_router_demo_returns_normalized_route():
    result = run_router_demo("Wie hoch ist der Goldpreis aktuell?")

    assert result["domains"] == ["commodity_prices"]


def test_run_rag_answering_avoids_statistics_hallucination_for_taschengeld_question(tmp_path: Path):
    stats_path = tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    full_path = tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"

    _write_jsonl(
        stats_path,
        [
            {
                "record_type": "dataset_family",
                "id": "dataset_family:cards",
                "title": "Zahlungskartentransaktionen",
                "latest_observation": {"period": "Q4 25", "value": "14,71", "unit": "%"},
                "sources": ["OeNB"],
                "release_events": [],
            },
            {
                "record_type": "chatbot_chunk",
                "id": "chatbot_chunk:dataset_family:cards:summary",
                "parent_id": "dataset_family:cards",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Zahlungskartentransaktionen",
                "text": "Card-not-present statistics.",
                "sources": ["OeNB"],
                "reference_urls": ["https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=5.4.2"],
                "retrieval_score": 1200,
                "retrieval_tier": "primary",
            },
        ],
    )
    _write_jsonl(full_path, [])

    result = run_rag_answering(
        "Wie viel Taschengeld soll ich meinen Kindern geben? Sie sind 9 und 14 Jahre alt.",
        base_dir=tmp_path,
    )

    assert result["answer_type"] == "not_found"
