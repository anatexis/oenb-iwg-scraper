"""Hybrid retrieval orchestration for the OeNB chatbot."""

from __future__ import annotations

from pathlib import Path

from analysis.embedding_backends import SemanticSearchBackend
from analysis.query_knowledge_base import search_knowledge_base
from analysis.query_router import extract_comparison_subjects, route_query
from analysis.semantic_search import apply_semantic_search


def retrieve_hybrid(
    query: str,
    *,
    primary_path: Path,
    secondary_path: Path | None = None,
    limit: int = 10,
    semantic_backend: SemanticSearchBackend | None = None,
    semantic_enabled: bool = False,
    routed_query: dict | None = None,
    llm_provider=None,
    knowledge_base_cache=None,
) -> dict:
    routing = routed_query or route_query(
        query,
        llm_provider=llm_provider,
        primary_path=primary_path,
        secondary_path=secondary_path,
        knowledge_base_cache=knowledge_base_cache,
    )
    if routing.get("strategy") == "reject_or_clarify":
        # Try retrieval anyway — the LLM router (especially small models)
        # sometimes misclassifies in-scope queries as out-of-scope.
        # If we find hits, override the rejection.
        fallback_routing = {**routing, "strategy": "rag_first"}
        fallback_hits = search_knowledge_base(
            query=query,
            primary_path=secondary_path or primary_path,
            secondary_path=primary_path if secondary_path else None,
            limit=limit,
            routed_query=fallback_routing,
            knowledge_base_cache=knowledge_base_cache,
        )
        if fallback_hits:
            routing = fallback_routing
        else:
            return {
                "hits": [],
                "confidence": 0.0,
                "routing": routing,
                "subquery_results": [],
            }

    # Lexical comparison detection overrides the LLM's query_intent — small
    # routers routinely mislabel "Was unterscheidet X von Y" as
    # topic_overview, which would suppress the subject split and the
    # two-part answer.
    if routing.get("query_intent") != "comparison" and extract_comparison_subjects(query):
        routing = {**routing, "query_intent": "comparison"}

    search_primary = primary_path
    search_secondary = secondary_path
    swap_source_labels = False
    if routing.get("strategy") == "rag_first" and secondary_path is not None:
        search_primary = secondary_path
        search_secondary = primary_path
        swap_source_labels = True

    subqueries = (
        _comparison_subqueries(query, routing)
        or routing.get("subqueries")
        or _orchestrated_subqueries(query, routing)
    )

    if subqueries:
        subquery_results = []
        merged_hits = []
        for subquery in subqueries:
            subroute = {
                "intent": routing.get("intent"),
                "query_intent": routing.get("query_intent"),
                "domains": [subquery["domain"]],
                "entities": routing.get("entities", []),
                "freshness_need": routing.get("freshness_need"),
                "subqueries": [],
                "strategy": routing.get("strategy"),
                "confidence": routing.get("confidence"),
                "reasoning_hint": routing.get("reasoning_hint"),
            }
            hits = search_knowledge_base(
                query=subquery["query"],
                primary_path=search_primary,
                secondary_path=search_secondary,
                limit=limit,
                routed_query=subroute,
                knowledge_base_cache=knowledge_base_cache,
            )
            if swap_source_labels:
                hits = _swap_source_preferences(hits)
            subquery_results.append({"domain": subquery["domain"], "query": subquery["query"], "hits": hits})
            merged_hits.extend(hits)
        hits = _deduplicate_hits(merged_hits)[:limit]
    else:
        hits = search_knowledge_base(
            query=query,
            primary_path=search_primary,
            secondary_path=search_secondary,
            limit=limit,
            routed_query=routing,
            knowledge_base_cache=knowledge_base_cache,
        )
        if swap_source_labels:
            hits = _swap_source_preferences(hits)
        subquery_results = []

    hits = apply_semantic_search(
        query=query,
        hits=hits,
        backend=semantic_backend,
        enabled=semantic_enabled,
        limit=limit,
    )

    return {
        "hits": hits,
        "confidence": _confidence_from_hits(hits),
        "routing": routing,
        "subquery_results": subquery_results,
    }


def _comparison_subqueries(query: str, routing: dict | None) -> list[dict]:
    """For comparison queries, one subquery per compared subject.

    Domain is set to website_general so each subject is searched broadly
    (no domain filter) — the router's single blob-domain is usually wrong
    for at least one of the two subjects. Overrides any LLM-supplied
    subqueries, which tend to carry the same text for both halves.
    """
    if not routing or routing.get("query_intent") != "comparison":
        return []
    subjects = extract_comparison_subjects(query)
    if not subjects:
        return []
    return [{"domain": "website_general", "query": subject} for subject in subjects]


def _orchestrated_subqueries(query: str, routing: dict | None) -> list[dict]:
    if not routing:
        return []
    query_intent = routing.get("query_intent")
    domains = list(routing.get("domains") or [])
    if query_intent not in {"release_lookup", "navigation"}:
        return []
    if "website_general" not in domains:
        return []

    entities = list(routing.get("entities") or [])
    preferred_query = entities[0] if entities else query
    subqueries = [{"domain": "website_general", "query": query}]
    for domain in domains:
        if domain == "website_general":
            continue
        subqueries.append({"domain": domain, "query": preferred_query})
    return subqueries


def _deduplicate_hits(hits: list[dict]) -> list[dict]:
    best_by_id: dict[str, dict] = {}
    for hit in hits:
        hit_id = hit.get("id")
        if not hit_id:
            continue
        current = best_by_id.get(hit_id)
        if current is None or int(hit.get("match_score", 0)) > int(current.get("match_score", 0)):
            best_by_id[hit_id] = hit
    return sorted(best_by_id.values(), key=lambda hit: (-int(hit.get("match_score", 0)), hit.get("id", "")))


def _confidence_from_hits(hits: list[dict]) -> float:
    if not hits:
        return 0.0
    top_score = max(int(hit.get("match_score", 0)) for hit in hits)
    return min(1.0, round(top_score / 2000, 3))


def _swap_source_preferences(hits: list[dict]) -> list[dict]:
    swapped = []
    for hit in hits:
        source_preference = hit.get("source_preference")
        if source_preference == "primary":
            source_preference = "secondary"
        elif source_preference == "secondary":
            source_preference = "primary"
        swapped.append({**hit, "source_preference": source_preference})
    return swapped
