"""Query routing for OeNB chatbot retrieval."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from analysis.domain_gating import DOMAIN_HINTS, classify_record_domains
from analysis.llm.factory import build_llm_provider
from analysis.text_stopwords import is_stopword

ROUTER_PROMPT_PATH = Path(__file__).parent / "prompts" / "router_prompt.txt"
DOMAIN_ORDER = [
    "monetary_policy",
    "interest_rates",
    "commodity_prices",
    "real_estate",
    "financial_soundness",
    "external_sector",
    "reserves_assets",
    "financial_education",
    "corporate_topics",
    "website_general",
]
DOMAIN_TAXONOMY = set(DOMAIN_ORDER)
FRESHNESS_LEVELS = {"low", "medium", "high"}
STRATEGIES = {"sql_first", "rag_first", "hybrid", "reject_or_clarify"}
STATISTICAL_DOMAINS = {
    "monetary_policy",
    "interest_rates",
    "commodity_prices",
    "real_estate",
    "financial_soundness",
    "external_sector",
    "reserves_assets",
}
QUERY_INTENTS = {
    "fact_lookup",
    "comparison",
    "advice_request",
    "release_lookup",
    "navigation",
    "explanation",
    "trend_over_time",
    "topic_overview",
}
STRUCTURED_RECORD_TYPES = {"dataset_family", "isaweb_dataset", "isaweb_metadata"}
TEXT_RECORD_TYPES = {"page_document"}
ROUTE_CANDIDATE_RECORD_TYPES = STRUCTURED_RECORD_TYPES | TEXT_RECORD_TYPES
DEFAULT_ROUTE = {
    "intent": "topic_overview",
    "query_intent": "topic_overview",
    "domains": ["website_general"],
    "entities": [],
    "freshness_need": "low",
    "subqueries": [],
    "strategy": "rag_first",
    "confidence": 0.25,
    "reasoning_hint": "default fallback to general website retrieval",
}

# Last-resort fallback rules when there are no usable candidates or no model response.
FALLBACK_RULES = [
    {
        "concept_key": "gold",
        "relation": "holdings",
        "domain": "reserves_assets",
        "terms": ["goldreserven", "gold reserve", "gold reserves", "reserve assets", "währungsreserven"],
        "entity": "Goldreserven",
        "intent": "fact_lookup",
        "freshness_need": "medium",
        "priority": 100,
    },
    {
        "concept_key": "policy_rates",
        "relation": "policy_rate",
        "domain": "monetary_policy",
        "terms": ["einlagenfazilität", "deposit facility", "leitzins", "hauptrefinanzierungssatz"],
        "entity": "Einlagenfazilität",
        "intent": "fact_lookup",
        "freshness_need": "high",
        "priority": 90,
    },
    {
        "concept_key": "policy_rates",
        "relation": "policy_rate",
        "domain": "interest_rates",
        "terms": ["einlagenfazilität", "deposit facility", "leitzins", "zinssatz", "key interest rates"],
        "entity": "Einlagenfazilität",
        "intent": "fact_lookup",
        "freshness_need": "high",
        "priority": 85,
    },
    {
        "concept_key": "gold",
        "relation": "price",
        "domain": "commodity_prices",
        "terms": ["goldpreis", "gold price", "rohstoffpreise", "commodity prices"],
        "entity": "Goldpreis",
        "intent": "fact_lookup",
        "freshness_need": "high",
        "priority": 80,
    },
    {
        "concept_key": "gold",
        "relation": "topic",
        "domain": "commodity_prices",
        "terms": ["gold"],
        "entity": "Goldpreis",
        "intent": "topic_overview",
        "freshness_need": "medium",
        "priority": 40,
    },
    {
        "concept_key": "real_estate",
        "relation": "price",
        "domain": "real_estate",
        "terms": ["immobilienpreise", "wohnimmobilien", "rppi", "house prices", "property prices"],
        "entity": "Immobilienpreise",
        "intent": "topic_overview",
        "freshness_need": "medium",
        "priority": 70,
    },
    {
        "concept_key": "fsi",
        "relation": "indicator",
        "domain": "financial_soundness",
        "terms": ["financial soundness", "fsi", "soundness indicators"],
        "entity": "Financial Soundness Indicators",
        "intent": "fact_lookup",
        "freshness_need": "medium",
        "priority": 70,
    },
    {
        "concept_key": "financial_education",
        "relation": "guidance",
        "domain": "financial_education",
        "terms": ["taschengeld", "kinder", "jugendliche", "finanzbildung", "schulden", "budget", "sparen"],
        "entity": "Taschengeld",
        "intent": "topic_overview",
        "freshness_need": "low",
        "priority": 60,
    },
    {
        "concept_key": "corporate_topics",
        "relation": "explanation",
        "domain": "corporate_topics",
        "terms": [
            "frauen in führungsfunktionen",
            "kunstsammlung",
            "art collection",
            "führungsfunktionen",
            "gleichstellung",
            "diversität",
        ],
        "entity": "OeNB corporate topic",
        "intent": "topic_overview",
        "freshness_need": "low",
        "priority": 60,
    },
]

QUERY_DOMAIN_HINTS = {
    "commodity_prices": ["inflation", "inflationsdaten", "verbraucherpreisindex", "vpi"],
    "interest_rates": ["sparzinsen", "kreditzinsen", "wohnbaukreditzinsen", "basiszinssatz", "referenzzinssatz"],
    "real_estate": ["wohnimmobilienpreisindex", "immobilienpreise"],
    "financial_soundness": [
        "oesterreichischen banken",
        "österreichischen banken",
        "oesterreichische banken",
        "österreichische banken",
        "bankenstabilitaet",
        "bankenstabilität",
    ],
}

QUERY_ENTITY_RULES = [
    ("isaweb", "ISAweb"),
    ("bargeldumlauf", "Bargeldumlauf"),
    ("wohnimmobilienpreisindex", "Wohnimmobilienpreisindex"),
    ("verbraucherpreisindex", "Verbraucherpreisindex"),
    ("inflation", "Inflation"),
    ("sparzinsen", "Sparzinsen"),
    ("wohnbaukreditzinsen", "Wohnbaukreditzinsen"),
    ("basiszinssatz", "Basiszinssatz"),
    ("referenzzinssatz", "Referenzzinssatz"),
    ("wechselkurs", "Wechselkurse"),
]

GENERIC_QUERY_INTENT_PATTERNS = {
    "release_lookup": [
        "wann werden",
        "wann wird",
        "wann ist die naechste veroeffentlichung",
        "wann ist die nächste veröffentlichung",
        "zu welchem termin erscheinen",
        "wann erscheinen",
        "veroeffentlicht",
        "veröffentlicht",
        "veroeffentlichung",
        "veröffentlichung",
    ],
    "navigation": [
        "wo finde ich",
        "auf welcher seite finde ich",
        "wo gibt es",
        "kann ich",
        "als csv",
        "als excel",
        "download",
        "herunterladen",
        "tabelle",
        "zeitreihe",
    ],
    "explanation": [
        "was misst",
        "wie funktioniert",
        "wie kann ich",
        "was ist isaweb",
        "was ist der unterschied",
        "was ist die bedeutung",
    ],
    "trend_over_time": [
        "in den letzten",
        "letzten 12 monaten",
        "letzten jahren",
        "entwickelt",
        "entwicklung",
        "trend",
    ],
}

IN_SCOPE_HINTS = {
    "oenb",
    "nationalbank",
    "geldmuseum",
    "museum",
    "isaweb",
    "statistik",
    "daten",
    "inflation",
    "zins",
    "gold",
    "immobil",
    "banken",
    "bargeld",
    "wechselkurs",
    "kredit",
    "verbraucherpreis",
    "wohnimmobilienpreisindex",
    "taschengeld",
    "kunstsammlung",
    "führungsfunktionen",
    "fuehrungsfunktionen",
}


def route_query(
    query: str,
    *,
    llm_provider=None,
    candidate_records: list[dict] | None = None,
    primary_path: Path | None = None,
    secondary_path: Path | None = None,
    candidate_limit: int = 8,
    knowledge_base_cache=None,
) -> dict:
    candidates = candidate_records or _build_route_candidates(
        query,
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=candidate_limit,
        knowledge_base_cache=knowledge_base_cache,
    )
    fallback_route = _route_with_rules(query)

    if llm_provider is None:
        try:
            llm_provider = build_llm_provider()
        except Exception:
            llm_provider = None

    if llm_provider is not None:
        try:
            raw = llm_provider.invoke_json(
                ROUTER_PROMPT_PATH.read_text(encoding="utf-8"),
                _build_router_user_prompt(query, candidates),
                schema_hint=(
                    '{"intent":"fact_lookup|topic_overview|comparison|advice_request|unknown",'
                    '"query_intent":"fact_lookup|comparison|advice_request|release_lookup|navigation|explanation|trend_over_time|topic_overview",'
                    '"domains":["website_general"],"entities":[],"freshness_need":"low|medium|high",'
                    '"subqueries":[],"strategy":"sql_first|rag_first|hybrid|reject_or_clarify",'
                    '"confidence":0.0,"reasoning_hint":"short explanation"}'
                ),
            )
            llm_route = _normalize_route(raw)
            return _merge_llm_and_candidate_routes(
                query=query,
                llm_route=llm_route,
                candidate_route=_route_from_candidates(query, candidates, fallback_route),
                fallback_route=fallback_route,
            )
        except Exception:
            pass

    if candidates:
        return _route_from_candidates(query, candidates, fallback_route)
    return fallback_route


def _build_route_candidates(
    query: str,
    *,
    primary_path: Path | None,
    secondary_path: Path | None,
    limit: int,
    knowledge_base_cache=None,
) -> list[dict]:
    tokens = _query_tokens(query)
    candidates = []
    candidates.extend(
        _collect_candidates_from_path(
            primary_path,
            query=query,
            tokens=tokens,
            source_preference="primary",
            knowledge_base_cache=knowledge_base_cache,
        )
    )
    candidates.extend(
        _collect_candidates_from_path(
            secondary_path,
            query=query,
            tokens=tokens,
            source_preference="secondary",
            knowledge_base_cache=knowledge_base_cache,
        )
    )
    candidates.sort(key=lambda item: (-item["score"], item["source_preference"], item["id"]))
    best: list[dict] = []
    seen = set()
    for candidate in candidates:
        if candidate["id"] in seen:
            continue
        best.append(candidate)
        seen.add(candidate["id"])
        if len(best) >= limit:
            break
    return best


def _collect_candidates_from_path(
    path: Path | None,
    *,
    query: str,
    tokens: list[str],
    source_preference: str,
    knowledge_base_cache=None,
) -> list[dict]:
    if path is None or not path.exists():
        return []

    candidates: list[dict] = []
    iter_records = knowledge_base_cache.records(path) if knowledge_base_cache is not None else None
    if iter_records is None:
        with path.open("r", encoding="utf-8") as handle:
            iter_records = [json.loads(line) for line in handle if line.strip()]
    for record in iter_records:
        record_type = record.get("record_type")
        if record_type not in ROUTE_CANDIDATE_RECORD_TYPES:
            continue
        candidate = _candidate_from_record(record, query=query, tokens=tokens, source_preference=source_preference)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_from_record(record: dict, *, query: str, tokens: list[str], source_preference: str) -> dict | None:
    title = str(record.get("title") or "").strip()
    if not title:
        return None
    lowered_title = title.lower()
    if "sitemap" in lowered_title or lowered_title.startswith("chart "):
        return None

    text_preview = _record_preview_text(record)
    reference_url = _record_reference_url(record)
    candidate_like_record = {
        "title": title,
        "text": text_preview,
        "reference_urls": [reference_url] if reference_url else [],
        "id": record.get("id"),
        "parent_id": record.get("id"),
    }
    domains = record.get("domains") or classify_record_domains(candidate_like_record)
    scored_title = _sanitize_candidate_text(title.lower())
    reference_text = _sanitize_candidate_text(_reference_text(reference_url).lower())
    scored_preview = _sanitize_candidate_text(text_preview.lower())
    score = _candidate_score(
        query=query,
        tokens=tokens,
        title_text=scored_title,
        reference_text=reference_text,
        preview_text=scored_preview,
        record_type=record.get("record_type"),
    )
    if score < 120:
        return None
    return {
        "id": record.get("id"),
        "title": title,
        "record_type": record.get("record_type"),
        "domains": domains,
        "source_preference": source_preference,
        "score": score,
        "reference_url": reference_url,
        "text_preview": text_preview[:240],
    }

def _record_preview_text(record: dict) -> str:
    for key in ("text_content", "text", "comment", "classification", "source_text_raw"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    source_page = record.get("source_page") or {}
    for key in ("text", "title"):
        value = source_page.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    latest = record.get("latest_observation") or {}
    if latest.get("series_label") or latest.get("value"):
        return " ".join(str(part) for part in (latest.get("series_label"), latest.get("value"), latest.get("unit")) if part)
    return ""


def _record_reference_url(record: dict) -> str:
    source_page = record.get("source_page") or {}
    isaweb_dataset = record.get("isaweb_dataset") or {}
    isaweb_metadata = record.get("isaweb_metadata") or {}
    for value in (
        record.get("url"),
        source_page.get("url"),
        source_page.get("final_url"),
        record.get("source_url"),
        isaweb_dataset.get("source_url"),
        isaweb_metadata.get("meta_url"),
    ):
        if value:
            return str(value)
    reference_urls = record.get("reference_urls") or []
    return str(reference_urls[0]) if reference_urls else ""


def _reference_text(reference_url: str) -> str:
    if not reference_url:
        return ""
    parsed = urlsplit(reference_url)
    return f"{parsed.path} {parsed.query}".strip()


def _sanitize_candidate_text(text: str) -> str:
    sanitized = text
    for boilerplate in (
        "oesterreichische nationalbank",
        "zur navigation",
        "zum inhalt",
        "to navigation",
        "to content",
    ):
        sanitized = sanitized.replace(boilerplate, " ")
    sanitized = re.sub(r"\boenb\b", " ", sanitized)
    return " ".join(sanitized.split())


def _candidate_score(
    *,
    query: str,
    tokens: list[str],
    title_text: str,
    reference_text: str,
    preview_text: str,
    record_type: str | None,
) -> int:
    title_hits = _field_token_score(tokens, title_text)
    reference_hits = _field_token_score(tokens, reference_text)
    preview_hits = _field_token_score(tokens, preview_text)

    phrase_hits = 0.0
    for phrase in _query_phrases(query):
        if phrase in title_text or phrase in reference_text:
            phrase_hits += 1.0
        elif phrase in preview_text:
            phrase_hits += 0.6

    # Ignore weak preview-only matches for open-ended website questions.
    if title_hits == 0 and reference_hits == 0 and phrase_hits == 0 and preview_hits < 2:
        return 0

    boost = 0
    if record_type in STRUCTURED_RECORD_TYPES:
        boost += 40
    elif record_type in TEXT_RECORD_TYPES:
        boost += 20

    return int(title_hits * 140 + reference_hits * 120 + preview_hits * 35 + phrase_hits * 220 + boost)


def _field_token_score(tokens: list[str], text: str) -> float:
    if not text:
        return 0.0
    words = _normalized_words(text)
    if not words:
        return 0.0
    return sum(_best_token_match(token, words) for token in tokens)


def _best_token_match(token: str, words: set[str]) -> float:
    normalized = _stem_token(token)
    best = 0.0
    for word in words:
        if normalized == word:
            return 1.0
        if len(normalized) >= 7 and len(word) >= 4 and (normalized in word or word in normalized):
            best = max(best, 0.6)
    return best


def _normalized_words(text: str) -> set[str]:
    return {_stem_token(word) for word in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{3,}", text.lower())}


def _stem_token(token: str) -> str:
    normalized = token.lower()
    for suffix in ("innen", "ungen", "eren", "ern", "en", "er", "es", "e", "n", "s"):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 4:
            return normalized[: -len(suffix)]
    return normalized


def _route_from_candidates(query: str, candidates: list[dict], fallback_route: dict) -> dict:
    if not candidates:
        return fallback_route

    if _is_clearly_out_of_scope(query) and not _has_strong_in_scope_candidate(query, candidates):
        return _normalize_route(
            {
                **DEFAULT_ROUTE,
                "strategy": "reject_or_clarify",
                "reasoning_hint": "query appears outside OeNB knowledge scope",
            }
        )

    query_intent = _infer_query_intent(query)
    if (
        fallback_route.get("domains") == ["website_general"]
        and query_intent in {"navigation", "explanation"}
        and not _domains_from_query_hints(query)
    ):
        return fallback_route

    domain_scores: dict[str, int] = {}
    domain_support: dict[str, int] = {}
    domain_best: dict[str, dict] = {}
    for candidate in candidates:
        for domain in candidate["domains"]:
            alignment = _domain_alignment_score(query, domain, candidate)
            if alignment <= 0:
                continue
            weighted_score = int(candidate["score"] * alignment)
            domain_scores[domain] = max(domain_scores.get(domain, 0), weighted_score)
            domain_support[domain] = domain_support.get(domain, 0) + weighted_score
            current_best = domain_best.get(domain)
            if current_best is None or candidate["score"] > current_best["score"]:
                domain_best[domain] = candidate

    for domain, support in domain_support.items():
        domain_scores[domain] = domain_scores.get(domain, 0) + int(support * 0.08)

    selected_domains = _select_domains(query, domain_scores)
    if _wants_multiple_topics(query):
        for domain in fallback_route.get("domains", []):
            if domain != "website_general" and domain not in selected_domains:
                selected_domains.append(domain)
    selected_domains = _augment_domains_for_query_intent(selected_domains, query_intent)
    if not selected_domains:
        return fallback_route
    if _should_prefer_fallback_route(query_intent, selected_domains, fallback_route):
        return fallback_route

    top_candidates = [domain_best[domain] for domain in selected_domains if domain in domain_best]
    intent = _infer_intent(query, fallback_route, query_intent)
    strategy = _infer_candidate_strategy(
        intent=intent,
        query_intent=query_intent,
        domains=selected_domains,
        candidates=top_candidates,
    )
    entities = _candidate_entities(selected_domains, top_candidates, fallback_route)
    freshness_need = _max_freshness(fallback_route["freshness_need"], _freshness_from_query(query))
    confidence = _confidence_from_candidates(top_candidates)
    subqueries = _candidate_subqueries(selected_domains, top_candidates, strategy)
    if strategy == "hybrid":
        subqueries = _merge_subqueries(subqueries, fallback_route.get("subqueries", []))

    if strategy == "rag_first" and confidence < 0.5:
        return _normalize_route(
            {
                **DEFAULT_ROUTE,
                "intent": intent,
                "freshness_need": _max_freshness(DEFAULT_ROUTE["freshness_need"], _freshness_from_query(query)),
                "reasoning_hint": "low-confidence candidate fallback to general website retrieval",
            }
        )

    route = {
        "intent": intent,
        "query_intent": query_intent,
        "domains": selected_domains,
        "entities": entities,
        "freshness_need": freshness_need,
        "subqueries": subqueries,
        "strategy": strategy,
        "confidence": confidence,
        "reasoning_hint": "candidate-informed routing from knowledge-base candidates",
    }
    return _normalize_route(route)


def _has_strong_in_scope_candidate(query: str, candidates: list[dict]) -> bool:
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return False

    for candidate in candidates:
        candidate_domains = [domain for domain in candidate.get("domains", []) if domain != "website_general"]
        if not candidate_domains:
            continue
        candidate_text = " ".join(
            part
            for part in (
                candidate.get("title", ""),
                candidate.get("text_preview", ""),
                _reference_text(candidate.get("reference_url", "")),
            )
            if part
        )
        if _field_token_score(query_tokens, candidate_text) >= max(1.5, len(query_tokens) * 0.75):
            return True
    return False


def _domain_alignment_score(query: str, domain: str, candidate: dict) -> float:
    query_text = query.lower()
    candidate_text = " ".join(
        part
        for part in (
            candidate.get("title", ""),
            candidate.get("text_preview", ""),
            _reference_text(candidate.get("reference_url", "")),
        )
        if part
    ).lower()

    hint_hits = 0.0
    for hint in DOMAIN_HINTS.get(domain, []):
        query_match = _hint_match_score(hint, query_text)
        candidate_match = _hint_match_score(hint, candidate_text)
        if query_match == 0 and candidate_match == 0:
            continue
        hint_hits += query_match * 2.0 + candidate_match

    if hint_hits == 0:
        return 0.4 if domain == "website_general" else 0.0
    return max(0.4, min(1.6, 0.4 + hint_hits / 3.0))


def _hint_match_score(hint: str, text: str) -> float:
    hint_tokens = _query_tokens(hint)
    if not hint_tokens:
        return 0.0
    text_words = _normalized_words(text)
    normalized_hint_tokens = [_stem_token(token) for token in hint_tokens]
    if all(token in text_words for token in normalized_hint_tokens):
        return 1.0
    return min(0.6, _field_token_score(hint_tokens, text) / max(1, len(hint_tokens)) * 0.6)


def _select_domains(query: str, domain_scores: dict[str, int]) -> list[str]:
    if not domain_scores:
        return []
    ordered = sorted(domain_scores.items(), key=lambda item: (-item[1], DOMAIN_ORDER.index(item[0])))
    top_score = ordered[0][1]
    wants_multiple = _wants_multiple_topics(query)
    selected = []
    for domain, score in ordered:
        if score < max(100, int(top_score * 0.65)):
            continue
        if not wants_multiple and selected:
            break
        selected.append(domain)
        if wants_multiple and len(selected) >= 2:
            break
    return selected or [ordered[0][0]]


def _infer_intent(query: str, fallback_route: dict, query_intent: str | None = None) -> str:
    normalized_query_intent = query_intent or _infer_query_intent(query)
    if normalized_query_intent == "comparison":
        return "comparison"
    if normalized_query_intent == "fact_lookup":
        return "fact_lookup"
    return fallback_route["intent"]


def _infer_candidate_strategy(*, intent: str, query_intent: str, domains: list[str], candidates: list[dict]) -> str:
    record_types = {candidate["record_type"] for candidate in candidates}
    has_statistical_domain = any(domain in STATISTICAL_DOMAINS for domain in domains)
    if intent == "advice_request" and not candidates:
        return "reject_or_clarify"
    if query_intent in {"release_lookup", "navigation", "explanation"} and has_statistical_domain:
        return "hybrid"
    if query_intent == "trend_over_time" and has_statistical_domain:
        return "sql_first"
    if len(domains) > 1:
        return "hybrid"
    if record_types & STRUCTURED_RECORD_TYPES and not record_types & TEXT_RECORD_TYPES and intent == "fact_lookup":
        return "sql_first"
    if domains == ["financial_education"] and intent == "advice_request":
        return "rag_first"
    if record_types <= TEXT_RECORD_TYPES:
        return "rag_first"
    if record_types & STRUCTURED_RECORD_TYPES and record_types & TEXT_RECORD_TYPES:
        return "hybrid"
    if domains == ["reserves_assets"] or domains == ["financial_soundness"]:
        return "hybrid"
    return _infer_fallback_strategy(domains, query_intent=query_intent, intent=intent)


def _candidate_entities(domains: list[str], candidates: list[dict], fallback_route: dict) -> list[str]:
    fallback_entities = list(fallback_route.get("entities", []))
    if fallback_entities and set(fallback_route.get("domains", [])).intersection(domains):
        return _normalize_string_list(fallback_entities)
    return _normalize_string_list([candidate["title"] for candidate in candidates[:2]])


def _candidate_subqueries(domains: list[str], candidates: list[dict], strategy: str) -> list[dict]:
    if strategy != "hybrid" or len(domains) <= 1:
        return []
    by_domain: dict[str, dict] = {}
    for candidate in candidates:
        for domain in candidate["domains"]:
            if domain in domains and domain not in by_domain:
                by_domain[domain] = candidate
    return [{"domain": domain, "query": by_domain[domain]["title"]} for domain in domains if domain in by_domain]


def _merge_subqueries(primary: list[dict], fallback: list[dict]) -> list[dict]:
    merged = list(primary)
    seen_domains = {item["domain"] for item in merged}
    for item in fallback:
        domain = item.get("domain")
        query = item.get("query")
        if domain in DOMAIN_TAXONOMY and query and domain not in seen_domains:
            merged.append({"domain": domain, "query": query})
            seen_domains.add(domain)
    return merged


def _confidence_from_candidates(candidates: list[dict]) -> float:
    if not candidates:
        return DEFAULT_ROUTE["confidence"]
    top_score = max(candidate["score"] for candidate in candidates)
    return min(0.95, round(0.35 + top_score / 1200, 3))


def _merge_llm_and_candidate_routes(*, query: str, llm_route: dict, candidate_route: dict, fallback_route: dict) -> dict:
    if candidate_route["domains"] == ["website_general"]:
        return llm_route
    if llm_route["domains"] == ["website_general"] and llm_route["strategy"] == DEFAULT_ROUTE["strategy"]:
        return candidate_route

    merged = dict(llm_route)
    merged["domains"] = _normalize_domains([*candidate_route["domains"], *llm_route.get("domains", [])])
    merged["entities"] = _normalize_string_list([*candidate_route["entities"], *llm_route.get("entities", [])])
    if llm_route.get("query_intent") in {None, "topic_overview"}:
        merged["query_intent"] = candidate_route.get("query_intent", llm_route.get("query_intent"))
    if llm_route.get("intent") in {"unknown", "topic_overview"} and candidate_route["intent"] != "topic_overview":
        merged["intent"] = candidate_route["intent"]
    merged["freshness_need"] = _max_freshness(candidate_route["freshness_need"], llm_route["freshness_need"])
    merged["strategy"] = _normalize_strategy(llm_route.get("strategy"), merged["domains"])
    if candidate_route["strategy"] == "hybrid":
        merged["strategy"] = "hybrid"
    merged["subqueries"] = candidate_route["subqueries"] if merged["strategy"] == "hybrid" else []
    merged["confidence"] = max(float(llm_route.get("confidence") or 0.0), candidate_route["confidence"], fallback_route["confidence"])
    return _normalize_route(merged)


def _build_router_user_prompt(query: str, candidates: list[dict]) -> str:
    payload = {
        "query": query,
        "candidates": [
            {
                "id": candidate["id"],
                "title": candidate["title"],
                "record_type": candidate["record_type"],
                "domains": candidate["domains"],
                "reference_url": candidate["reference_url"],
                "source_preference": candidate["source_preference"],
                "text_preview": candidate["text_preview"],
                "score": candidate["score"],
            }
            for candidate in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _route_with_rules(query: str) -> dict:
    lowered = query.lower()
    query_intent = _infer_query_intent(query)
    matches = []
    for rule in FALLBACK_RULES:
        positions = [lowered.find(term) for term in rule["terms"] if lowered.find(term) >= 0]
        if positions:
            matches.append((rule["priority"], min(positions), rule))

    query_domains = _domains_from_query_hints(query)
    if not matches and not query_domains:
        route = dict(DEFAULT_ROUTE)
        route["query_intent"] = query_intent
        route["entities"] = _entities_from_query(query, route["domains"])
        if _is_clearly_out_of_scope(query):
            route["strategy"] = "reject_or_clarify"
            route["reasoning_hint"] = "query appears outside OeNB knowledge scope"
            return route
        route["strategy"] = _infer_fallback_strategy(route["domains"], query_intent=query_intent, intent=route["intent"])
        return route

    matches = _consolidate_matches(matches)
    domains = []
    entities = []
    subqueries = []
    seen_domains = set()
    seen_entities = set()
    intent = "topic_overview"
    freshness_need = "low"

    for _, _, rule in matches:
        domain = rule["domain"]
        if domain not in seen_domains:
            domains.append(domain)
            seen_domains.add(domain)
            subqueries.append({"domain": domain, "query": rule["entity"]})
        entity = rule["entity"]
        if entity not in seen_entities:
            entities.append(entity)
            seen_entities.add(entity)
        if rule["intent"] == "fact_lookup":
            intent = "fact_lookup"
        freshness_need = _max_freshness(freshness_need, rule["freshness_need"])

    for domain in query_domains:
        if domain not in seen_domains:
            domains.append(domain)
            seen_domains.add(domain)

    domains = _augment_domains_for_query_intent(domains, query_intent)
    intent = _infer_intent(query, {"intent": intent}, query_intent)
    if not entities:
        entities = _entities_from_query(query, domains)
    strategy = _infer_fallback_strategy(domains, query_intent=query_intent, intent=intent)
    if strategy != "hybrid" or len(domains) <= 1:
        subqueries = []

    return _normalize_route(
        {
            "intent": intent,
            "query_intent": query_intent,
            "domains": domains,
            "entities": entities,
            "freshness_need": freshness_need,
            "subqueries": subqueries,
            "strategy": strategy,
            "confidence": _fallback_confidence(domains, entities),
            "reasoning_hint": "deterministic fallback routing from OeNB query rules",
        }
    )


def _consolidate_matches(matches: list[tuple[int, int, dict]]) -> list[tuple[int, int, dict]]:
    by_concept: dict[str, list[tuple[int, int, dict]]] = {}
    for item in matches:
        by_concept.setdefault(item[2]["concept_key"], []).append(item)

    consolidated: list[tuple[int, int, dict]] = []
    for concept_matches in by_concept.values():
        specific_matches = [item for item in concept_matches if item[2]["relation"] != "topic"]
        consolidated.extend(specific_matches or concept_matches)
    consolidated.sort(key=lambda entry: (entry[1], -entry[0]))
    return consolidated


def _infer_fallback_strategy(domains: list[str], *, query_intent: str | None = None, intent: str | None = None) -> str:
    normalized_query_intent = query_intent or "topic_overview"
    normalized_intent = intent or "topic_overview"
    has_statistical_domain = any(domain in STATISTICAL_DOMAINS for domain in domains)
    if len(domains) > 1:
        if set(domains).issubset({"monetary_policy", "interest_rates"}) and normalized_query_intent == "fact_lookup":
            return "sql_first"
        return "hybrid"
    if not domains:
        return DEFAULT_ROUTE["strategy"]
    domain = domains[0]
    if normalized_query_intent in {"release_lookup", "navigation", "explanation"} and has_statistical_domain:
        return "hybrid"
    if normalized_query_intent == "trend_over_time" and has_statistical_domain:
        return "sql_first"
    if domain in {
        "monetary_policy",
        "interest_rates",
        "commodity_prices",
        "real_estate",
        "external_sector",
    }:
        return "sql_first" if normalized_intent == "fact_lookup" else "hybrid"
    if domain in {"reserves_assets", "financial_soundness"}:
        return "hybrid"
    if domain in {"financial_education", "corporate_topics", "website_general"}:
        return "rag_first"
    return DEFAULT_ROUTE["strategy"]


def _normalize_route(raw: dict | None) -> dict:
    route = dict(DEFAULT_ROUTE)
    if raw:
        route["intent"] = str(raw.get("intent") or route["intent"]).strip() or route["intent"]
        route["query_intent"] = _normalize_query_intent(raw.get("query_intent"), route["intent"])
        route["domains"] = _normalize_domains(raw.get("domains"))
        route["entities"] = _normalize_string_list(raw.get("entities"))
        route["freshness_need"] = _normalize_freshness(raw.get("freshness_need"))
        route["subqueries"] = _normalize_subqueries(raw.get("subqueries"))
        route["strategy"] = _normalize_strategy(raw.get("strategy"), route["domains"])
        route["confidence"] = _normalize_confidence(raw.get("confidence"))
        route["reasoning_hint"] = str(raw.get("reasoning_hint") or route["reasoning_hint"]).strip()
    if not route["domains"]:
        route["domains"] = ["website_general"]
    if len(route["domains"]) <= 1 and route["strategy"] != "hybrid":
        route["subqueries"] = []
    return route


def _normalize_domains(value) -> list[str]:
    domains = []
    for domain in _normalize_string_list(value):
        if domain in DOMAIN_TAXONOMY and domain not in domains:
            domains.append(domain)
    return sorted(domains, key=lambda domain: DOMAIN_ORDER.index(domain))


def _normalize_freshness(value) -> str:
    normalized = str(value or "low").strip().lower()
    return normalized if normalized in FRESHNESS_LEVELS else "low"


def _normalize_strategy(value, domains: list[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in STRATEGIES:
        return normalized
    return _infer_fallback_strategy(domains)


def _normalize_query_intent(value, intent: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in QUERY_INTENTS:
        return normalized
    if intent in {"fact_lookup", "comparison", "advice_request"}:
        return intent
    return "topic_overview"


def _normalize_subqueries(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    subqueries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        query = str(item.get("query") or "").strip()
        if domain in DOMAIN_TAXONOMY and query:
            subqueries.append({"domain": domain, "query": query})
    return subqueries


def _normalize_string_list(value) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    normalized = []
    for item in items:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_confidence(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ROUTE["confidence"]
    return max(0.0, min(1.0, round(normalized, 3)))


def _fallback_confidence(domains: list[str], entities: list[str]) -> float:
    if not domains or domains == ["website_general"]:
        return 0.25
    if len(domains) > 1:
        return 0.72
    if entities:
        return 0.86
    return 0.65


def _freshness_from_query(query: str) -> str:
    lowered = query.lower()
    if any(term in lowered for term in ("aktuell", "current", "latest", "heute", "derzeit")):
        return "high"
    return "low"


def _query_tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{3,}", query.lower()) if not is_stopword(token)]


def _query_phrases(query: str) -> list[str]:
    lowered = query.lower()
    phrases = []
    for phrase in (
        "goldreserven",
        "gold reserve",
        "goldpreis",
        "einlagenfazilität",
        "frauen in führungsfunktionen",
        "kunstsammlung",
    ):
        if phrase in lowered:
            phrases.append(phrase)
    return phrases


def _infer_query_intent(query: str) -> str:
    lowered = query.lower()
    if "soll ich" in lowered or "sollte ich" in lowered:
        return "advice_request"
    if any(term in lowered for term in ("unterschied zwischen", "vergleich", "verglichen", "fixen und", "fixen oder")):
        return "comparison"
    if any(term in lowered for term in GENERIC_QUERY_INTENT_PATTERNS["trend_over_time"]):
        return "trend_over_time"
    if any(term in lowered for term in GENERIC_QUERY_INTENT_PATTERNS["release_lookup"]):
        return "release_lookup"
    if any(term in lowered for term in GENERIC_QUERY_INTENT_PATTERNS["navigation"]):
        return "navigation"
    if any(term in lowered for term in GENERIC_QUERY_INTENT_PATTERNS["explanation"]) or any(
        term in lowered for term in ("warum", "wieso", "weshalb", "was schreibt")
    ):
        return "explanation"
    if any(term in lowered for term in ("wie hoch", "wie viele", "wieviel", "wie viel", "was ist der", "was ist die")):
        return "fact_lookup"
    return "topic_overview"


def _domains_from_query_hints(query: str) -> list[str]:
    query_text = query.lower()
    domain_scores: dict[str, int] = {}
    for domain, hints in QUERY_DOMAIN_HINTS.items():
        score = 0
        for hint in hints:
            if hint in query_text:
                score += 100
        if score > 0:
            domain_scores[domain] = score
    return _select_domains(query, domain_scores) if domain_scores else []


def _augment_domains_for_query_intent(domains: list[str], query_intent: str) -> list[str]:
    normalized = [domain for domain in domains if domain in DOMAIN_TAXONOMY]
    if query_intent in {"release_lookup", "navigation"} and any(domain != "website_general" for domain in normalized):
        normalized.append("website_general")
    if not normalized:
        normalized = ["website_general"]
    return _normalize_domains(normalized)


def _entities_from_query(query: str, domains: list[str]) -> list[str]:
    lowered = query.lower()
    entities = [entity for needle, entity in QUERY_ENTITY_RULES if needle in lowered]
    if not entities and "financial_soundness" in domains and "banken" in lowered:
        entities.append("Oesterreichische Banken")
    return _normalize_string_list(entities)


def _is_clearly_out_of_scope(query: str) -> bool:
    lowered = query.lower()
    return not any(hint in lowered for hint in IN_SCOPE_HINTS)


def _should_prefer_fallback_route(query_intent: str, selected_domains: list[str], fallback_route: dict) -> bool:
    if query_intent not in {"release_lookup", "navigation", "explanation", "trend_over_time"}:
        return False
    fallback_statistical_domains = [domain for domain in fallback_route.get("domains", []) if domain in STATISTICAL_DOMAINS]
    if not fallback_statistical_domains:
        return False
    selected_statistical_domains = [domain for domain in selected_domains if domain in STATISTICAL_DOMAINS]
    if not selected_statistical_domains:
        return True
    return not set(selected_statistical_domains).intersection(fallback_statistical_domains)


def _wants_multiple_topics(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in (" und ", " or ", " oder ", ","))


def _max_freshness(current: str, incoming: str) -> str:
    ranking = {"low": 0, "medium": 1, "high": 2}
    return incoming if ranking[incoming] > ranking[current] else current


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route a user query into OeNB chatbot domains")
    parser.add_argument("query", help="Free-text user query")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    print(json.dumps(route_query(args.query), indent=2, ensure_ascii=False))
