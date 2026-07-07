"""Tests for the CML eval pipeline orchestration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.eval_pipeline import DEFAULT_STEP_NAMES, run_eval_pipeline


def test_runs_steps_in_order_and_reports_ok(tmp_path):
    calls = []
    steps = [
        ("alpha", lambda ctx: calls.append("alpha") or "a-detail"),
        ("beta", lambda ctx: calls.append("beta") or "b-detail"),
    ]
    result = run_eval_pipeline(base_dir=tmp_path, steps=steps)
    assert calls == ["alpha", "beta"]
    assert result["status"] == "ok"
    assert [s["name"] for s in result["steps"]] == ["alpha", "beta"]
    assert all(s["status"] == "ok" for s in result["steps"])


def test_aborts_on_failure_and_marks_remaining_skipped(tmp_path):
    calls = []

    def boom(ctx):
        raise RuntimeError("export kaputt")

    steps = [
        ("alpha", lambda ctx: calls.append("alpha")),
        ("boom", boom),
        ("gamma", lambda ctx: calls.append("gamma")),
    ]
    result = run_eval_pipeline(base_dir=tmp_path, steps=steps)
    assert calls == ["alpha"]
    assert result["status"] == "failed"
    by_name = {s["name"]: s for s in result["steps"]}
    assert by_name["boom"]["status"] == "failed"
    assert "export kaputt" in by_name["boom"]["detail"]
    assert by_name["gamma"]["status"] == "skipped"


def test_default_steps_cover_full_pipeline():
    assert DEFAULT_STEP_NAMES == [
        "extract_text",
        "export_full_site_kb",
        "export_statistics_kb",
        "build_indexes",
        "run_eval",
        "score_eval",
    ]


def test_context_carries_paths_and_collects_artifacts(tmp_path):
    seen = {}

    def step(ctx):
        seen["base_dir"] = ctx["base_dir"]
        ctx["artifacts"]["report_path"] = "x.json"

    result = run_eval_pipeline(base_dir=tmp_path, steps=[("s", step)])
    assert seen["base_dir"] == tmp_path
    assert result["artifacts"]["report_path"] == "x.json"
