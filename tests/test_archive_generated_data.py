import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.archive_generated_data import (
    archive_legacy_analysis_files,
    archive_superseded_artifacts,
    publish_active_artifacts,
)


def test_publish_active_artifacts_creates_stable_active_aliases(tmp_path: Path):
    data_dir = tmp_path / "data"
    stats_dir = data_dir / "statistics_production"
    full_dir = data_dir / "full_site_production"
    stats_dir.mkdir(parents=True)
    full_dir.mkdir(parents=True)

    (stats_dir / "knowledge_base_production_v5.jsonl").write_text("stats-v5", encoding="utf-8")
    (stats_dir / "crawl_items_production_v3.json").write_text(json.dumps({"items": 1}), encoding="utf-8")
    (full_dir / "knowledge_base_full_v3.jsonl").write_text("full-v3", encoding="utf-8")
    (full_dir / "crawl_items_full_v1.json").write_text(json.dumps({"items": 2}), encoding="utf-8")

    publish_active_artifacts(
        data_dir,
        active_artifacts={
            "statistics_production/knowledge_base_active.jsonl": "statistics_production/knowledge_base_production_v5.jsonl",
            "statistics_production/crawl_items_active.json": "statistics_production/crawl_items_production_v3.json",
            "full_site_production/knowledge_base_active.jsonl": "full_site_production/knowledge_base_full_v3.jsonl",
            "full_site_production/crawl_items_active.json": "full_site_production/crawl_items_full_v1.json",
        },
    )

    assert (stats_dir / "knowledge_base_active.jsonl").read_text(encoding="utf-8") == "stats-v5"
    assert json.loads((stats_dir / "crawl_items_active.json").read_text(encoding="utf-8")) == {"items": 1}
    assert (full_dir / "knowledge_base_active.jsonl").read_text(encoding="utf-8") == "full-v3"
    assert json.loads((full_dir / "crawl_items_active.json").read_text(encoding="utf-8")) == {"items": 2}


def test_archive_superseded_artifacts_moves_old_generated_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    stats_dir = data_dir / "statistics_production"
    smoke_dir = data_dir / "smoke_live"
    archive_root = data_dir / "archive" / "2026-03-20"
    stats_dir.mkdir(parents=True)
    smoke_dir.mkdir(parents=True)

    (stats_dir / "knowledge_base_old.jsonl").write_text("old-kb", encoding="utf-8")
    (stats_dir / "knowledge_base_active.jsonl").write_text("active-kb", encoding="utf-8")
    (stats_dir / "pages.db").write_text("db", encoding="utf-8")
    (smoke_dir / "knowledge_base_report_fix.jsonl").write_text("smoke-old", encoding="utf-8")
    (smoke_dir / "pages.db").write_text("smoke-db", encoding="utf-8")

    moved = archive_superseded_artifacts(
        data_dir,
        keep_relpaths={
            "statistics_production/knowledge_base_active.jsonl",
            "statistics_production/pages.db",
            "smoke_live/pages.db",
        },
        archive_label="2026-03-20",
    )

    assert "statistics_production/knowledge_base_old.jsonl" in moved
    assert "smoke_live/knowledge_base_report_fix.jsonl" in moved
    assert not (stats_dir / "knowledge_base_old.jsonl").exists()
    assert not (smoke_dir / "knowledge_base_report_fix.jsonl").exists()
    assert (archive_root / "statistics_production" / "knowledge_base_old.jsonl").read_text(encoding="utf-8") == "old-kb"
    assert (archive_root / "smoke_live" / "knowledge_base_report_fix.jsonl").read_text(encoding="utf-8") == "smoke-old"
    assert (stats_dir / "knowledge_base_active.jsonl").read_text(encoding="utf-8") == "active-kb"
    assert (stats_dir / "pages.db").read_text(encoding="utf-8") == "db"


def test_archive_legacy_analysis_files_moves_unkept_python_files(tmp_path: Path):
    analysis_dir = tmp_path / "analysis"
    archive_dir = analysis_dir / "archive" / "legacy"
    analysis_dir.mkdir(parents=True)

    (analysis_dir / "refresh_knowledge_base.py").write_text("active", encoding="utf-8")
    (analysis_dir / "query_knowledge_base.py").write_text("active", encoding="utf-8")
    (analysis_dir / "dashboard.py").write_text("legacy-dashboard", encoding="utf-8")
    (analysis_dir / "deep_scan.py").write_text("legacy-deep-scan", encoding="utf-8")
    (analysis_dir / "cml_crawl_runden.py").write_text("keep-for-later", encoding="utf-8")

    moved = archive_legacy_analysis_files(
        analysis_dir,
        keep_filenames={
            "refresh_knowledge_base.py",
            "query_knowledge_base.py",
            "cml_crawl_runden.py",
        },
    )

    assert moved == ["dashboard.py", "deep_scan.py"]
    assert (analysis_dir / "refresh_knowledge_base.py").read_text(encoding="utf-8") == "active"
    assert (analysis_dir / "cml_crawl_runden.py").read_text(encoding="utf-8") == "keep-for-later"
    assert not (analysis_dir / "dashboard.py").exists()
    assert not (analysis_dir / "deep_scan.py").exists()
    assert (archive_dir / "dashboard.py").read_text(encoding="utf-8") == "legacy-dashboard"
    assert (archive_dir / "deep_scan.py").read_text(encoding="utf-8") == "legacy-deep-scan"


def test_archive_legacy_analysis_files_moves_notebooks_and_support_dirs(tmp_path: Path):
    analysis_dir = tmp_path / "analysis"
    archive_dir = analysis_dir / "archive" / "legacy"
    templates_dir = analysis_dir / "templates"
    analysis_dir.mkdir(parents=True)
    templates_dir.mkdir(parents=True)

    (analysis_dir / "chatbot_retrieval.py").write_text("active", encoding="utf-8")
    (analysis_dir / "rag_exploration.ipynb").write_text("legacy-rag", encoding="utf-8")
    (analysis_dir / "chart_synonyms.json").write_text('{"legacy": true}', encoding="utf-8")
    (templates_dir / "dashboard.html").write_text("legacy-template", encoding="utf-8")

    moved = archive_legacy_analysis_files(
        analysis_dir,
        keep_filenames={"chatbot_retrieval.py"},
    )

    assert "rag_exploration.ipynb" in moved
    assert "chart_synonyms.json" in moved
    assert "templates" in moved
    assert (archive_dir / "rag_exploration.ipynb").read_text(encoding="utf-8") == "legacy-rag"
    assert (archive_dir / "chart_synonyms.json").read_text(encoding="utf-8") == '{"legacy": true}'
    assert (archive_dir / "templates" / "dashboard.html").read_text(encoding="utf-8") == "legacy-template"
