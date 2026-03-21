"""Validate exported knowledge-base JSONL coverage."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def validate_knowledge_base_jsonl(path: Path) -> dict:
    """Return high-level coverage metrics for a JSONL knowledge base export."""

    record_counts: Counter[str] = Counter()
    chunk_parent_counts: Counter[str] = Counter()
    dataset_families_with_sources = 0
    total_records = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total_records += 1
            record = json.loads(line)
            record_type = record.get("record_type", "unknown")
            record_counts[record_type] += 1

            if record_type == "dataset_family" and record.get("sources"):
                dataset_families_with_sources += 1
            if record_type == "chatbot_chunk":
                chunk_parent_counts[record.get("parent_record_type", "unknown")] += 1

    return {
        "total_records": total_records,
        "record_counts": dict(record_counts),
        "dataset_families_with_sources": dataset_families_with_sources,
        "chunk_parent_counts": dict(chunk_parent_counts),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate an exported knowledge-base JSONL")
    parser.add_argument("path", type=Path, help="Path to the JSONL file")
    args = parser.parse_args()

    summary = validate_knowledge_base_jsonl(args.path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
