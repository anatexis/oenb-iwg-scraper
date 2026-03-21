import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.chatbot_retrieval import default_knowledge_base_paths, retrieve_chatbot_knowledge, search_chatbot_knowledge


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_default_knowledge_base_paths_point_to_active_files(tmp_path: Path):
    primary, secondary = default_knowledge_base_paths(tmp_path)

    assert primary == tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    assert secondary == tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"


def test_search_chatbot_knowledge_uses_active_paths_by_default(tmp_path: Path):
    primary, secondary = default_knowledge_base_paths(tmp_path)
    _write_jsonl(
        primary,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
            }
        ],
    )
    _write_jsonl(
        secondary,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "full:pdf:1",
                "parent_record_type": "asset_document",
                "chunk_kind": "asset_document_summary",
                "title": "Historisches PDF",
                "text": "Leitzins in einem alten PDF.",
                "retrieval_score": 250,
                "retrieval_tier": "background",
                "reference_urls": ["https://www.oenb.at/old.pdf"],
            }
        ],
    )

    results = search_chatbot_knowledge("aktueller Leitzins", base_dir=tmp_path, limit=3)

    assert results[0]["id"] == "stats:family:1"
    assert results[0]["source_preference"] == "primary"


def test_retrieve_chatbot_knowledge_returns_hybrid_payload(tmp_path: Path):
    primary, secondary = default_knowledge_base_paths(tmp_path)
    _write_jsonl(
        primary,
        [
            {
                "record_type": "chatbot_chunk",
                "id": "stats:family:1",
                "parent_record_type": "dataset_family",
                "chunk_kind": "family_summary",
                "title": "Base and Reference Rates of the Oesterreichische Nationalbank",
                "text": "Latest observation: 11.06.25 = 1.53 % per annum.",
                "retrieval_score": 1000,
                "retrieval_tier": "primary",
                "reference_urls": ["https://www.oenb.at/en/Statistics/..."],
            }
        ],
    )
    _write_jsonl(secondary, [])

    result = retrieve_chatbot_knowledge("aktueller Leitzins", base_dir=tmp_path, limit=3)

    assert result["hits"][0]["id"] == "stats:family:1"
    assert "routing" in result
    assert "confidence" in result
