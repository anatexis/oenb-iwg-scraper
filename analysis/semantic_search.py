"""Small adapter layer for future semantic reranking."""

from __future__ import annotations

from analysis.embedding_backends import NoopSemanticSearchBackend, SemanticSearchBackend


def apply_semantic_search(
    *,
    query: str,
    hits: list[dict],
    backend: SemanticSearchBackend | None = None,
    enabled: bool = False,
    limit: int = 10,
) -> list[dict]:
    if not enabled:
        return hits[:limit]
    active_backend = backend or NoopSemanticSearchBackend()
    return active_backend.rerank(query, hits, limit=limit)
