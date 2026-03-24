import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.refresh_knowledge_base import (
    build_scrapy_command,
    refresh_knowledge_base,
    smoke_refresh_knowledge_base,
)
from analysis.validate_knowledge_base import validate_knowledge_base_jsonl


def test_build_scrapy_command_defaults_to_frontier_incremental_mode(tmp_path: Path):
    db_path = tmp_path / "pages.db"
    output_path = tmp_path / "crawl.json"

    command = build_scrapy_command(
        db_path=db_path,
        output_json_path=output_path,
        use_frontier=True,
        frontier_limit=250,
    )

    joined = " ".join(command)
    assert "-m scrapy crawl oenb" in joined
    assert f"SQLITE_DB_PATH={db_path}" in joined
    assert "-a use_frontier=true" in joined
    assert f"-a frontier_db_path={db_path}" in joined
    assert "-a frontier_limit=250" in joined
    assert str(output_path) in joined


def test_build_scrapy_command_can_forward_frontier_kinds(tmp_path: Path):
    db_path = tmp_path / "pages.db"

    command = build_scrapy_command(
        db_path=db_path,
        use_frontier=True,
        frontier_limit=250,
        frontier_kinds=["isaweb_entry", "isaweb_dataset", "dataset_metadata"],
    )

    joined = " ".join(command)
    assert "-a frontier_kinds=isaweb_entry,isaweb_dataset,dataset_metadata" in joined


def test_build_scrapy_command_can_enable_isaweb_focus_mode(tmp_path: Path):
    db_path = tmp_path / "pages.db"

    command = build_scrapy_command(
        db_path=db_path,
        use_frontier=True,
        frontier_limit=250,
        isaweb_focus=True,
    )

    joined = " ".join(command)
    assert "-a isaweb_focus=true" in joined


def test_refresh_knowledge_base_runs_crawl_then_extract_then_export(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pages.db"
    output_path = tmp_path / "knowledge_base.jsonl"
    crawl_output_path = tmp_path / "crawl.json"

    calls = []

    def fake_run(command, check, cwd):
        calls.append(("crawl", command, cwd))

    def fake_extract(db_path_arg, extractor_version):
        calls.append(("extract", db_path_arg, extractor_version))
        return 12

    def fake_export(db_path_arg, output_path_arg):
        calls.append(("export", db_path_arg, output_path_arg))
        return 34

    monkeypatch.setattr("analysis.refresh_knowledge_base.subprocess.run", fake_run)
    monkeypatch.setattr("analysis.refresh_knowledge_base.run_extraction", fake_extract)
    monkeypatch.setattr("analysis.refresh_knowledge_base.export_knowledge_base_jsonl", fake_export)

    summary = refresh_knowledge_base(
        db_path=db_path,
        output_path=output_path,
        crawl_output_path=crawl_output_path,
        use_frontier=True,
        frontier_limit=150,
        extractor_version="kb-v1",
    )

    assert calls[0][0] == "crawl"
    assert calls[1] == ("extract", db_path, "kb-v1")
    assert calls[2] == ("export", db_path, output_path)
    assert summary == {"extracted_pages": 12, "exported_records": 34}


def test_build_scrapy_command_can_apply_smoke_page_limit(tmp_path: Path):
    db_path = tmp_path / "pages.db"

    command = build_scrapy_command(
        db_path=db_path,
        use_frontier=True,
        frontier_limit=50,
        page_limit=25,
    )

    joined = " ".join(command)
    assert "CLOSESPIDER_PAGECOUNT=25" in joined


def test_build_scrapy_command_uses_absolute_paths(tmp_path: Path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    command = build_scrapy_command(
        db_path=Path("data/pages.db"),
        output_json_path=Path("data/crawl.json"),
    )

    joined = " ".join(command)
    assert f"SQLITE_DB_PATH={project_dir / 'data/pages.db'}" in joined
    assert str(project_dir / "data/crawl.json") in joined


def test_smoke_refresh_knowledge_base_uses_smoke_defaults(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pages.db"
    output_path = tmp_path / "knowledge_base.jsonl"
    crawl_output_path = tmp_path / "crawl.json"

    calls = []

    def fake_run(command, check, cwd):
        calls.append(("crawl", command, cwd))

    def fake_extract(db_path_arg, extractor_version):
        calls.append(("extract", db_path_arg, extractor_version))
        return 5

    def fake_export(db_path_arg, output_path_arg):
        calls.append(("export", db_path_arg, output_path_arg))
        return 11

    monkeypatch.setattr("analysis.refresh_knowledge_base.subprocess.run", fake_run)
    monkeypatch.setattr("analysis.refresh_knowledge_base.run_extraction", fake_extract)
    monkeypatch.setattr("analysis.refresh_knowledge_base.export_knowledge_base_jsonl", fake_export)

    summary = smoke_refresh_knowledge_base(
        db_path=db_path,
        output_path=output_path,
        crawl_output_path=crawl_output_path,
    )

    joined = " ".join(calls[0][1])
    assert "CLOSESPIDER_PAGECOUNT=60" in joined
    assert "-a frontier_limit=80" in joined
    assert calls[1] == ("extract", db_path, "kb-smoke-v1")
    assert calls[2] == ("export", db_path, output_path)
    assert summary == {"extracted_pages": 5, "exported_records": 11}


def test_validate_knowledge_base_jsonl_reports_record_coverage(tmp_path: Path):
    kb_path = tmp_path / "knowledge_base.jsonl"
    records = [
        {"record_type": "page_document", "id": "page:1"},
        {"record_type": "asset_document", "id": "asset:1"},
        {"record_type": "isaweb_dataset", "id": "isa:1"},
        {"record_type": "dataset_family", "id": "family:1", "sources": ["OeNB"]},
        {"record_type": "chatbot_chunk", "id": "chunk:1", "parent_record_type": "dataset_family"},
        {"record_type": "chatbot_chunk", "id": "chunk:2", "parent_record_type": "isaweb_dataset"},
    ]
    kb_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    summary = validate_knowledge_base_jsonl(kb_path)

    assert summary["total_records"] == 6
    assert summary["record_counts"]["dataset_family"] == 1
    assert summary["record_counts"]["chatbot_chunk"] == 2
    assert summary["dataset_families_with_sources"] == 1
    assert summary["chunk_parent_counts"]["dataset_family"] == 1
    assert summary["chunk_parent_counts"]["isaweb_dataset"] == 1
