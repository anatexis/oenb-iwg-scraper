"""Run an incremental crawl refresh and rebuild the JSONL knowledge base."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from analysis.export_knowledge_base_jsonl import export_knowledge_base_jsonl
from analysis.extract_text import run_extraction


def build_scrapy_command(
    *,
    db_path: Path,
    output_json_path: Path | None = None,
    use_frontier: bool = True,
    frontier_limit: int = 500,
    frontier_kinds: list[str] | None = None,
    isaweb_focus: bool = False,
    section: str | None = None,
    page_limit: int | None = None,
) -> list[str]:
    """Build the Scrapy command for a refresh crawl."""

    db_path = db_path.resolve()
    output_json_path = output_json_path.resolve() if output_json_path is not None else None

    command = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        "oenb",
        "-s",
        'ITEM_PIPELINES={"oenb_scraper.pipelines.DeduplicationPipeline": 100, "oenb_scraper.pipelines.FileSizePipeline": 200, "oenb_scraper.pipelines.SQLitePipeline": 400}',
        "-s",
        f"SQLITE_DB_PATH={db_path}",
    ]
    if output_json_path is not None:
        command.extend(["-O", str(output_json_path)])
    if section:
        command.extend(["-a", f"section={section}"])
    if page_limit is not None:
        command.extend(["-s", f"CLOSESPIDER_PAGECOUNT={page_limit}"])
    if use_frontier:
        command.extend(
            [
                "-a",
                "use_frontier=true",
                "-a",
                f"frontier_db_path={db_path}",
                "-a",
                f"frontier_limit={frontier_limit}",
            ]
        )
        if frontier_kinds:
            command.extend(["-a", f"frontier_kinds={','.join(frontier_kinds)}"])
    if isaweb_focus:
        command.extend(["-a", "isaweb_focus=true"])
    return command


def refresh_knowledge_base(
    *,
    db_path: Path,
    output_path: Path,
    crawl_output_path: Path | None = None,
    use_frontier: bool = True,
    frontier_limit: int = 500,
    frontier_kinds: list[str] | None = None,
    isaweb_focus: bool = False,
    section: str | None = None,
    extractor_version: str = "kb-refresh-v1",
    page_limit: int | None = None,
) -> dict[str, int]:
    """Run crawl, HTML text extraction and JSONL knowledge-base export."""

    db_path = db_path.resolve()
    output_path = output_path.resolve()
    crawl_output_path = crawl_output_path.resolve() if crawl_output_path is not None else None

    command = build_scrapy_command(
        db_path=db_path,
        output_json_path=crawl_output_path,
        use_frontier=use_frontier,
        frontier_limit=frontier_limit,
        frontier_kinds=frontier_kinds,
        isaweb_focus=isaweb_focus,
        section=section,
        page_limit=page_limit,
    )
    scraper_dir = Path(__file__).resolve().parent.parent / "scraper"
    subprocess.run(command, check=True, cwd=scraper_dir)

    extracted_pages = run_extraction(db_path, extractor_version)
    exported_records = export_knowledge_base_jsonl(db_path, output_path)
    return {
        "extracted_pages": extracted_pages,
        "exported_records": exported_records,
    }


def smoke_refresh_knowledge_base(
    *,
    db_path: Path,
    output_path: Path,
    crawl_output_path: Path | None = None,
    section: str | None = None,
    frontier_limit: int = 80,
    frontier_kinds: list[str] | None = None,
    isaweb_focus: bool = False,
    page_limit: int = 60,
    extractor_version: str = "kb-smoke-v1",
) -> dict[str, int]:
    """Run a bounded smoke crawl for quick live validation."""

    return refresh_knowledge_base(
        db_path=db_path,
        output_path=output_path,
        crawl_output_path=crawl_output_path,
        use_frontier=True,
        frontier_limit=frontier_limit,
        frontier_kinds=frontier_kinds,
        isaweb_focus=isaweb_focus,
        section=section,
        extractor_version=extractor_version,
        page_limit=page_limit,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh the crawler knowledge base incrementally")
    parser.add_argument("db_path", type=Path, help="Path to the SQLite crawl database")
    parser.add_argument("output_path", type=Path, help="Output JSONL knowledge-base path")
    parser.add_argument("--crawl-output", type=Path, default=None, help="Optional Scrapy item export JSON path")
    parser.add_argument("--section", default=None, help="Optional section filter")
    parser.add_argument("--full-crawl", action="store_true", help="Disable frontier-based incremental crawling")
    parser.add_argument("--frontier-limit", type=int, default=500, help="Maximum due frontier URLs to seed")
    parser.add_argument(
        "--frontier-kinds",
        default=None,
        help="Optional comma-separated frontier resource kinds to seed, e.g. isaweb_entry,isaweb_dataset",
    )
    parser.add_argument("--isaweb-focus", action="store_true", help="Restrict link following to ISAweb/service targets")
    parser.add_argument("--extractor-version", default="kb-refresh-v1", help="Version tag for HTML text extraction")
    parser.add_argument("--page-limit", type=int, default=None, help="Optional hard page cap via CLOSESPIDER_PAGECOUNT")
    parser.add_argument("--smoke", action="store_true", help="Run a bounded smoke crawl profile")
    args = parser.parse_args()

    if args.smoke:
        summary = smoke_refresh_knowledge_base(
            db_path=args.db_path,
            output_path=args.output_path,
            crawl_output_path=args.crawl_output,
            section=args.section,
            frontier_limit=args.frontier_limit if args.frontier_limit != 500 else 80,
            frontier_kinds=[entry.strip() for entry in args.frontier_kinds.split(",") if entry.strip()] if args.frontier_kinds else None,
            isaweb_focus=args.isaweb_focus,
            page_limit=args.page_limit if args.page_limit is not None else 60,
            extractor_version=args.extractor_version if args.extractor_version != "kb-refresh-v1" else "kb-smoke-v1",
        )
    else:
        summary = refresh_knowledge_base(
            db_path=args.db_path,
            output_path=args.output_path,
            crawl_output_path=args.crawl_output,
            use_frontier=not args.full_crawl,
            frontier_limit=args.frontier_limit,
            frontier_kinds=[entry.strip() for entry in args.frontier_kinds.split(",") if entry.strip()] if args.frontier_kinds else None,
            isaweb_focus=args.isaweb_focus,
            section=args.section,
            extractor_version=args.extractor_version,
            page_limit=args.page_limit,
        )
    print(
        f"Refresh complete: extracted_pages={summary['extracted_pages']} "
        f"exported_records={summary['exported_records']}"
    )
