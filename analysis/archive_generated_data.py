"""Archive superseded generated crawl artifacts and publish stable active aliases."""

from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_ACTIVE_ARTIFACTS = {
    "statistics_production/knowledge_base_active.jsonl": "statistics_production/knowledge_base_production_v5.jsonl",
    "statistics_production/crawl_items_active.json": "statistics_production/crawl_items_production_v3.json",
    "full_site_production/knowledge_base_active.jsonl": "full_site_production/knowledge_base_full_v3.jsonl",
    "full_site_production/crawl_items_active.json": "full_site_production/crawl_items_full_v1.json",
}

DEFAULT_KEEP_RELPATHS = {
    "statistics_production/pages.db",
    "statistics_production/knowledge_base_production_v5.jsonl",
    "statistics_production/crawl_items_production_v3.json",
    "statistics_production/knowledge_base_active.jsonl",
    "statistics_production/crawl_items_active.json",
    "full_site_production/pages.db",
    "full_site_production/knowledge_base_full_v3.jsonl",
    "full_site_production/crawl_items_full_v1.json",
    "full_site_production/knowledge_base_active.jsonl",
    "full_site_production/crawl_items_active.json",
    "smoke_live/pages.db",
}


def archive_legacy_analysis_files(
    analysis_dir: Path,
    *,
    keep_filenames: set[str],
    archive_relpath: str = "archive/legacy",
) -> list[str]:
    archive_dir = analysis_dir / archive_relpath
    moved: list[str] = []
    for path in sorted(analysis_dir.iterdir()):
        if path.name in {"archive", "__pycache__"}:
            continue
        if path.name in keep_filenames:
            continue
        if path.is_file() and path.suffix in {".py", ".ipynb", ".json"}:
            archive_dir.mkdir(parents=True, exist_ok=True)
            destination = archive_dir / path.name
            path.rename(destination)
            moved.append(path.name)
        elif path.is_dir() and path.name == "templates":
            archive_dir.mkdir(parents=True, exist_ok=True)
            destination = archive_dir / path.name
            path.rename(destination)
            moved.append(path.name)
    return moved


def publish_active_artifacts(
    data_dir: Path,
    *,
    active_artifacts: dict[str, str] = DEFAULT_ACTIVE_ARTIFACTS,
) -> list[str]:
    published: list[str] = []
    for target_relpath, source_relpath in active_artifacts.items():
        source_path = data_dir / source_relpath
        target_path = data_dir / target_relpath
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        published.append(target_relpath)
    return published


def archive_superseded_artifacts(
    data_dir: Path,
    *,
    keep_relpaths: set[str] = DEFAULT_KEEP_RELPATHS,
    archive_label: str,
) -> list[str]:
    archive_root = data_dir / "archive" / archive_label
    moved: list[str] = []
    for subdir_name in ("statistics_production", "full_site_production", "smoke_live"):
        subdir = data_dir / subdir_name
        if not subdir.exists():
            continue
        for path in sorted(subdir.iterdir()):
            if not path.is_file():
                continue
            relpath = path.relative_to(data_dir).as_posix()
            if relpath in keep_relpaths:
                continue
            destination = archive_root / relpath
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
            moved.append(relpath)
    return moved


if __name__ == "__main__":
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Archive older generated artifacts and publish stable active aliases")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Crawler data directory",
    )
    parser.add_argument(
        "--archive-label",
        default=date.today().isoformat(),
        help="Archive label under data/archive/",
    )
    args = parser.parse_args()

    publish_active_artifacts(args.data_dir)
    moved = archive_superseded_artifacts(args.data_dir, archive_label=args.archive_label)
    print(f"Published {len(DEFAULT_ACTIVE_ARTIFACTS)} active aliases")
    print(f"Archived {len(moved)} files to {args.data_dir / 'archive' / args.archive_label}")
