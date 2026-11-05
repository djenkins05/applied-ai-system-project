from pathlib import Path

import pytest

from fakes import FakeAPIError, FakeClient, ReadTimeout, explanations_json, prefs_json
from src.llm import GeminiClient
from src.mock_llm import MockGemini
from src.moodmix_cli import main as cli_main
from src.moodmix_cli import render
from src.pipeline import recommend_from_text
from src.preferences import catalog_vocabulary, parse_preferences, to_user_prefs
from src.recommender import STRATEGIES, load_songs, recommend_songs

CATALOG = Path(__file__).resolve().parent.parent / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(CATALOG))


def client(fake):
    return GeminiClient(client=fake, sleep=lambda _s: None)


def good_explanations(songs, text="A gentle pick for focus."):
    # ids of the engine's top 5 for prefs_json(), computed independently of the pipeline
    prefs = parse_preferences(prefs_json(), catalog_vocabulary(songs))
    ids = [s["id"] for s, _, _ in recommend_songs(to_user_prefs(prefs), songs, 5)]
    return explanations_json([(i, text) for i in ids])


# --- Happy path ----------------------------------------------------------------

def test_happy_path_matches_the_engine_called_directly(songs):
    fake = FakeClient(interpret=prefs_json(), explain=good_explanations(songs))
    result = recommend_from_text("studying for finals", songs, client=client(fake))

    prefs = parse_preferences(prefs_json(), catalog_vocabulary(songs))
    expected = recommend_songs(to_user_prefs(prefs), songs, 5)
    assert result.ok and result.error_kind is None
    assert [r.song["id"] for r in result.recommendations] == [s["id"] for s, _, _ in expected]
    assert [r.score for r in result.recommendations] == [score for _, score, _ in expected]
    assert all(0.0 <= r.score <= 4.0 for r in result.recommendations)
    assert "AI-generated interpretation" in result.interpretation
    assert fake.kinds() == ["interpret", "explain"]


def test_engine_reasons_are_always_present_next_to_ai_text(songs):
    fake = FakeClient(interpret=prefs_json(), explain=good_explanations(songs))
    result = recommend_from_text("studying", songs, client=client(fake))
    for rec in result.recommendations:
        assert rec.ai_explanation == "A gentle pick for focus."
        assert rec.explanation_source == "ai"
        assert rec.reasons and all(isinstance(r, str) for r in rec.reasons)


def test_warnings_from_validation_reach_the_interpretation(songs):
    fake = FakeClient(interpret=prefs_json(target_energy=1.7), explain=good_explanations(songs))
    result = recommend_from_text("intense", songs, client=client(fake), explain=False)
    assert result.prefs.target_energy == 1.0
    assert "clamped target_energy" in result.interpretation


def test_strategy_is_chosen_by_the_caller_and_gemini_cannot_change_it(songs):
    raw = '{"genres": ["lofi"], "target_energy": 0.3, "strategy": "genre_first", "k": 18}'
    result = recommend_from_text("x", songs, client=client(FakeClient(interpret=raw)),
                                 strategy="classic", explain=False)
    assert result.strategy == "classic" and len(result.recommendations) == 5
    assert "ignored unknown keys" in result.interpretation


def test_unknown_strategy_is_reported_not_raised(songs):
    result = recommend_from_text("x", songs, client=client(FakeClient()), strategy="nope")
    assert not result.ok and result.error_kind == "input"


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_every_strategy_works_through_the_pipeline(songs, strategy):
    fake = FakeClient(interpret=prefs_json())
    result = recommend_from_text("studying", songs, client=client(fake), strategy=strategy, explain=False)
    assert result.ok and len(result.recommendations) == 5


# --- Failures never raise ------------------------------------------------------

@pytest.mark.parametrize("script, kind", [
    (ReadTimeout(), "timeout"),
    (FakeAPIError(503), "unavailable"),
    (FakeAPIError(429), "unavailable"),
    (FakeAPIError(403), "auth"),
    (FakeAPIError(400), "llm_error"),
    (None, "bad_response"),
    ("not json", "invalid_preferences"),
    ("{}", "invalid_preferences"),
    ('{"genres": ["k-pop"]}', "invalid_preferences"),
])
def test_interpretation_failures_return_an_error_result(songs, script, kind):
    result = recommend_from_text("studying", songs, client=client(FakeClient(interpret=script)))
    assert not result.ok and result.error_kind == kind
    assert result.error and result.recommendations == []


def test_missing_api_key_is_reported_cleanly(songs):
    result = recommend_from_text("studying", songs, client=GeminiClient())
    assert not result.ok and result.error_kind == "no_api_key"
    assert "GEMINI_API_KEY" in result.error


@pytest.mark.parametrize("text", ["", "   ", None, "x" * 501])
def test_bad_input_is_reported_without_calling_gemini(songs, text):
    fake = FakeClient(interpret=prefs_json())
    result = recommend_from_text(text, songs, client=client(fake))
    assert not result.ok and result.error_kind == "input" and fake.calls == []


def test_secret_never_appears_in_an_error_result(songs, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-secret-key-123456")
    result = recommend_from_text("hi", songs, client=client(FakeClient(interpret=FakeAPIError(401))))
    assert "dummy-secret-key-123456" not in (result.error or "")


# --- Explanation step is optional and failure-tolerant -------------------------

@pytest.mark.parametrize("failure", [
    ReadTimeout(), FakeAPIError(429), FakeAPIError(503), FakeAPIError(403), None, "garbage",
    RuntimeError("anything at all"),
])
def test_recommendations_survive_any_explanation_failure(songs, failure):
    fake = FakeClient(interpret=prefs_json(), explain=failure)
    result = recommend_from_text("studying", songs, client=client(fake))
    assert result.ok and len(result.recommendations) == 5
    assert all(r.ai_explanation is None and r.explanation_source == "engine" for r in result.recommendations)
    assert all(r.reasons for r in result.recommendations)
    assert result.explanation_note


def test_untrusted_explanations_fall_back_to_the_engine_per_song(songs):
    prefs = parse_preferences(prefs_json(), catalog_vocabulary(songs))
    ranked = recommend_songs(to_user_prefs(prefs), songs, 5)
    ids = [s["id"] for s, _, _ in ranked]
    explain = explanations_json([
        (ids[0], "Similar to Gym Hero."),          # mentions another song -> untrusted
        (ids[1], "A calm, steady pick."),          # fine
        (999, "Invented id."),                     # invalid id
        (ids[2], "It scores 4.0 out of 4."),       # false score claim
    ])
    result = recommend_from_text("studying", songs, client=client(FakeClient(interpret=prefs_json(), explain=explain)))
    by_id = {r.song["id"]: r for r in result.recommendations}
    assert by_id[ids[0]].ai_explanation is None
    assert by_id[ids[1]].ai_explanation == "A calm, steady pick."
    assert by_id[ids[2]].ai_explanation is None
    assert by_id[ids[3]].ai_explanation is None
    assert result.explanation_note and all(r.reasons for r in result.recommendations)


def test_explain_false_skips_the_second_call(songs):
    fake = FakeClient(interpret=prefs_json())
    recommend_from_text("studying", songs, client=client(fake), explain=False)
    assert fake.kinds() == ["interpret"]


def test_explanation_call_gets_engine_facts_only(songs):
    fake = FakeClient(interpret=prefs_json(), explain=good_explanations(songs))
    result = recommend_from_text("studying", songs, client=client(fake))
    contents = fake.calls[1]["contents"]
    for rec in result.recommendations:
        assert rec.song["title"] in contents and f'"score": {round(rec.score, 2)}' in contents


# --- Mock client and CLI (offline demo) ----------------------------------------

def test_mock_gemini_runs_the_full_pipeline_offline(songs):
    mock = MockGemini()
    result = recommend_from_text("I need motivation to work out", songs, client=GeminiClient(client=mock))
    assert result.ok and result.prefs.genres[0] == "EDM"
    assert all(r.ai_explanation for r in result.recommendations)
    assert [c["config"]["response_json_schema"]["properties"].keys() >= {"genres"} for c in mock.calls][0]


def test_mock_gemini_rejects_gibberish_gracefully(songs):
    result = recommend_from_text("asdf qwerty", songs, client=GeminiClient(client=MockGemini()))
    assert not result.ok and result.error_kind == "invalid_preferences"


def test_render_always_shows_engine_reasons(songs):
    result = recommend_from_text("studying for finals", songs, client=GeminiClient(client=MockGemini()))
    text = render(result)
    assert "AI says:" in text and text.count("Engine reasons:") == 5 and "genre match" in text


def test_render_shows_errors_without_a_traceback(songs):
    text = render(recommend_from_text("", songs, client=GeminiClient(client=MockGemini())))
    assert text.startswith("Could not make recommendations (input)")


def test_cli_mock_mode_exits_zero_and_prints_results(capsys):
    assert cli_main(["--mock", "I'm studying for finals"]) == 0
    out = capsys.readouterr().out
    assert "MOCK Gemini" in out and "Top 5 recommendations" in out


def test_cli_without_a_key_exits_nonzero_with_a_clear_message(capsys):
    assert cli_main(["hello there"]) == 1
    assert "GEMINI_API_KEY" in capsys.readouterr().out
