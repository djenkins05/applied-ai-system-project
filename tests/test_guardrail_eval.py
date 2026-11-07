"""The saved guardrail demonstration must pass, and its checker must be able to fail."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_guardrails", ROOT / "evals" / "run_guardrails.py")
run_guardrails = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_guardrails)


def test_every_guardrail_case_passes():
    report = run_guardrails.run_all()
    assert report["total"] >= 40
    assert report["failed"] == 0, [c["id"] for c in report["cases"] if not c["passed"]]


def test_report_is_deterministic():
    first = run_guardrails.format_report(run_guardrails.run_all())
    second = run_guardrails.format_report(run_guardrails.run_all())
    assert first == second and "Summary:" in first


def test_checker_detects_a_wrong_expectation():
    songs = run_guardrails.load_songs(str(ROOT / "data" / "songs.csv"))
    result = run_guardrails.recommend_from_manual(
        run_guardrails.ManualPreferences(genres=["lofi"], energy=0.3), songs)
    assert run_guardrails.check({"ok": True, "source": "manual"}, result, None) == []
    assert run_guardrails.check({"ok": False}, result, None)
