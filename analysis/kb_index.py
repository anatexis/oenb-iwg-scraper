"""SQLite FTS5 index for JSONL knowledge bases.

The index is a sibling file (``KB.jsonl.index.db``) holding every record for
id lookups plus an FTS5 table over chatbot chunks. Retrieval uses it as a
BM25-ranked candidate generator; without an index the callers fall back to
the linear JSONL scan.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_FOLD_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

ERROR_TITLE_MARKERS = ("fehlerseite", "403 forbidden", "404 not found", "page not found")


def fold_text(text: str) -> str:
    return text.lower().translate(_FOLD_MAP)


def is_error_page_chunk(record: dict) -> bool:
    """Crawled 403/404 responses ended up in the KB — never surface them."""
    title = (record.get("title") or "").lower()
    text = (record.get("text") or "").lower()
    if any(marker in title for marker in ERROR_TITLE_MARKERS):
        return True
    return text.startswith("403 forbidden") or text.startswith("404 not found")


def index_path_for(jsonl_path: Path) -> Path:
    return jsonl_path.with_name(jsonl_path.name + ".index.db")


def has_index(jsonl_path: Path | None) -> bool:
    return jsonl_path is not None and index_path_for(jsonl_path).exists()


def build_kb_index(jsonl_path: Path, *, batch_size: int = 5000) -> Path:
    index_path = index_path_for(jsonl_path)
    if index_path.exists():
        index_path.unlink()
    connection = sqlite3.connect(index_path)
    try:
        connection.executescript(
            """
            CREATE TABLE records (id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
            CREATE VIRTUAL TABLE chunks USING fts5(
                id UNINDEXED, title, text, url, sources, tokenize='unicode61'
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        stat = jsonl_path.stat()
        connection.execute("INSERT INTO meta VALUES ('source_size', ?)", (str(stat.st_size),))
        connection.execute("INSERT INTO meta VALUES ('source_mtime', ?)", (str(stat.st_mtime),))

        record_rows: list[tuple[str, str]] = []
        chunk_rows: list[tuple[str, str, str, str, str]] = []
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                record_id = str(record.get("id") or "")
                if not record_id:
                    continue
                record_rows.append((record_id, line.strip()))
                if record.get("record_type") == "chatbot_chunk" and not is_error_page_chunk(record):
                    reference_urls = record.get("reference_urls") or []
                    chunk_rows.append(
                        (
                            record_id,
                            fold_text(str(record.get("title") or "")),
                            fold_text(str(record.get("text") or "")),
                            fold_text(" ".join(str(u) for u in reference_urls)),
                            fold_text(" ".join(record.get("sources") or [])),
                        )
                    )
                if len(record_rows) >= batch_size:
                    _flush(connection, record_rows, chunk_rows)
        _flush(connection, record_rows, chunk_rows)
        connection.commit()
    finally:
        connection.close()
    return index_path


def _flush(connection, record_rows, chunk_rows) -> None:
    if record_rows:
        connection.executemany(
            "INSERT OR REPLACE INTO records VALUES (?, ?)", record_rows
        )
        record_rows.clear()
    if chunk_rows:
        connection.executemany(
            "INSERT INTO chunks (id, title, text, url, sources) VALUES (?, ?, ?, ?, ?)",
            chunk_rows,
        )
        chunk_rows.clear()


def _fts_query(tokens: list[str]) -> str:
    parts: list[str] = []
    for token in tokens:
        folded = fold_text(str(token).strip()).replace('"', " ").strip()
        if not folded:
            continue
        if " " in folded:
            parts.append(f'"{folded}"')
        else:
            parts.append(f'"{folded}"*')
    return " OR ".join(parts)


def _connect_readonly(index_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)


def search_candidates(jsonl_path: Path, tokens: list[str], *, limit: int = 400) -> list[dict]:
    """Return chunk records matching any token, best BM25 rank first."""
    match_query = _fts_query(tokens)
    if not match_query:
        return []
    connection = _connect_readonly(index_path_for(jsonl_path))
    try:
        # Unweighted BM25: column weighting (title>text) was measured on the
        # 67-case eval and changed nothing — the noise cases match generic
        # tokens in titles too. Keep the simple form.
        rows = connection.execute(
            """
            SELECT records.record_json, chunks.rank
            FROM chunks JOIN records ON records.id = chunks.id
            WHERE chunks MATCH ?
            ORDER BY chunks.rank
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
    finally:
        connection.close()
    candidates = []
    for record_json, rank in rows:
        record = json.loads(record_json)
        record["_bm25_rank"] = rank
        candidates.append(record)
    return candidates


def record_by_id(jsonl_path: Path, record_id: str | None) -> dict | None:
    if not record_id or not has_index(jsonl_path):
        return None
    connection = _connect_readonly(index_path_for(jsonl_path))
    try:
        row = connection.execute(
            "SELECT record_json FROM records WHERE id = ?", (str(record_id),)
        ).fetchone()
    finally:
        connection.close()
    return json.loads(row[0]) if row else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the FTS5 index for a KB JSONL file")
    parser.add_argument("jsonl", type=Path, help="Knowledge-base JSONL path")
    args = parser.parse_args()
    path = build_kb_index(args.jsonl)
    print(f"index written: {path}")
