"""Tests for replaying stored routing decisions without an LLM router."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.chatbot_answering import answer_chatbot_question
from analysis.run_chatbot_eval import run_chatbot_eval_fixture

NAV_ROUTING = {
    "intent": "topic_overview",
    "query_intent": "navigation",
    "domains": ["website_general"],
    "entities": [],
    "freshness_need": "low",
    "subqueries": [],
    "strategy": "rag_first",
    "confidence": 0.25,
    "reasoning_hint": "replayed",
}


def _write_kb(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def _page_chunk(chunk_id, title, url):
    return {
        "record_type": "chatbot_chunk",
        "id": chunk_id,
        "parent_id": f"parent:{chunk_id}",
        "parent_record_type": "page_document",
        "title": title,
        "text": f"{title} Inhalt der Seite.",
        "reference_urls": [url],
        "retrieval_score": 100,
    }


def test_answer_chatbot_question_uses_injected_routing_without_calling_router(
    tmp_path, monkeypatch
):
    primary = tmp_path / "stats.jsonl"
    secondary = tmp_path / "site.jsonl"
    _write_kb(primary, [])
    _write_kb(
        secondary,
        [_page_chunk("chunk:1", "Statistik", "https://www.oenb.at/Statistik.html")],
    )

    def explode(*args, **kwargs):
        raise AssertionError("route_query must not be called during replay")

    monkeypatch.setattr("analysis.hybrid_retrieval.route_query", explode)

    result = answer_chatbot_question(
        "Wo finde ich die Statistik-Hauptseite?",
        base_dir=tmp_path,
        primary_path=primary,
        secondary_path=secondary,
        routed_query=NAV_ROUTING,
    )
    assert result["answer_type"] != "not_found"


def test_run_chatbot_eval_replays_routing_from_previous_report(tmp_path, monkeypatch):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps([{"id": "nav-1", "type": "NAV", "query": "Wo ist die Statistik?"}]),
        encoding="utf-8",
    )
    replay_path = tmp_path / "old_report.json"
    replay_path.write_text(
        json.dumps(
            {"cases": [{"id": "nav-1", "result": {"routing": NAV_ROUTING}}]}
        ),
        encoding="utf-8",
    )
    seen = {}

    def fake_run_rag_answering(query, *, routed_query=None, **kwargs):
        seen["routed_query"] = routed_query
        return {"query": query, "answer_type": "not_found", "answer": None}

    monkeypatch.setattr("analysis.run_chatbot_eval.run_rag_answering", fake_run_rag_answering)

    run_chatbot_eval_fixture(
        fixture_path=fixture_path,
        output_path=tmp_path / "report.json",
        base_dir=tmp_path,
        replay_routing_path=replay_path,
    )
    assert seen["routed_query"] == NAV_ROUTING
