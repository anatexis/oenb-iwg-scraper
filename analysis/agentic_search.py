"""Selective agentic lookup orchestration."""

from __future__ import annotations


def maybe_run_agentic_search(
    *,
    query: str,
    retrieval_payload: dict,
    live_lookup,
    enabled: bool = False,
) -> dict | None:
    if not enabled:
        return None
    confidence = float(retrieval_payload.get("confidence") or 0.0)
    routing = retrieval_payload.get("routing") or {}
    freshness_need = routing.get("freshness_need") or "low"
    if freshness_need != "high" or confidence >= 0.75:
        return None
    hits = retrieval_payload.get("hits") or []
    return live_lookup(query, hits, routing)
