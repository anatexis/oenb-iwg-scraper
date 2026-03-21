"""Search exported knowledge-base JSONL files with statistics-first ranking."""

from __future__ import annotations

import json
import re
from pathlib import Path

from analysis.domain_gating import filter_records_for_route
from analysis.query_router import route_query
from analysis.text_stopwords import is_stopword

QUERY_SYNONYMS = {
    "leitzins": ["base rate", "reference rate", "base and reference rates", "basiszinssatz", "referenzzinssatz", "leitzinssätze", "key interest rates", "policy rates"],
    "leitzinsen": ["base rate", "reference rate", "base and reference rates", "basiszinssatz", "referenzzinssatz", "leitzinssätze", "key interest rates", "policy rates"],
    "kreditzinsen": ["kreditzinssätze", "lending rates", "lending rate"],
    "kreditzins": ["kreditzinssätze", "lending rates", "lending rate"],
    "sparzinsen": ["einlagenzinssätze", "deposit rates", "deposit rate", "einlagenzinsen"],
    "einlagenzinsen": ["einlagenzinssätze", "deposit rates", "deposit rate", "sparzinsen"],
    "rppi": ["residential property price index", "wohnimmobilienpreisindex"],
    "fsi": ["financial soundness indicators", "tier 1 capital", "indikatoren zur stabilität des finanzsektors"],
}

PREFERRED_QUERY_PHRASES = {
    "leitzins": ["key interest rates", "policy rates"],
    "leitzinsen": ["key interest rates", "policy rates"],
}

ROUTED_DOMAIN_TERMS = {
    "monetary_policy": ["einlagenfazilität", "deposit facility", "policy rates", "key interest rates", "leitzins"],
    "interest_rates": ["key interest rates", "policy rates", "base and reference rates"],
    "commodity_prices": ["gold", "gold price", "goldpreis", "commodity prices"],
    "real_estate": ["residential property price index", "rppi", "property prices", "immobilienpreise"],
    "financial_soundness": ["financial soundness indicators", "fsi", "tier 1 capital"],
    "external_sector": ["dienstleistungsverkehr", "external sector", "services trade"],
    "reserves_assets": ["gold reserves", "goldreserven", "reserve assets", "währungsreserven"],
    "financial_education": ["taschengeld", "financial education", "finanzbildung", "kinder", "jugendliche"],
    "corporate_topics": ["kunstsammlung", "art collection", "frauen in führungsfunktionen", "gleichstellung", "diversität"],
}


def search_knowledge_base(
    *,
    query: str,
    primary_path: Path,
    secondary_path: Path | None = None,
    limit: int = 10,
    routed_query: dict | None = None,
    knowledge_base_cache=None,
) -> list[dict]:
    """Search chatbot chunks with a statistics-first preference."""

    routed_query = routed_query or route_query(query)
    primary_records = filter_records_for_route(
        _matching_chunk_records(primary_path, query, routed_query, knowledge_base_cache=knowledge_base_cache),
        routed_query,
    )
    primary_hits = _rank_hits(primary_records, query=query, source_preference="primary", routed_query=routed_query)
    if len(primary_hits) >= limit or secondary_path is None:
        return primary_hits[:limit]

    secondary_records = filter_records_for_route(
        _matching_chunk_records(secondary_path, query, routed_query, knowledge_base_cache=knowledge_base_cache),
        routed_query,
    )
    secondary_hits = _rank_hits(
        secondary_records,
        query=query,
        source_preference="secondary",
        routed_query=routed_query,
    )
    if _should_blend_sources(routed_query):
        return _merge_hits_by_query_intent(primary_hits, secondary_hits)[:limit]
    return [*primary_hits, *secondary_hits][:limit]


def _matching_chunk_records(
    path: Path,
    query: str,
    routed_query: dict | None = None,
    *,
    knowledge_base_cache=None,
) -> list[dict]:
    query_tokens = _expanded_query_tokens(query, routed_query)
    strong_terms = _strong_match_terms(routed_query)
    records: list[dict] = []
    iter_records = knowledge_base_cache.records(path) if knowledge_base_cache is not None else None
    if iter_records is None:
        with path.open("r", encoding="utf-8") as handle:
            iter_records = [json.loads(line) for line in handle if line.strip()]
    for record in iter_records:
        if record.get("record_type") != "chatbot_chunk":
            continue
        haystack = _search_haystack(record)
        if _is_candidate_match(haystack, query_tokens, strong_terms):
            records.append(record)
    return records


def _rank_hits(records: list[dict], *, query: str, source_preference: str, routed_query: dict | None = None) -> list[dict]:
    query_tokens = set(_expanded_query_tokens(query, routed_query))
    preferred_phrases = set(_preferred_query_phrases(query))
    strong_terms = set(_strong_match_terms(routed_query))
    ranked = []
    for record in records:
        title = (record.get("title") or "").lower()
        text = _rankable_text(record).lower()
        primary_url = _primary_reference_url(record).lower()
        token_hits = len({token for token in query_tokens if token in title or token in text})
        title_hits = len({token for token in query_tokens if token in title})
        phrase_title_hits = len({token for token in query_tokens if " " in token and token in title})
        preferred_title_hits = len({token for token in preferred_phrases if token in title})
        strong_hits = len({term for term in strong_terms if term in title or term in text or term in primary_url})
        preferred_record_boost = _preferred_record_boost(query, title, primary_url)
        query_intent_boost = _query_intent_record_boost(routed_query, record, title=title, text=text, primary_url=primary_url)
        score = (
            int(record.get("retrieval_score", 0))
            + token_hits * 50
            + title_hits * 80
            + phrase_title_hits * 250
            + preferred_title_hits * 500
            + strong_hits * 600
            + preferred_record_boost
            + query_intent_boost
        )
        ranked.append(
            {
                **record,
                "source_preference": source_preference,
                "match_score": score,
            }
        )

    return sorted(
        ranked,
        key=lambda record: (
            -record["match_score"],
            0 if source_preference == "primary" else 1,
            record.get("id", ""),
        ),
    )


def _query_tokens(query: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{3,}", query.lower())
        if not is_stopword(token)
    ]


def _expanded_query_tokens(query: str, routed_query: dict | None = None) -> list[str]:
    tokens = _query_tokens(query)
    expanded = list(tokens)
    seen = set(tokens)
    for token in tokens:
        for synonym in QUERY_SYNONYMS.get(token, []):
            synonym_lower = synonym.lower()
            if synonym_lower not in seen:
                expanded.append(synonym_lower)
                seen.add(synonym_lower)
    if routed_query:
        for term in _routing_terms(routed_query):
            term_lower = term.lower()
            if term_lower not in seen:
                expanded.append(term_lower)
                seen.add(term_lower)
    return expanded


def _preferred_query_phrases(query: str) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for token in _query_tokens(query):
        for phrase in PREFERRED_QUERY_PHRASES.get(token, []):
            phrase_lower = phrase.lower()
            if phrase_lower not in seen:
                phrases.append(phrase_lower)
                seen.add(phrase_lower)
    return phrases


def _routing_terms(routed_query: dict) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for domain in routed_query.get("domains", []):
        for term in ROUTED_DOMAIN_TERMS.get(domain, []):
            if term not in seen:
                terms.append(term)
                seen.add(term)
    for entity in routed_query.get("entities", []):
        entity_text = str(entity).strip()
        if entity_text and entity_text not in seen:
            terms.append(entity_text)
            seen.add(entity_text)
    for subquery in routed_query.get("subqueries", []):
        query_text = str(subquery.get("query") or "").strip()
        if query_text and query_text not in seen:
            terms.append(query_text)
            seen.add(query_text)
    return terms


def _strong_match_terms(routed_query: dict | None) -> list[str]:
    if not routed_query:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for term in _routing_terms(routed_query):
        normalized = term.lower().strip()
        if normalized and not is_stopword(normalized) and normalized not in seen:
            terms.append(normalized)
            seen.add(normalized)
    return terms


def _is_candidate_match(haystack: str, query_tokens: list[str], strong_terms: list[str]) -> bool:
    if any(term in haystack for term in strong_terms):
        return True
    token_hits = [token for token in query_tokens if token in haystack]
    if not token_hits:
        return False
    if len(query_tokens) <= 1:
        return True
    return len(token_hits) >= 2


def _primary_reference_url(record: dict) -> str:
    reference_urls = record.get("reference_urls") or []
    return str(reference_urls[0]) if reference_urls else ""


def _search_haystack(record: dict) -> str:
    return " ".join(
        str(part)
        for part in (
            record.get("title"),
            _rankable_text(record),
            _primary_reference_url(record),
            " ".join(record.get("sources", [])),
        )
        if part
    ).lower()


def _preferred_record_boost(query: str, title: str, primary_url: str) -> int:
    lowered_query = query.lower()
    if "einlagenfazilität" in lowered_query or "deposit facility" in lowered_query:
        if "report=10.4" in primary_url or "key interest rates" in title:
            return 900
    if "leitzins" in lowered_query or "leitzinsen" in lowered_query:
        if "report=10.4" in primary_url or "key interest rates" in title:
            return 700
    return 0


def _query_intent_record_boost(routed_query: dict | None, record: dict, *, title: str, text: str, primary_url: str) -> int:
    if not routed_query:
        return 0
    query_intent = routed_query.get("query_intent")
    parent_record_type = record.get("parent_record_type")
    boost = 0
    if query_intent == "release_lookup":
        if "release" in title or "release" in text or "releasekalender" in primary_url:
            boost += 900
        if parent_record_type == "page_document":
            boost += 250
    if query_intent == "navigation":
        if any(term in title or term in text or term in primary_url for term in ("csv", "excel", "download", "tabelle", "zeitreihe")):
            boost += 700
        if parent_record_type == "page_document":
            boost += 200
        if parent_record_type == "dataset_family" and any(
            term in title or term in text for term in ("csv", "excel", "download")
        ):
            boost -= 300
    return boost


def _should_blend_sources(routed_query: dict | None) -> bool:
    if not routed_query:
        return False
    query_intent = routed_query.get("query_intent")
    domains = set(routed_query.get("domains") or [])
    return query_intent in {"release_lookup", "navigation", "explanation"} and "website_general" in domains


def _merge_hits_by_query_intent(primary_hits: list[dict], secondary_hits: list[dict]) -> list[dict]:
    return sorted(
        [*primary_hits, *secondary_hits],
        key=lambda record: (
            -int(record.get("match_score", 0)),
            0 if record.get("source_preference") == "secondary" else 1,
            record.get("id", ""),
        ),
    )


def _rankable_text(record: dict) -> str:
    text = record.get("text") or ""
    if record.get("chunk_kind") == "family_summary":
        marker = "Supporting pages:"
        if marker in text:
            return text.split(marker, 1)[0].strip()
    return text


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Search chatbot chunks in knowledge-base JSONL files")
    parser.add_argument("query", help="Free-text query")
    parser.add_argument("--primary", type=Path, required=True, help="Primary JSONL path, e.g. statistics KB")
    parser.add_argument("--secondary", type=Path, default=None, help="Optional fallback JSONL path, e.g. full-site KB")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of hits")
    args = parser.parse_args()

    hits = search_knowledge_base(
        query=args.query,
        primary_path=args.primary,
        secondary_path=args.secondary,
        limit=args.limit,
    )
    print(json.dumps(hits, indent=2, ensure_ascii=False))
