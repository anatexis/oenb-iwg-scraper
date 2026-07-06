"""Stable entry point for stats-first chatbot retrieval."""

from __future__ import annotations

from pathlib import Path

from analysis.hybrid_retrieval import retrieve_hybrid


def default_knowledge_base_paths(base_dir: Path) -> tuple[Path, Path]:
    data_dir = base_dir / "data"
    return (
        data_dir / "statistics_production" / "knowledge_base_active.jsonl",
        data_dir / "full_site_production" / "knowledge_base_active.jsonl",
    )


def search_chatbot_knowledge(
    query: str,
    *,
    base_dir: Path | None = None,
    primary_path: Path | None = None,
    secondary_path: Path | None = None,
    limit: int = 10,
    knowledge_base_cache=None,
) -> list[dict]:
    result = retrieve_chatbot_knowledge(
        query,
        base_dir=base_dir,
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=limit,
        knowledge_base_cache=knowledge_base_cache,
    )
    return result["hits"]


def retrieve_chatbot_knowledge(
    query: str,
    *,
    base_dir: Path | None = None,
    primary_path: Path | None = None,
    secondary_path: Path | None = None,
    limit: int = 10,
    knowledge_base_cache=None,
    routed_query: dict | None = None,
) -> dict:
    if primary_path is None or secondary_path is None:
        resolved_primary, resolved_secondary = default_knowledge_base_paths(base_dir or Path.cwd())
        primary_path = primary_path or resolved_primary
        secondary_path = secondary_path or resolved_secondary

    return retrieve_hybrid(
        query=query,
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=limit,
        knowledge_base_cache=knowledge_base_cache,
        routed_query=routed_query,
    )


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Search the OeNB chatbot knowledge bases")
    parser.add_argument("query", help="Free-text query")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Worktree root containing data/")
    parser.add_argument("--primary", type=Path, default=None, help="Optional primary knowledge-base path")
    parser.add_argument("--secondary", type=Path, default=None, help="Optional fallback knowledge-base path")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of hits")
    args = parser.parse_args()

    hits = search_chatbot_knowledge(
        args.query,
        base_dir=args.base_dir,
        primary_path=args.primary,
        secondary_path=args.secondary,
        limit=args.limit,
    )
    print(json.dumps(hits, indent=2, ensure_ascii=False))
