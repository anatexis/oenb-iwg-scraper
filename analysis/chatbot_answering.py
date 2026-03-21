"""Build concise chatbot-ready answers from stats-first retrieval hits."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from analysis.agentic_search import maybe_run_agentic_search
from analysis.chatbot_retrieval import default_knowledge_base_paths, retrieve_chatbot_knowledge
from analysis.isaweb_live_lookup import default_live_lookup
from analysis.text_stopwords import is_stopword


def answer_chatbot_question(
    query: str,
    *,
    base_dir: Path | None = None,
    primary_path: Path | None = None,
    secondary_path: Path | None = None,
    limit: int = 5,
    include_debug: bool = False,
    agentic_enabled: bool = False,
    knowledge_base_cache=None,
) -> dict:
    base = base_dir or Path.cwd()
    if primary_path is None or secondary_path is None:
        resolved_primary, resolved_secondary = default_knowledge_base_paths(base)
        primary_path = primary_path or resolved_primary
        secondary_path = secondary_path or resolved_secondary

    retrieval_payload = retrieve_chatbot_knowledge(
        query,
        base_dir=base,
        primary_path=primary_path,
        secondary_path=secondary_path,
        limit=limit,
        knowledge_base_cache=knowledge_base_cache,
    )
    hits = retrieval_payload["hits"]
    agentic_result = maybe_run_agentic_search(
        query=query,
        retrieval_payload=retrieval_payload,
        live_lookup=default_live_lookup,
        enabled=agentic_enabled,
    )
    if not hits:
        response = {
            "query": query,
            "answer_type": "not_found",
            "answer": "Ich habe in der aktuellen Wissensbasis keine passende Antwort gefunden.",
            "citations": [],
            "sources": [],
            "release_dates": [],
        }
        if include_debug:
            response["hits"] = []
            response["routing"] = retrieval_payload.get("routing")
            response["agentic_result"] = agentic_result
        return response

    if not _is_grounded_top_hit(query, retrieval_payload.get("routing"), hits[0]):
        response = {
            "query": query,
            "answer_type": "not_found",
            "answer": "Ich habe in der aktuellen Wissensbasis keinen belastbaren Treffer für diese Frage gefunden.",
            "citations": [],
            "sources": [],
            "release_dates": [],
        }
        if include_debug:
            response["hits"] = hits
            response["routing"] = retrieval_payload.get("routing")
            response["agentic_result"] = agentic_result
        return response

    routing = retrieval_payload.get("routing") or {}
    if retrieval_payload.get("subquery_results") and _should_render_subquery_answers(query, routing):
        subanswers = []
        citation_urls: list[str] = []
        sources: list[str] = []
        release_dates: list[str] = []
        for subquery_result in _ordered_subquery_results(routing, retrieval_payload["subquery_results"]):
            label = subquery_result.get("query") or subquery_result.get("domain") or "Teilfrage"
            if not subquery_result.get("hits"):
                subanswers.append(
                    {
                        "label": label,
                        "domain": subquery_result.get("domain"),
                        "answer": "Keine passende Reihe in der aktuellen Wissensbasis gefunden.",
                    }
                )
                continue
            subpayload = _build_answer_payload_for_hit(
                query=query,
                hit=subquery_result["hits"][0],
                primary_path=primary_path,
                secondary_path=secondary_path,
                knowledge_base_cache=knowledge_base_cache,
                routing=routing,
            )
            subanswers.append(
                {
                    "label": label,
                    "domain": subquery_result.get("domain"),
                    "answer": subpayload["answer"],
                }
            )
            citation_urls.extend(item["url"] for item in subpayload["citations"])
            sources.extend(subpayload["sources"])
            release_dates.extend(subpayload["release_dates"])

        response = {
            "query": query,
            "answer_type": "multi_part",
            "answer": _render_subanswers_text(routing, subanswers),
            "citations": _citation_payload(citation_urls),
            "sources": _unique_strings(sources),
            "release_dates": _unique_strings(release_dates),
            "subanswers": subanswers,
        }
        if include_debug:
            response["hits"] = hits
            response["routing"] = retrieval_payload.get("routing")
            response["agentic_result"] = agentic_result
        return response

    response = _build_answer_payload_for_hit(
        query=query,
        hit=hits[0],
        primary_path=primary_path,
        secondary_path=secondary_path,
        knowledge_base_cache=knowledge_base_cache,
        routing=routing,
    )
    if include_debug:
        response["hits"] = hits
        response["top_hit"] = hits[0]
        response["parent_record"] = response.get("_parent_record")
        response["routing"] = retrieval_payload.get("routing")
        response["agentic_result"] = agentic_result
    response.pop("_parent_record", None)
    return response


def _build_answer_payload_for_hit(
    *,
    query: str,
    hit: dict,
    primary_path: Path | None,
    secondary_path: Path | None,
    knowledge_base_cache=None,
    routing: dict | None = None,
) -> dict:
    parent = _load_parent_record(
        hit["parent_id"],
        primary_path if hit.get("source_preference") == "primary" else secondary_path,
        knowledge_base_cache=knowledge_base_cache,
    )
    if not parent:
        return {
            "query": query,
            "answer_type": hit.get("parent_record_type", "chatbot_chunk"),
            "answer": hit.get("text", ""),
            "citations": _citation_payload(hit.get("reference_urls", [])),
            "sources": hit.get("sources", []),
            "release_dates": [],
            "_parent_record": None,
        }

    latest = parent.get("latest_observation") or {}
    latest_rows = parent.get("latest_observations") or []
    latest_text = _format_latest_observation_text(query, parent.get("title", hit.get("title", "")), latest, latest_rows)

    release_dates = [
        event["release_date_text"]
        for event in parent.get("release_events", [])
        if _is_meaningful_release_date(event.get("release_date_text"))
    ]
    release_text = f" Nächste Veröffentlichung: {release_dates[0]}." if release_dates else ""

    title = parent.get("title", hit.get("title", "Treffer"))
    query_intent = (routing or {}).get("query_intent")
    intent_suffix = _intent_aware_suffix(query, query_intent, title, hit)

    answer = f"{title}.{latest_text}{release_text}{intent_suffix}".strip()
    source_urls = _core_citation_urls(parent, hit)

    return {
        "query": query,
        "answer_type": parent.get("record_type", hit.get("parent_record_type", "chatbot_chunk")),
        "answer": answer,
        "citations": _citation_payload(source_urls),
        "sources": parent.get("sources", hit.get("sources", [])),
        "release_dates": release_dates,
        "_parent_record": parent,
    }


def _is_grounded_top_hit(query: str, routing: dict | None, hit: dict) -> bool:
    if not hit:
        return False
    if not routing:
        return True
    if routing.get("domains") == ["website_general"] and hit.get("parent_record_type") == "asset_document":
        return False
    if routing.get("strategy") == "rag_first" and routing.get("domains") == ["website_general"] and float(
        routing.get("confidence") or 0.0
    ) < 0.55:
        return False
    if hit.get("parent_record_type") == "dataset_family":
        return True

    haystack = _sanitize_grounding_text(
        " ".join(
            str(part)
            for part in (
                hit.get("title"),
                hit.get("text"),
                " ".join(hit.get("reference_urls") or []),
            )
            if part
        ).lower()
    )
    grounding_terms = _grounding_terms(query, routing)
    grounded_hits = sum(1 for term in grounding_terms if _term_matches_text(term, haystack))
    primary_terms = _primary_grounding_terms(query, routing)
    primary_grounded = any(_term_matches_text(term, haystack) for term in primary_terms)

    if routing.get("strategy") == "rag_first" and hit.get("parent_record_type") == "asset_document":
        return primary_grounded
    if routing.get("strategy") == "rag_first" and routing.get("domains") == ["website_general"]:
        return primary_grounded and float(routing.get("confidence") or 0.0) >= 0.55
    return primary_grounded or grounded_hits >= 1 or float(routing.get("confidence") or 0.0) >= 0.8


def _load_parent_record(parent_id: str, path: Path | None, *, knowledge_base_cache=None) -> dict | None:
    if knowledge_base_cache is not None:
        return knowledge_base_cache.record_by_id(path, parent_id)
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("id") == parent_id:
                return record
    return None


def _grounding_terms(query: str, routing: dict) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{4,}", _sanitize_grounding_text(query.lower())):
        normalized = _stem_token(token)
        if normalized and normalized not in seen and not is_stopword(normalized):
            terms.append(normalized)
            seen.add(normalized)
    for entity in routing.get("entities", []):
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{4,}", _sanitize_grounding_text(str(entity).lower())):
            normalized = _stem_token(token)
            if normalized and normalized not in seen and not is_stopword(normalized):
                terms.append(normalized)
                seen.add(normalized)
    return terms


def _primary_grounding_terms(query: str, routing: dict) -> list[str]:
    entity_terms: list[str] = []
    seen: set[str] = set()
    for entity in routing.get("entities", []):
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{4,}", _sanitize_grounding_text(str(entity).lower())):
            normalized = _stem_token(token)
            if normalized and normalized not in seen and not is_stopword(normalized):
                entity_terms.append(normalized)
                seen.add(normalized)
    if entity_terms:
        return entity_terms

    query_terms = _grounding_terms(query, routing)
    return sorted(query_terms, key=len, reverse=True)[:2]


def _should_render_subquery_answers(query: str, routing: dict) -> bool:
    query_intent = routing.get("query_intent")
    if query_intent in {"release_lookup", "navigation"}:
        return True
    if query_intent == "topic_overview":
        lowered = query.lower()
        return any(term in lowered for term in (" und ", " or ", " oder ", ","))
    return False


def _ordered_subquery_results(routing: dict, subquery_results: list[dict]) -> list[dict]:
    query_intent = routing.get("query_intent")
    if query_intent not in {"release_lookup", "navigation"}:
        return subquery_results
    return sorted(
        subquery_results,
        key=lambda item: (
            0 if item.get("domain") == "website_general" else 1,
            item.get("domain") or "",
        ),
    )


def _render_subanswers_text(routing: dict, subanswers: list[dict]) -> str:
    query_intent = routing.get("query_intent")
    if query_intent not in {"release_lookup", "navigation"}:
        return " ".join(f"{item['label']}: {item['answer']}" for item in subanswers)

    parts: list[str] = []
    for index, item in enumerate(subanswers):
        if index == 0 and item.get("domain") == "website_general":
            parts.append(item["answer"])
            continue
        parts.append(f"{item['label']}: {item['answer']}")
    return " ".join(parts)


def _term_matches_text(term: str, text: str) -> bool:
    words = {_stem_token(token) for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]{4,}", _sanitize_grounding_text(text.lower()))}
    if term in words:
        return True
    return any(len(term) >= 5 and len(word) >= 4 and (term in word or word in term) for word in words)


def _sanitize_grounding_text(text: str) -> str:
    sanitized = text
    for boilerplate in ("oesterreichische nationalbank",):
        sanitized = sanitized.replace(boilerplate, " ")
    sanitized = re.sub(r"\boenb\b", " ", sanitized)
    return " ".join(sanitized.split())


def _stem_token(token: str) -> str:
    normalized = token.lower()
    for suffix in ("innen", "ungen", "eren", "ern", "en", "er", "es", "e", "n", "s"):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 4:
            return normalized[: -len(suffix)]
    return normalized


def _citation_payload(urls: list[str], *, limit: int = 5) -> list[dict]:
    seen = set()
    citations = []
    for url in urls:
        normalized = _normalize_citation_url(url)
        if not normalized or normalized in seen:
            continue
        citations.append({"url": normalized})
        seen.add(normalized)
        if len(citations) >= limit:
            break
    return citations


def _is_meaningful_release_date(value: str | None) -> bool:
    cleaned = (value or "").strip()
    return bool(cleaned) and cleaned.lower() not in {"no date available", "n/a", "na"}


def _normalize_citation_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    path = parts.path.split(";jsessionid", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _format_latest_observation_text(query: str, title: str, latest: dict, latest_rows: list[dict]) -> str:
    lowered_query = query.lower()
    if latest_rows:
        valid_rows = [row for row in latest_rows if row.get("value")]
        period = valid_rows[0].get("period") if valid_rows else None
        focused_rows = _focus_latest_rows(query, valid_rows)
        if _is_gold_query_without_gold_row(lowered_query, title, valid_rows, focused_rows):
            return " In der aktuell materialisierten Wissensbasis ist in dieser Rohstofftabelle kein expliziter Gold-Wert als letzte Beobachtung verfügbar."
        if len(valid_rows) > 4:
            focus_row = next(
                (row for row in focused_rows if (row.get("series_label") or "").strip().lower() == "euro area"),
                focused_rows[0],
            )
            unit = f" {focus_row['unit']}" if focus_row.get("unit") else ""
            label = focus_row.get("series_label") or "Value"
            extra_count = max(len(valid_rows) - 1, 0)
            if period:
                return (
                    f" Stand Wissensbasis: {period}. {label} = {focus_row['value']}{unit}. "
                    f"Tabelle enthält außerdem {extra_count} weitere Reihen."
                )

        series_parts = []
        for row in focused_rows:
            unit = f" {row['unit']}" if row.get("unit") else ""
            label = row.get("series_label") or "Value"
            series_parts.append(f"{label} = {row['value']}{unit}")
        if period and series_parts:
            return f" Stand Wissensbasis: {period}. " + "; ".join(series_parts) + "."

    unit = f" {latest['unit']}" if latest.get("unit") else ""
    if _is_gold_query_without_gold_row(lowered_query, title, [latest] if latest else [], []):
        return " In der aktuell materialisierten Wissensbasis ist in dieser Rohstofftabelle kein expliziter Gold-Wert als letzte Beobachtung verfügbar."
    if latest.get("value") and latest.get("period"):
        return f" Stand Wissensbasis: {latest['period']} = {latest['value']}{unit}."
    return ""


def _intent_aware_suffix(query: str, query_intent: str | None, title: str, hit: dict) -> str:
    if query_intent == "trend_over_time":
        return " Die verlinkte Tabelle enthält die vollständige Zeitreihe zur historischen Entwicklung."
    if query_intent == "comparison":
        chunk_text = hit.get("text") or ""
        sources_snippet = _extract_sources_snippet(chunk_text)
        if sources_snippet:
            return f" Quellen und Berechnungsgrundlage: {sources_snippet}"
        return " Details zur Berechnungsgrundlage finden Sie auf der verlinkten Seite."
    lowered = query.lower()
    if any(w in lowered for w in ("wo ", "where ", "lagerort", "standort")):
        return " Diese Tabelle enthält Bestandsdaten. Für weiterführende Informationen siehe die verlinkte Seite."
    return ""


def _extract_sources_snippet(chunk_text: str) -> str:
    for marker in ("Sources:", "Quellen:"):
        if marker not in chunk_text:
            continue
        after = chunk_text.split(marker, 1)[1].strip()
        for cutoff in ("Supporting pages:", "Unterstützende Seiten:"):
            if cutoff in after:
                after = after.split(cutoff, 1)[0].strip()
        return after[:200].rstrip(". ") + "." if after else ""
    return ""


def _focus_latest_rows(query: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    lowered_query = query.lower()
    preferred_labels = []
    if "goldpreis" in lowered_query or " gold" in f" {lowered_query}":
        preferred_labels.extend(["gold"])
    if "einlagenfazilität" in lowered_query or "deposit facility" in lowered_query or "leitzins" in lowered_query:
        preferred_labels.extend(["euro area", "deposit facility"])
    if not preferred_labels:
        return rows

    focused = [
        row
        for row in rows
        if any(label in (row.get("series_label") or "").strip().lower() for label in preferred_labels)
    ]
    return focused or rows


def _is_gold_query_without_gold_row(
    lowered_query: str,
    title: str,
    rows: list[dict],
    focused_rows: list[dict],
) -> bool:
    if "goldpreis" not in lowered_query and " gold" not in f" {lowered_query}":
        return False
    if "commodity" not in title.lower() and "rohstoff" not in title.lower():
        return False
    candidates = focused_rows or rows
    if not candidates:
        return True
    return not any("gold" in (row.get("series_label") or "").strip().lower() for row in candidates)


def _core_citation_urls(parent: dict, top_hit: dict) -> list[str]:
    urls = []
    source_page = parent.get("source_page") or {}
    isaweb_dataset = parent.get("isaweb_dataset") or {}
    isaweb_metadata = parent.get("isaweb_metadata") or {}

    for candidate in (
        source_page.get("url"),
        isaweb_dataset.get("source_url"),
        isaweb_metadata.get("meta_url"),
    ):
        if candidate and candidate not in urls:
            urls.append(candidate)

    if not urls:
        urls.extend(top_hit.get("reference_urls", []))
    return urls


def _unique_strings(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if value and value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a chatbot-ready answer from the OeNB knowledge bases")
    parser.add_argument("query", help="Free-text query")
    parser.add_argument(
        "--base-dir",
        type=Path,
        nargs="?",
        const=Path.cwd(),
        default=Path.cwd(),
        help="Worktree root containing data/",
    )
    parser.add_argument("--primary", type=Path, default=None, help="Optional primary knowledge-base path")
    parser.add_argument("--secondary", type=Path, default=None, help="Optional fallback knowledge-base path")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of retrieval hits")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    answer = answer_chatbot_question(
        args.query,
        base_dir=args.base_dir,
        primary_path=args.primary,
        secondary_path=args.secondary,
        limit=args.limit,
        include_debug=False,
    )
    print(json.dumps(answer, indent=2, ensure_ascii=False))
