"""Tests for the evaluation harness (evals/run_eval.py), including deliberate-breakage self-tests.

Basis of each test (see the module docstring in run_eval.py):
  * structure/determinism/freshness tests check the harness itself;
  * mutation tests break the system on purpose and require the harness to notice (the checks have teeth).
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_eval", ROOT / "evals" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)

@pytest.fixture(scope="module")
def report():
    return run_eval.build_report(check_determinism=True)


def failed(rep):
    return set(rep["failed_scenarios"])


# --- Structure, determinism, freshness ---------------------------------------------------------------

def test_every_category_is_present_with_a_minimum_number_of_scenarios(report):
    minimums = {"A": 6, "B": 6, "C": 13, "D": 6, "E": 20, "F": 14, "G": 10, "H": 10, "I": 20, "K": 1}
    for letter, minimum in minimums.items():
        assert report["categories"][letter]["scenarios"] >= minimum, letter


def test_scenario_and_check_counts_are_reported_separately_and_add_up(report):
    graded = [s for s in report["scenarios"] if not s["informational"]]
    assert report["new_scenarios"]["total"] == len(graded)
    assert report["new_checks"]["total"] == sum(len(s["checks"]) for s in graded)
    assert report["new_checks"]["total"] > report["new_scenarios"]["total"]
    assert sum(v["checks"] for v in report["new_checks"]["by_basis"].values()) == report["new_checks"]["total"]
    assert report["new_scenarios"]["informational_not_graded"] == 7      # 6 grounding probes + 1 documented finding


def test_guardrail_cases_are_reused_not_double_counted(report):
    reused = report["reused_guardrail_suite"]
    assert reused["scenarios"] == 43 and reused["failed"] == 0
    new_ids = {s["id"] for s in report["scenarios"]}
    guardrail_ids = {c["id"] for c in json.loads((ROOT / "evals" / "guardrail_cases.json").read_text())["cases"]}
    assert not new_ids & guardrail_ids              # no scenario id appears in both suites


def test_every_graded_scenario_passes_and_no_failure_is_expected(report):
    """There is no allow-list of expected failures: any failing scenario fails this test and the harness exit code."""
    assert failed(report) == set()
    assert report["overall_pass"] is True
    assert report["new_scenarios"]["failed"] == 0 and report["new_checks"]["failed"] == 0


def test_the_original_top3_expectation_is_kept_as_a_documented_finding(report):
    finding = next(f for f in report["findings"] if f["id"] == "H1-finding-top3-not-guaranteed")
    assert "top 3" in finding["original_expectation"]
    assert finding["status"] == "NOT MET"                      # preserved, not hidden and not turned into a pass
    observed = finding["observed"]
    assert (observed["rank_before"], observed["rank_after"]) == (5, 4)
    assert (observed["score_before"], observed["score_after"]) == (1.78, 3.85)
    assert len(finding["songs_already_matching_both_chosen_genre_and_mood"]) == 4
    assert "does not guarantee" in finding["explanation"]
    scenario = next(s for s in report["scenarios"] if s["id"] == "H1-finding-top3-not-guaranteed")
    assert scenario["informational"] is True and scenario["passed"] is None     # documented, not graded
    assert "FINDING" in run_eval.format_report(report) and "expectation NOT MET" in run_eval.format_report(report)


def test_h1_checks_the_intended_behavior_not_a_hard_coded_rank(report):
    h1 = next(s for s in report["scenarios"] if s["id"] == "H1-like-new-genre")
    names = {c["name"] for c in h1["checks"]}
    assert {"liked_song_score_increases", "liked_song_rank_improves", "result_is_deterministic",
            "ranking_equals_engine_on_adjusted_preferences"} <= names
    assert "liked_song_reaches_top_3" not in names and h1["passed"] is True


def test_the_suite_is_deterministic(report):
    assert report["deterministic_on_rerun"] is True
    assert run_eval.format_report(report) == run_eval.format_report(run_eval.build_report(check_determinism=True))


def test_saved_reports_match_a_fresh_run(report):
    saved = json.loads((ROOT / "evals" / "results" / "eval_report.json").read_text(encoding="utf-8"))
    assert saved == json.loads(json.dumps(report))
    assert (ROOT / "evals" / "results" / "eval_report.txt").read_text(encoding="utf-8") == run_eval.format_report(report)


def test_existing_guardrail_results_are_untouched():
    text = (ROOT / "evals" / "results" / "guardrails.txt").read_text(encoding="utf-8")
    assert "Summary: 43/43 passed, 0 failed" in text


def test_grounding_table_separates_documented_coverage_from_the_rest(report):
    table = report["grounding"]
    d = table["documented_coverage"]
    assert d["FN"] == 0 and d["FP"] == 0 and d["TP"] >= 19 and d["TN"] >= 6
    outside = table["outside_documented_coverage"]
    assert outside["TP"] + outside["FN"] == 6 and outside["FN"] >= 1    # the limits are reported, not hidden


def test_harness_makes_no_network_calls(report):
    assert report["scenarios"]            # conftest blocks sockets: reaching here means none were opened


# --- Deliberate breakage: the harness must notice -----------------------------------------------------------

def run_broken():
    return run_eval.build_report(check_determinism=False)


def extra_failures(rep):
    return failed(rep)


def test_reversed_engine_ordering_is_detected(monkeypatch):
    import src.pipeline as pipeline
    real = pipeline.recommend_songs

    def reversed_engine(user_prefs, songs, k=5, strategy="balanced"):
        return list(reversed(real(user_prefs, songs, len(songs), strategy)))[:k]
    monkeypatch.setattr(pipeline, "recommend_songs", reversed_engine)
    rep = run_broken()
    assert not rep["overall_pass"]
    assert {"A1-jazz-coffee-shop", "B1-study", "G1-fallback-503"} <= extra_failures(rep)


def test_inflated_scores_are_detected_by_invariants(monkeypatch):
    import src.pipeline as pipeline
    real = pipeline.recommend_songs
    monkeypatch.setattr(pipeline, "recommend_songs", lambda *a, **k: [(s, sc * 2, e) for s, sc, e in real(*a, **k)])
    rep = run_broken()
    broken = [c["name"] for s in rep["scenarios"] for c in s["checks"] if c["basis"] == "invariant" and not c["passed"]]
    assert "scores_within_0_and_4" in broken and "engine_reasons_present_and_add_up_to_score" in broken


def test_validator_that_accepts_everything_is_detected(monkeypatch):
    import src.explain as explain
    monkeypatch.setattr(explain, "check_explanation", lambda *a, **k: None)
    rep = run_broken()
    assert {"I-u1", "I-u3", "I-u5", "IP1-mixed-explanations"} <= extra_failures(rep)
    assert rep["grounding"]["documented_coverage"]["FN"] > 0


def test_leaking_diagnostics_are_detected(monkeypatch):
    import src.llm as llm
    monkeypatch.setattr(llm, "sanitize_detail", lambda text: text if isinstance(text, str) else None)
    rep = run_broken()
    assert {"F12-leaky-400"} <= extra_failures(rep)


def test_a_changed_retry_policy_is_detected(monkeypatch):
    import src.llm as llm
    real = llm.classify_error

    def retry_everything(error):
        mapped = real(error)
        if isinstance(mapped, (llm.LLMBadRequestError, llm.LLMModelNotFoundError, llm.LLMAuthError)):
            return llm.LLMUnavailableError("changed", status_code=mapped.status_code)
        return mapped
    monkeypatch.setattr(llm, "classify_error", retry_everything)
    rep = run_broken()
    assert {"F5-400", "F6-401", "F8-404"} <= extra_failures(rep)


def test_feedback_that_ignores_votes_is_detected(monkeypatch):
    import src.feedback as feedback
    monkeypatch.setattr(feedback, "adjust_preferences",
                        lambda base, log, songs: feedback.AdjustedPreferences(prefs=base, notes=[]))
    rep = run_broken()
    assert {"H1-like-new-genre", "H4-energy-direction", "H5-label-weights"} <= extra_failures(rep)


def test_dislikes_that_do_not_exclude_are_detected(monkeypatch):
    import src.feedback as feedback
    monkeypatch.setattr(feedback.FeedbackLog, "disliked_ids", property(lambda self: []))
    rep = run_broken()
    assert {"H2-dislike-top-pick", "H7-shortfall-message"} <= extra_failures(rep)


def test_a_disabled_injection_guardrail_is_detected(monkeypatch):
    import src.guardrails as guardrails
    monkeypatch.setattr(guardrails, "detect_injection", lambda text: None)
    rep = run_broken()
    assert "D4-injection-rejected-and-not-logged" in extra_failures(rep)
    assert rep["reused_guardrail_suite"]["failed"] > 0 and not rep["overall_pass"]
