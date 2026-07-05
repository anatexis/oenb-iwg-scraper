"""Tests for the deterministic eval scorer."""

from analysis.score_chatbot_eval import diff_scored_reports, score_case, score_report


def _case(expect, answer_type="multi_part", answer="", citations=None):
    return {
        "id": "case_001",
        "type": "NAV",
        "query": "irrelevant",
        "expect": expect,
        "result": {
            "answer_type": answer_type,
            "answer": answer,
            "citations": citations or [],
        },
    }


class TestRejectCases:
    def test_reject_case_passes_when_not_found(self):
        case = _case({"reject": True}, answer_type="not_found", answer=None)
        assert score_case(case)["verdict"] == "pass"

    def test_reject_case_fails_when_answered(self):
        case = _case({"reject": True}, answer="Die Zimmerpflanze ...")
        assert score_case(case)["verdict"] == "fail"


class TestAnswerCases:
    def test_not_found_fails_for_non_reject_case(self):
        case = _case({"url_patterns": ["/Statistik/"]}, answer_type="not_found")
        assert score_case(case)["verdict"] == "fail"

    def test_pass_when_url_and_keywords_match(self):
        # Keywords are stems: "Zins" matches "Zinssätze" via umlaut folding
        case = _case(
            {"url_patterns": ["/Statistik/"], "keywords_any": ["Zins"]},
            answer="Aktuelle Zinssätze finden Sie hier.",
            citations=[{"url": "https://www.oenb.at/Statistik/zinsen.html"}],
        )
        assert score_case(case)["verdict"] == "pass"

    def test_keyword_matches_across_umlaut_spelling(self):
        # Fixture is ASCII ("Aussenwirtschaft"), answers use real umlauts
        case = _case(
            {"keywords_any": ["Aussenwirtschaft"]},
            answer="Die Außenwirtschaftsstatistik der OeNB.",
        )
        assert score_case(case)["verdict"] == "pass"

    def test_partial_when_only_url_matches(self):
        case = _case(
            {"url_patterns": ["/Statistik/"], "keywords_any": ["Inflation"]},
            answer="Hier gibt es Daten.",
            citations=[{"url": "https://www.oenb.at/Statistik/zinsen.html"}],
        )
        assert score_case(case)["verdict"] == "partial"

    def test_fail_when_nothing_matches(self):
        case = _case(
            {"url_patterns": ["/Statistik/"], "keywords_any": ["Inflation"]},
            answer="Versicherungsstatistik Aktiva.",
            citations=[{"url": "https://www.oenb.at/isawebstat/report"}],
        )
        assert score_case(case)["verdict"] == "fail"

    def test_single_dimension_pass_or_fail_no_partial(self):
        hit = _case(
            {"url_patterns": ["/Statistik/"]},
            citations=[{"url": "https://www.oenb.at/Statistik/"}],
        )
        miss = _case(
            {"url_patterns": ["/Statistik/"]},
            citations=[{"url": "https://www.oenb.at/Termine/"}],
        )
        assert score_case(hit)["verdict"] == "pass"
        assert score_case(miss)["verdict"] == "fail"

    def test_unscored_without_expect_block(self):
        case = _case(None)
        del case["expect"]
        assert score_case(case)["verdict"] == "unscored"


def _report(cases):
    return {"summary": {}, "cases": cases}


class TestScoreReport:
    def test_aggregates_verdicts_by_case_type(self):
        cases = [
            _case({"reject": True}, answer_type="not_found"),
            _case({"url_patterns": ["/Statistik/"]}, answer_type="not_found"),
        ]
        cases[0]["id"], cases[0]["type"] = "ood_001", "OOD"
        cases[1]["id"], cases[1]["type"] = "nav_001", "NAV"
        scored = score_report(_report(cases))
        assert scored["summary"]["verdict_counts"] == {"pass": 1, "fail": 1}
        assert scored["summary"]["by_type"]["OOD"] == {"pass": 1}
        assert scored["summary"]["by_type"]["NAV"] == {"fail": 1}
        assert scored["summary"]["score"] == 0.5

    def test_partial_counts_half_in_score(self):
        case = _case(
            {"url_patterns": ["/Statistik/"], "keywords_any": ["Inflation"]},
            answer="Hier gibt es Daten.",
            citations=[{"url": "https://www.oenb.at/Statistik/x.html"}],
        )
        scored = score_report(_report([case]))
        assert scored["summary"]["score"] == 0.5

    def test_joins_expect_from_fixture_for_old_reports(self):
        case = _case(None, answer_type="not_found")
        del case["expect"]
        fixture = [{"id": "case_001", "expect": {"reject": True}}]
        scored = score_report(_report([case]), fixture_cases=fixture)
        assert scored["cases"][0]["verdict"] == "pass"


class TestDiffScoredReports:
    def test_reports_flipped_cases_both_directions(self):
        old = [
            {"id": "a", "type": "NAV", "verdict": "fail"},
            {"id": "b", "type": "FACT", "verdict": "pass"},
            {"id": "c", "type": "OOD", "verdict": "pass"},
        ]
        new = [
            {"id": "a", "type": "NAV", "verdict": "pass"},
            {"id": "b", "type": "FACT", "verdict": "fail"},
            {"id": "c", "type": "OOD", "verdict": "pass"},
        ]
        diff = diff_scored_reports(baseline=old, current=new)
        assert {d["id"]: d for d in diff["improved"]}.keys() == {"a"}
        assert {d["id"]: d for d in diff["regressed"]}.keys() == {"b"}


class TestCli:
    def test_cli_scores_report_and_diffs_baseline(self, tmp_path, capsys):
        from analysis.score_chatbot_eval import main

        fixture = [{"id": "a", "type": "NAV", "expect": {"url_patterns": ["/Statistik/"]}}]
        base_case = {
            "id": "a", "type": "NAV",
            "result": {"answer_type": "not_found", "answer": None, "citations": []},
        }
        new_case = {
            "id": "a", "type": "NAV",
            "result": {
                "answer_type": "page_document", "answer": "Statistik-Seite",
                "citations": [{"url": "https://www.oenb.at/Statistik/"}],
            },
        }
        fixture_path = tmp_path / "fixture.json"
        base_path = tmp_path / "base.json"
        report_path = tmp_path / "report.json"
        import json
        fixture_path.write_text(json.dumps(fixture))
        base_path.write_text(json.dumps({"cases": [base_case]}))
        report_path.write_text(json.dumps({"cases": [new_case]}))

        main([str(report_path), "--fixture", str(fixture_path), "--baseline", str(base_path)])
        out = capsys.readouterr().out
        assert '"pass": 1' in out
        assert "improved" in out and '"from": "fail"' in out


class TestFixtureExpectations:
    def test_every_v2_case_has_expect_block(self):
        import json
        from pathlib import Path

        cases = json.loads(
            Path("tests/fixtures/chatbot_eval_v2.json").read_text(encoding="utf-8")
        )
        missing = [c["id"] for c in cases if not c.get("expect")]
        assert missing == []

    def test_reject_flag_matches_ood_type(self):
        import json
        from pathlib import Path

        cases = json.loads(
            Path("tests/fixtures/chatbot_eval_v2.json").read_text(encoding="utf-8")
        )
        for case in cases:
            is_ood = case["type"] == "OOD"
            assert bool(case.get("expect", {}).get("reject")) == is_ood, case["id"]
