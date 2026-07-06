import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.run_chatbot_eval import run_chatbot_eval_fixture


def test_run_chatbot_eval_fixture_executes_cases_and_writes_summary(tmp_path, monkeypatch):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "query": "Wie hoch ist der Leitzins?",
                    "intent_family": "structured_rate_lookup",
                    "expected_domains": ["interest_rates"],
                    "expected_strategy": "sql_first",
                    "expected_answer_mode": "current_structured_rate",
                    "current_observation": "good",
                    "primary_failure_layer": "unknown",
                    "notes": "first case",
                },
                {
                    "id": "case-2",
                    "query": "Was kann ich mir im Geldmuseum anschauen?",
                    "intent_family": "website_visitor_information",
                    "expected_domains": ["website_general"],
                    "expected_strategy": "rag_first",
                    "expected_answer_mode": "visitor_information",
                    "current_observation": "bad",
                    "primary_failure_layer": "retrieval",
                    "notes": "second case",
                },
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"

    def fake_run_rag_answering(query, *, base_dir=None, debug=False, agentic_enabled=None, knowledge_base_cache=None, routed_query=None):
        return {
            "query": query,
            "answer_type": "dataset_family" if "Leitzins" in query else "not_found",
            "answer": f"answer for {query}",
            "routing": {"domains": ["interest_rates"] if "Leitzins" in query else ["website_general"]},
        }

    monkeypatch.setattr("analysis.run_chatbot_eval.run_rag_answering", fake_run_rag_answering)

    report = run_chatbot_eval_fixture(
        fixture_path=fixture_path,
        output_path=output_path,
        base_dir=tmp_path,
        debug=True,
    )

    assert output_path.exists()
    assert report["summary"]["total_cases"] == 2
    assert report["summary"]["answer_type_counts"] == {"dataset_family": 1, "not_found": 1}
    assert report["summary"]["failure_layer_counts"] == {"unknown": 1, "retrieval": 1}
    assert report["cases"][0]["result"]["query"] == "Wie hoch ist der Leitzins?"
    assert report["cases"][1]["result"]["answer_type"] == "not_found"

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["summary"]["total_cases"] == 2


def test_run_chatbot_eval_fixture_reuses_single_knowledge_base_cache(tmp_path, monkeypatch):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "query": "q1",
                    "intent_family": "structured_rate_lookup",
                    "expected_domains": ["interest_rates"],
                    "expected_strategy": "sql_first",
                    "expected_answer_mode": "current_structured_rate",
                    "current_observation": "good",
                    "primary_failure_layer": "unknown",
                    "notes": "first case",
                },
                {
                    "id": "case-2",
                    "query": "q2",
                    "intent_family": "structured_rate_lookup",
                    "expected_domains": ["interest_rates"],
                    "expected_strategy": "sql_first",
                    "expected_answer_mode": "current_structured_rate",
                    "current_observation": "good",
                    "primary_failure_layer": "unknown",
                    "notes": "second case",
                },
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"
    seen_cache_ids: list[int] = []

    def fake_run_rag_answering(
        query, *, base_dir=None, debug=False, agentic_enabled=None, knowledge_base_cache=None, routed_query=None
    ):
        seen_cache_ids.append(id(knowledge_base_cache))
        return {
            "query": query,
            "answer_type": "not_found",
            "answer": f"answer for {query}",
        }

    monkeypatch.setattr("analysis.run_chatbot_eval.run_rag_answering", fake_run_rag_answering)

    run_chatbot_eval_fixture(
        fixture_path=fixture_path,
        output_path=output_path,
        base_dir=tmp_path,
        debug=False,
    )

    assert len(seen_cache_ids) == 2
    assert seen_cache_ids[0] != id(None)
    assert seen_cache_ids[0] == seen_cache_ids[1]


def test_run_chatbot_eval_fixture_scores_cases_with_expect_blocks(tmp_path, monkeypatch):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "id": "nav-1",
                    "type": "NAV",
                    "query": "Wo finde ich Statistik?",
                    "expect": {"url_patterns": ["/Statistik/"], "keywords_any": ["Statistik"]},
                },
                {
                    "id": "ood-1",
                    "type": "OOD",
                    "query": "Zimmerpflanze?",
                    "expect": {"reject": True},
                },
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"

    def fake_run_rag_answering(query, *, base_dir=None, debug=False, agentic_enabled=None, knowledge_base_cache=None, routed_query=None):
        if "Statistik" in query:
            return {
                "query": query,
                "answer_type": "page_document",
                "answer": "Die Statistik-Hauptseite.",
                "citations": [{"url": "https://www.oenb.at/Statistik/"}],
            }
        return {"query": query, "answer_type": "not_found", "answer": None}

    monkeypatch.setattr("analysis.run_chatbot_eval.run_rag_answering", fake_run_rag_answering)

    report = run_chatbot_eval_fixture(
        fixture_path=fixture_path,
        output_path=output_path,
        base_dir=tmp_path,
    )

    assert report["summary"]["verdict_counts"] == {"pass": 2}
    assert report["summary"]["score"] == 1.0
    assert report["cases"][0]["verdict"] == "pass"
