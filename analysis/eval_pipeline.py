"""End-to-end eval pipeline: extraction -> KB exports -> indexes -> eval -> score.

Designed to run as a Cloudera CML job (thin wrapper in cml_eval.py) and
locally. Steps run in order; the first failure aborts the pipeline and the
job exits non-zero. Every artifact lands in the standard data/ layout that
the chatbot runtime already expects.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
import traceback
from pathlib import Path


def _step_extract_text(ctx: dict) -> str:
    from analysis.extract_text import run_extraction

    db_path = ctx["full_site_db"]
    if not db_path.exists():
        raise FileNotFoundError(f"full-site DB fehlt: {db_path} (erst Crawl-Job laufen lassen)")
    count = run_extraction(db_path)
    return f"{count} Seiten extrahiert"


def _step_export_full_site_kb(ctx: dict) -> str:
    from analysis.export_knowledge_base_jsonl import export_knowledge_base_jsonl

    count = export_knowledge_base_jsonl(ctx["full_site_db"], ctx["full_site_kb"])
    ctx["artifacts"]["full_site_kb"] = str(ctx["full_site_kb"])
    return f"{count} Records"


def _step_export_statistics_kb(ctx: dict) -> str:
    from analysis.export_knowledge_base_jsonl import export_knowledge_base_jsonl

    db_path = ctx["statistics_db"]
    if not db_path.exists():
        return "übersprungen: keine Statistik-DB (ISAweb-Job noch nicht gelaufen)"
    count = export_knowledge_base_jsonl(db_path, ctx["statistics_kb"])
    ctx["artifacts"]["statistics_kb"] = str(ctx["statistics_kb"])
    return f"{count} Records"


def _step_build_indexes(ctx: dict) -> str:
    from analysis.kb_index import build_kb_index

    built = []
    for kb in (ctx["statistics_kb"], ctx["full_site_kb"]):
        if kb.exists():
            build_kb_index(kb)
            built.append(kb.name)
    if not built:
        raise FileNotFoundError("keine KB zum Indizieren gefunden")
    return f"Indexe: {', '.join(built)}"


def _step_run_eval(ctx: dict) -> str:
    from analysis.run_chatbot_eval import run_chatbot_eval_fixture

    reports_dir = ctx["base_dir"] / "data" / "eval_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    previous = sorted(reports_dir.glob("eval_*.json"))
    ctx["baseline_report"] = previous[-1] if previous else None

    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    report_path = reports_dir / f"eval_{stamp}.json"
    report = run_chatbot_eval_fixture(
        fixture_path=ctx["fixture_path"],
        output_path=report_path,
        base_dir=ctx["base_dir"],
        debug=True,
    )
    ctx["artifacts"]["report_path"] = str(report_path)
    ctx["report"] = report
    counts = report["summary"].get("verdict_counts", {})
    return f"{report['summary']['total_cases']} Cases, Verdikte: {counts}"


def _step_score_eval(ctx: dict) -> str:
    from analysis.score_chatbot_eval import diff_scored_reports, score_report

    fixture_cases = json.loads(ctx["fixture_path"].read_text(encoding="utf-8"))
    scored = score_report(ctx["report"], fixture_cases=fixture_cases)
    ctx["artifacts"]["score"] = scored["summary"]["score"]
    ctx["artifacts"]["verdict_counts"] = scored["summary"]["verdict_counts"]
    ctx["artifacts"]["by_type"] = scored["summary"]["by_type"]

    detail = f"Score {scored['summary']['score']:.3f} {scored['summary']['verdict_counts']}"
    baseline = ctx.get("baseline_report")
    if baseline:
        baseline_report = json.loads(Path(baseline).read_text(encoding="utf-8"))
        baseline_scored = score_report(baseline_report, fixture_cases=fixture_cases)
        diff = diff_scored_reports(baseline=baseline_scored["cases"], current=scored["cases"])
        ctx["artifacts"]["baseline"] = str(baseline)
        ctx["artifacts"]["improved"] = diff["improved"]
        ctx["artifacts"]["regressed"] = diff["regressed"]
        detail += (
            f" | Baseline {baseline_scored['summary']['score']:.3f}"
            f" (+{len(diff['improved'])}/-{len(diff['regressed'])})"
        )
    return detail


_DEFAULT_STEPS = [
    ("extract_text", _step_extract_text),
    ("export_full_site_kb", _step_export_full_site_kb),
    ("export_statistics_kb", _step_export_statistics_kb),
    ("build_indexes", _step_build_indexes),
    ("run_eval", _step_run_eval),
    ("score_eval", _step_score_eval),
]

DEFAULT_STEP_NAMES = [name for name, _ in _DEFAULT_STEPS]


def run_eval_pipeline(
    *,
    base_dir: Path,
    steps: list | None = None,
    fixture_path: Path | None = None,
) -> dict:
    data_dir = base_dir / "data"
    ctx = {
        "base_dir": base_dir,
        "fixture_path": fixture_path or base_dir / "tests" / "fixtures" / "chatbot_eval_v2.json",
        "full_site_db": data_dir / "full_site_production" / "pages.db",
        "full_site_kb": data_dir / "full_site_production" / "knowledge_base_active.jsonl",
        "statistics_db": data_dir / "statistics_production" / "pages.db",
        "statistics_kb": data_dir / "statistics_production" / "knowledge_base_active.jsonl",
        "artifacts": {},
    }

    results = []
    failed = False
    for name, step in steps if steps is not None else _DEFAULT_STEPS:
        if failed:
            results.append({"name": name, "status": "skipped", "detail": "", "duration_s": 0.0})
            continue
        start = time.perf_counter()
        try:
            detail = step(ctx)
            results.append(
                {
                    "name": name,
                    "status": "ok",
                    "detail": str(detail or ""),
                    "duration_s": round(time.perf_counter() - start, 1),
                }
            )
        except Exception:
            results.append(
                {
                    "name": name,
                    "status": "failed",
                    "detail": traceback.format_exc(limit=3),
                    "duration_s": round(time.perf_counter() - start, 1),
                }
            )
            failed = True

    return {
        "status": "failed" if failed else "ok",
        "steps": results,
        "artifacts": ctx["artifacts"],
    }
