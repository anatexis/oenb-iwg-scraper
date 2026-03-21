"""Small CLI helper for inspecting routed query output."""

from __future__ import annotations

import argparse
import json

from analysis.query_router import route_query


def run_router_demo(query: str) -> dict:
    return route_query(query)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect routed OeNB chatbot query output")
    parser.add_argument("query", help="Free-text query")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    print(json.dumps(run_router_demo(args.query), indent=2, ensure_ascii=False))
