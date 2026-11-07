"""The unified-catalog evaluation harness: passes, is deterministic, and detects deliberate breakage."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.recommender import load_songs

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_unified_catalog", ROOT / "evals" / "run_unified_catalog.py")
harness = importlib.util.module_from_spec(spec)
sys.modules["run_unified_catalog"] = harness
spec.loader.exec_module(harness)


@pytest.fixture(scope="module")
def report():
    return harness.run_all()


def test_all_scenarios_pass_with_no_allowed_failures(report):
    assert report["failed"] == 0 and report["scenarios_total"] == 15
    assert report["checks_passed"] == report["checks_total"] >= 60
    failed = [(s["name"], c["check"]) for s in report["scenarios"] for c in s["checks"] if not c["passed"]]
    assert failed == []


def test_report_is_deterministic_and_has_no_timestamps(report):
    again = harness.run_all()
    assert harness.format_report(report) == harness.format_report(again)
    assert json.dumps(report, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_saved_results_match_a_fresh_run(report):
    saved = (ROOT / "evals" / "results" / "unified_catalog.txt").read_text()
    assert saved == harness.format_report(report)


def test_no_check_is_a_constant_true(report):
    # a check with no detail and no variable input would be vacuous; every check must carry a real comparison
    source = (ROOT / "evals" / "run_unified_catalog.py").read_text()
    assert ", True, " not in source


def test_harness_detects_a_corrupted_catalog(monkeypatch):
    broken = [dict(s) for s in load_songs(str(ROOT / "data" / "songs.csv"))]
    broken[0]["genre"] = "not-a-genre"
    monkeypatch.setattr(harness, "load_songs", lambda path: broken)
    assert harness.run_all()["failed"] > 0


def test_harness_detects_a_missing_song(monkeypatch):
    shortened = load_songs(str(ROOT / "data" / "songs.csv"))[:-1]
    monkeypatch.setattr(harness, "load_songs", lambda path: shortened)
    assert harness.run_all()["failed"] > 0


def test_diagnostics_are_reported_but_not_counted(report):
    assert report["diagnostics_not_graded"] and "Diagnostics (not graded" in harness.format_report(report)
    assert report["checks_total"] == sum(len(s["checks"]) for s in report["scenarios"])
