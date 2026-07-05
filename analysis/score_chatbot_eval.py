"""Deterministic post-hoc scorer for chatbot eval reports."""

from __future__ import annotations

from collections import Counter, defaultdict

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_SCORE_WEIGHTS = {"pass": 1.0, "partial": 0.5}


def _normalize(text: str) -> str:
    return text.lower().translate(_UMLAUT_MAP)


def _url_dimension(expect: dict, citations: list[dict]) -> bool | None:
    patterns = expect.get("url_patterns") or []
    if not patterns:
        return None
    urls = [_normalize(str(c.get("url") or "")) for c in citations]
    return any(_normalize(p) in url for p in patterns for url in urls)


def _keyword_dimension(expect: dict, answer: str) -> bool | None:
    keywords_any = expect.get("keywords_any") or []
    keywords_all = expect.get("keywords_all") or []
    if not keywords_any and not keywords_all:
        return None
    text = _normalize(answer)
    matched = True
    if keywords_any:
        matched = any(_normalize(k) in text for k in keywords_any)
    if matched and keywords_all:
        matched = all(_normalize(k) in text for k in keywords_all)
    return matched


def score_case(case: dict) -> dict:
    expect = case.get("expect")
    result = case.get("result") or {}
    answer_type = result.get("answer_type")
    scored = {"id": case.get("id"), "type": case.get("type")}

    if not expect:
        return {**scored, "verdict": "unscored", "reasons": ["no expect block"]}

    if expect.get("reject"):
        if answer_type == "not_found":
            return {**scored, "verdict": "pass", "reasons": []}
        return {**scored, "verdict": "fail", "reasons": ["expected rejection, got answer"]}

    if answer_type == "not_found":
        return {**scored, "verdict": "fail", "reasons": ["not_found"]}

    dimensions = {
        "url": _url_dimension(expect, result.get("citations") or []),
        "keywords": _keyword_dimension(expect, str(result.get("answer") or "")),
    }
    checked = {name: ok for name, ok in dimensions.items() if ok is not None}
    reasons = [f"{name} missed" for name, ok in checked.items() if not ok]

    if not checked:
        return {**scored, "verdict": "unscored", "reasons": ["expect block has no checks"]}
    if all(checked.values()):
        return {**scored, "verdict": "pass", "reasons": []}
    if any(checked.values()):
        return {**scored, "verdict": "partial", "reasons": reasons}
    return {**scored, "verdict": "fail", "reasons": reasons}


def score_report(report: dict, *, fixture_cases: list[dict] | None = None) -> dict:
    expect_by_id = {c.get("id"): c.get("expect") for c in fixture_cases or [] if c.get("expect")}
    scored_cases = []
    verdict_counts: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)

    for case in report.get("cases") or []:
        if not case.get("expect") and case.get("id") in expect_by_id:
            case = {**case, "expect": expect_by_id[case["id"]]}
        scored = score_case(case)
        scored_cases.append(scored)
        verdict_counts[scored["verdict"]] += 1
        by_type[str(scored.get("type"))][scored["verdict"]] += 1

    total = len(scored_cases)
    score = (
        sum(_SCORE_WEIGHTS.get(v, 0.0) * n for v, n in verdict_counts.items()) / total
        if total
        else 0.0
    )
    return {
        "summary": {
            "total_cases": total,
            "verdict_counts": dict(verdict_counts),
            "by_type": {t: dict(c) for t, c in by_type.items()},
            "score": score,
        },
        "cases": scored_cases,
    }


def diff_scored_reports(*, baseline: list[dict], current: list[dict]) -> dict:
    baseline_by_id = {c["id"]: c for c in baseline}
    improved, regressed = [], []
    rank = {"fail": 0, "unscored": 0, "partial": 1, "pass": 2}

    for case in current:
        old = baseline_by_id.get(case["id"])
        if old is None or old["verdict"] == case["verdict"]:
            continue
        entry = {
            "id": case["id"],
            "type": case.get("type"),
            "from": old["verdict"],
            "to": case["verdict"],
        }
        if rank[case["verdict"]] > rank[old["verdict"]]:
            improved.append(entry)
        else:
            regressed.append(entry)
    return {"improved": improved, "regressed": regressed}


def build_arg_parser():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Score a chatbot eval report deterministically")
    parser.add_argument("report", type=Path, help="Eval report JSON to score")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/chatbot_eval_v2.json"),
        help="Fixture with expect blocks (joined by case id for old reports)",
    )
    parser.add_argument(
        "--baseline", type=Path, default=None, help="Older report to diff verdicts against"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    import json

    args = build_arg_parser().parse_args(argv)
    fixture_cases = json.loads(args.fixture.read_text(encoding="utf-8")) if args.fixture.exists() else []
    report = json.loads(args.report.read_text(encoding="utf-8"))
    scored = score_report(report, fixture_cases=fixture_cases)

    output: dict = {"summary": scored["summary"]}
    if args.baseline:
        baseline_report = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline_scored = score_report(baseline_report, fixture_cases=fixture_cases)
        output["baseline_summary"] = baseline_scored["summary"]
        output["diff"] = diff_scored_reports(
            baseline=baseline_scored["cases"], current=scored["cases"]
        )
    output["failures"] = [c for c in scored["cases"] if c["verdict"] in ("fail", "partial")]
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
