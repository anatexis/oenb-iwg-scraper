"""Tests for the SQLite FTS5 knowledge-base index."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.kb_index import (
    build_kb_index,
    has_index,
    index_path_for,
    record_by_id,
    search_candidates,
)


def _chunk(chunk_id, title, text, url, parent_record_type="page_document", retrieval_score=100):
    return {
        "record_type": "chatbot_chunk",
        "id": chunk_id,
        "parent_id": f"parent:{chunk_id}",
        "parent_record_type": parent_record_type,
        "title": title,
        "text": text,
        "reference_urls": [url],
        "retrieval_score": retrieval_score,
    }


def _write_kb(tmp_path):
    kb = tmp_path / "kb.jsonl"
    records = [
        _chunk("chunk:zins", "Zinssätze und Wechselkurse", "Tabelle mit Zinssätzen.",
               "https://www.oenb.at/statistik/zinssaetze.html"),
        _chunk("chunk:error", "Fehlerseite - OeNB", "403 Forbidden",
               "https://www.oenb.at/Bargeld.html"),
        {"record_type": "page_document", "id": "parent:chunk:zins",
         "title": "Zinssätze", "url": "https://www.oenb.at/statistik/zinssaetze.html"},
    ]
    kb.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return kb


def test_build_creates_sibling_index(tmp_path):
    kb = _write_kb(tmp_path)
    index_path = build_kb_index(kb)
    assert index_path == index_path_for(kb)
    assert index_path.exists()
    assert has_index(kb)


def test_search_candidates_folds_umlauts_both_ways(tmp_path):
    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    # ASCII query token must match umlaut spelling in the KB
    hits = search_candidates(kb, ["zinssaetze"], limit=10)
    assert [h["id"] for h in hits] == ["chunk:zins"]
    # umlaut query token must match as well
    hits = search_candidates(kb, ["zinssätze"], limit=10)
    assert [h["id"] for h in hits] == ["chunk:zins"]


def test_search_candidates_supports_prefix_and_phrases(tmp_path):
    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    assert search_candidates(kb, ["zins"], limit=10), "prefix must match"
    assert search_candidates(kb, ["zinssätze und wechselkurse"], limit=10), "phrase must match"


def test_error_page_chunks_are_not_indexed(tmp_path):
    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    hits = search_candidates(kb, ["bargeld"], limit=10)
    assert hits == []


def test_record_by_id_returns_any_record_type(tmp_path):
    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    parent = record_by_id(kb, "parent:chunk:zins")
    assert parent["record_type"] == "page_document"
    assert record_by_id(kb, "missing") is None


def test_has_index_false_without_build(tmp_path):
    kb = _write_kb(tmp_path)
    assert not has_index(kb)


def test_search_knowledge_base_uses_index_when_present(tmp_path, monkeypatch):
    from analysis import kb_index
    from analysis.query_knowledge_base import search_knowledge_base

    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    calls = {}
    original = kb_index.search_candidates

    def spy(path, tokens, **kwargs):
        calls["path"] = path
        return original(path, tokens, **kwargs)

    monkeypatch.setattr("analysis.query_knowledge_base.kb_index_search_candidates", spy)

    results = search_knowledge_base(
        query="Wo finde ich Zinssätze?",
        primary_path=kb,
        secondary_path=None,
        limit=5,
        routed_query={"query_intent": "navigation", "domains": ["website_general"], "subqueries": [], "entities": []},
    )
    assert calls["path"] == kb
    assert [r["id"] for r in results] == ["chunk:zins"]


def test_knowledge_base_cache_record_by_id_uses_index_without_full_load(tmp_path):
    from analysis.knowledge_base_cache import KnowledgeBaseCache

    kb = _write_kb(tmp_path)
    build_kb_index(kb)
    cache = KnowledgeBaseCache()
    record = cache.record_by_id(kb, "parent:chunk:zins")
    assert record["record_type"] == "page_document"
    assert cache._records_by_path == {}, "index lookup must not load the whole JSONL"


def test_bm25_blend_lets_rare_token_beat_generic_archive_pages(tmp_path):
    # nav_006 regression: hundreds of archive issues match generic tokens
    # ("daten", "statistik") and tie above the specific hit. The BM25 rank
    # from the index must break that tie in favor of the rare token.
    from analysis.query_knowledge_base import search_knowledge_base

    kb = tmp_path / "kb.jsonl"
    records = [
        _chunk(
            f"chunk:archiv{i}",
            f"Statistiken - Daten und Analysen Q{i % 4 + 1}-0{i % 9} - OeNB",
            "Statistiken Daten und Analysen Archivausgabe.",
            f"https://www.oenb.at/Publikationen/Statistik/archiv-{i}.html",
        )
        for i in range(30)
    ]
    records.append(
        _chunk(
            "chunk:finanzsektor",
            "Daten zum Finanzsektor - Statistik - OeNB",
            "Statistische Daten zum oesterreichischen Finanzsektor.",
            "https://www.oenb.at/statistik/finanzsektor.html",
        )
    )
    kb.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    build_kb_index(kb)

    results = search_knowledge_base(
        query="Wo finde ich statistische Daten zum oesterreichischen Finanzsektor?",
        primary_path=kb,
        secondary_path=None,
        limit=5,
        routed_query={"query_intent": "navigation", "domains": ["website_general"], "subqueries": [], "entities": []},
    )
    assert results[0]["id"] == "chunk:finanzsektor"
