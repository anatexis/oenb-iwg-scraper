"""Run an eval fixture against the current OeNB chatbot QA path."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from analysis.knowledge_base_cache import KnowledgeBaseCache
from analysis.rag_answering import run_rag_answering
from analysis.score_chatbot_eval import score_report


def run_chatbot_eval_fixture(
    *,
    fixture_path: Path,
    output_path: Path,
    base_dir: Path | None = None,
    debug: bool = False,
    agentic_enabled: bool | None = None,
    replay_routing_path: Path | None = None,
) -> dict:
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    routing_by_id: dict[str, dict] = {}
    if replay_routing_path is not None:
        replay_report = json.loads(replay_routing_path.read_text(encoding="utf-8"))
        routing_by_id = {
            c["id"]: c["result"]["routing"]
            for c in replay_report.get("cases", [])
            if c.get("result", {}).get("routing")
        }
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
            routed_query=routing_by_id.get(case.get("id")),
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

    if any(case.get("expect") for case in output_cases):
        scored = score_report(report)
        report["summary"]["verdict_counts"] = scored["summary"]["verdict_counts"]
        report["summary"]["by_type"] = scored["summary"]["by_type"]
        report["summary"]["score"] = scored["summary"]["score"]
        verdict_by_id = {c["id"]: c for c in scored["cases"]}
        for case in output_cases:
            scored_case = verdict_by_id.get(case.get("id"))
            if scored_case:
                case["verdict"] = scored_case["verdict"]
                case["verdict_reasons"] = scored_case["reasons"]

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
    parser.add_argument(
        "--replay-routing",
        type=Path,
        default=None,
        help="Reuse routing decisions from a previous report (skips the LLM router)",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    report = run_chatbot_eval_fixture(
        fixture_path=args.fixture,
        output_path=args.output,
        base_dir=args.base_dir,
        debug=args.debug,
        agentic_enabled=args.agentic,
        replay_routing_path=args.replay_routing,
    )
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
