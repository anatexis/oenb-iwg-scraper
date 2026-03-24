import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.query_router import route_query


def test_chatbot_eval_regressions_cover_expected_domains():
    fixture_path = Path(__file__).parent / "fixtures" / "chatbot_eval_questions.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in cases:
        result = route_query(case["query"])
        assert set(case["expected_domains"]).issubset(set(result["domains"])), case["query"]
