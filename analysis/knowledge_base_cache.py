"""Reusable in-memory cache for JSONL knowledge-base records."""

from __future__ import annotations

import json
from pathlib import Path

from analysis.kb_index import has_index as _has_kb_index
from analysis.kb_index import record_by_id as _index_record_by_id


class KnowledgeBaseCache:
    """Load JSONL knowledge-base files once and reuse them across queries."""

    def __init__(self) -> None:
        self._records_by_path: dict[Path, list[dict]] = {}
        self._record_index_by_path: dict[Path, dict[str, dict]] = {}

    def records(self, path: Path | None) -> list[dict]:
        if path is None or not path.exists():
            return []
        normalized = path.resolve()
        if normalized not in self._records_by_path:
            records: list[dict] = []
            record_index: dict[str, dict] = {}
            with normalized.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    records.append(record)
                    record_id = record.get("id")
                    if record_id:
                        record_index[str(record_id)] = record
            self._records_by_path[normalized] = records
            self._record_index_by_path[normalized] = record_index
        return self._records_by_path[normalized]

    def record_by_id(self, path: Path | None, record_id: str | None) -> dict | None:
        if path is None or not record_id or not path.exists():
            return None
        normalized = path.resolve()
        if normalized in self._record_index_by_path:
            return self._record_index_by_path[normalized].get(str(record_id))
        if _has_kb_index(normalized):
            # Point lookup via the FTS index sidecar — avoids loading the
            # whole JSONL (2+ GB for the statistics KB) into memory.
            return _index_record_by_id(normalized, record_id)
        self.records(normalized)
        return self._record_index_by_path[normalized].get(str(record_id))
