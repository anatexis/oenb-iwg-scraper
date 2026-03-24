"""Run an eval fixture against the current OeNB chatbot QA path."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from analysis.knowledge_base_cache import KnowledgeBaseCache
from analysis.rag_answering import run_rag_answering


def run_chatbot_eval_fixture(
    *,
    fixture_path: Path,
    output_path: Path,
    base_dir: Path | None = None,
    debug: bool = False,
    agentic_enabled: bool | None = None,
) -> dict:
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    output_cases: list[dict] = []
    answer_types: Counter[str] = Counter()
    failure_layers: Counter[str] = Counter()
    knowledge_base_cache = KnowledgeBaseCache()

    for case in cases:
        result = run_rag_answering(
            case["query"],
            base_dir=base_dir,
            debug=debug,
            agentic_enabled=agentic_enabled,
            knowledge_base_cache=knowledge_base_cache,
        )
        output_cases.append(
            {
                **case,
                "result": result,
            }
        )
        answer_types.update([str(result.get("answer_type") or "unknown")])
        failure_layers.update([str(case.get("primary_failure_layer") or "unknown")])

    report = {
        "fixture_path": str(fixture_path),
        "base_dir": str(base_dir or Path.cwd()),
        "summary": {
            "total_cases": len(output_cases),
            "answer_type_counts": dict(answer_types),
            "failure_layer_counts": dict(failure_layers),
        },
        "cases": output_cases,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an OeNB chatbot eval fixture")
    parser.add_argument("fixture", type=Path, help="Path to eval fixture JSON")
    parser.add_argument("output", type=Path, help="Path to output report JSON")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Worktree root containing data/")
    parser.add_argument("--debug", action="store_true", help="Include routing/retrieval debug data")
    parser.add_argument("--agentic", action="store_true", help="Enable selective live ISAweb lookup")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    report = run_chatbot_eval_fixture(
        fixture_path=args.fixture,
        output_path=args.output,
        base_dir=args.base_dir,
        debug=args.debug,
        agentic_enabled=args.agentic,
    )
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
