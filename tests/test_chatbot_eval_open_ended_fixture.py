import json
from collections import Counter
from pathlib import Path


def test_open_ended_eval_fixture_has_required_fields_and_coverage():
    fixture_path = Path(__file__).parent / "fixtures" / "chatbot_eval_open_ended.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert len(cases) >= 12

    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))

    required_fields = {
        "id",
        "query",
        "intent_family",
        "expected_domains",
        "expected_strategy",
        "expected_answer_mode",
        "current_observation",
        "primary_failure_layer",
        "notes",
    }
    allowed_layers = {"routing", "retrieval", "answering", "coverage", "unknown"}
    allowed_strategies = {"sql_first", "rag_first", "hybrid", "reject_or_clarify"}

    for case in cases:
        assert required_fields.issubset(case)
        assert case["expected_domains"]
        assert case["expected_strategy"] in allowed_strategies
        assert case["primary_failure_layer"] in allowed_layers

    layer_counts = Counter(case["primary_failure_layer"] for case in cases)
    assert layer_counts["routing"] >= 1
    assert layer_counts["retrieval"] >= 1
    assert layer_counts["answering"] >= 1
    assert layer_counts["coverage"] >= 1
