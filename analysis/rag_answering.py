"""Stable CLI entry point for routed hybrid RAG answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.chatbot_answering import answer_chatbot_question
from analysis.runtime_config import load_runtime_config


def run_rag_answering(
    query: str,
    *,
    base_dir: Path | None = None,
    debug: bool = False,
    agentic_enabled: bool | None = None,
    knowledge_base_cache=None,
) -> dict:
    base = base_dir or Path.cwd()
    config = load_runtime_config(base)
    return answer_chatbot_question(
        query,
        base_dir=base,
        primary_path=config.primary_kb_path,
        secondary_path=config.secondary_kb_path,
        include_debug=debug,
        agentic_enabled=config.agentic_enabled if agentic_enabled is None else agentic_enabled,
        knowledge_base_cache=knowledge_base_cache,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Answer OeNB questions via routed hybrid retrieval")
    parser.add_argument("query", help="Free-text query")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Worktree root containing data/")
    parser.add_argument("--debug", action="store_true", help="Include routing and retrieval debug data")
    parser.add_argument("--agentic", action="store_true", help="Enable selective live ISAweb lookup")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    result = run_rag_answering(
        args.query,
        base_dir=args.base_dir,
        debug=args.debug,
        agentic_enabled=args.agentic,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
