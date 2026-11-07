"""The unified 68-song catalog through the pipeline, feedback and grounding. Gemini is always mocked or fake."""

import pytest

from fakes import FakeClient, explanations_json, prefs_json
from src.explain import check_explanation
from src.feedback import DISLIKE, LIKE, FeedbackLog, recommend_with_feedback
from src.llm import GeminiClient
from src.mock_llm import MockGemini
from src.pipeline import recommend_from_manual, recommend_from_text
from src.fallback import ManualPreferences, available_options
from src.preferences import catalog_vocabulary, parse_preferences, to_user_prefs
from src.recommender import STRATEGIES, load_songs, recommend_songs


@pytest.fixture(scope="module")
def songs():
    return load_songs("data/songs.csv")


def mock_client():
    return GeminiClient(client=MockGemini(), model="mock", sleep=lambda _s: None)


# --- Mock Gemini interpretations rank real songs, and the engine alone decides ----------

@pytest.mark.parametrize("text, genres", [
    ("I'm studying for finals", {"lofi", "ambient", "classical"}),
    ("I need motivation to work out", {"EDM", "pop", "metal"}),
    ("it's a party, let's dance", {"pop", "disco", "EDM"}),
    ("help me relax and sleep", {"ambient", "classical", "jazz"}),
])
def test_mock_requests_pick_matching_songs(songs, text, genres):
    result = recommend_from_text(text, songs, client=mock_client(), k=5)
    assert result.ok and len(result.recommendations) == 5
    assert result.recommendations[0].song["genre"] in genres
    assert {r.song["id"] for r in result.recommendations} <= {s["id"] for s in songs}


def test_pipeline_ranking_equals_the_engine_run_directly(songs):
    fake = FakeClient(interpret=prefs_json(genres=["jazz"], moods=["relaxed"], target_energy=0.3))
    result = recommend_from_text("calm evening", songs, client=GeminiClient(client=fake, sleep=lambda _s: None),
                                 k=5, explain=False)
    prefs = parse_preferences(prefs_json(genres=["jazz"], moods=["relaxed"], target_energy=0.3),
                              catalog_vocabulary(songs))
    expected = recommend_songs(to_user_prefs(prefs), songs, 5)
    assert [(r.song["id"], r.score) for r in result.recommendations] == [(s["id"], sc) for s, sc, _ in expected]


def test_every_song_can_be_ranked_by_every_strategy(songs):
    prefs = to_user_prefs(parse_preferences(prefs_json(genres=["pop"], moods=["happy"], target_energy=0.8),
                                            catalog_vocabulary(songs)))
    for strategy in STRATEGIES:
        ranked = recommend_songs(prefs, songs, len(songs), strategy)
        assert len(ranked) == 68 and all(0 <= sc <= 4.0 for _, sc, _ in ranked)


def test_manual_fallback_uses_the_catalog_options(songs):
    options = available_options(catalog_vocabulary(songs))
    assert "metal" in options["genres"] and "ominous" in options["moods"]
    result = recommend_from_manual(ManualPreferences(genres=["jazz"], moods=["relaxed"], energy=0.3), songs, k=3)
    assert result.ok and result.recommendations[0].song["genre"] == "jazz"


# --- Feedback works on real songs ----------------------------------------------------------

def base_prefs(songs):
    return parse_preferences(prefs_json(genres=["pop"], moods=["happy"], target_energy=0.6), catalog_vocabulary(songs))


def test_like_adds_labels_and_improves_the_liked_song(songs):
    base = base_prefs(songs)
    before = recommend_with_feedback(base, FeedbackLog(), songs, k=10)
    jazz = next(s for s in songs if s["genre"] == "jazz")
    log = FeedbackLog()
    log.set(jazz["id"], LIKE)
    after = recommend_with_feedback(base, log, songs, k=10)
    assert any("jazz" in note for note in after.adjusted.notes)
    assert after.adjusted.prefs.genres != before.adjusted.prefs.genres


def test_dislike_excludes_the_song_and_reset_restores_the_baseline_exactly(songs):
    base = base_prefs(songs)
    baseline = recommend_with_feedback(base, FeedbackLog(), songs, k=5)
    top = baseline.result.recommendations[0].song["id"]
    log = FeedbackLog()
    log.set(top, DISLIKE)
    out = recommend_with_feedback(base, log, songs, k=5)
    assert top not in [r.song["id"] for r in out.result.recommendations]
    assert [s["id"] for s in out.excluded] == [top]
    log.reset()
    again = recommend_with_feedback(base, log, songs, k=5)
    assert [(r.song["id"], r.score) for r in again.result.recommendations] == \
           [(r.song["id"], r.score) for r in baseline.result.recommendations]


def test_feedback_makes_no_gemini_calls_without_explain(songs):
    fake = FakeClient(interpret=prefs_json(), explain=explanations_json([]))
    log = FeedbackLog()
    log.set(songs[0]["id"], LIKE)
    recommend_with_feedback(base_prefs(songs), log, songs, k=5, client=GeminiClient(client=fake, sleep=lambda _s: None))
    assert fake.calls == []


# --- Grounded explanations with real, punctuation-heavy names ---------------------------------

def fact_for(song, songs, score=3.5):
    return {"song_id": song["id"], "title": song["title"], "artist": song["artist"], "genre": song["genre"],
            "mood": song["mood"], "score": score, "reasons": []}


def by_title(songs, title):
    return next(s for s in songs if s["title"] == title)


def test_grounding_accepts_a_true_sentence_naming_the_song_with_special_characters(songs):
    prefs = parse_preferences(prefs_json(), catalog_vocabulary(songs))
    for title in ("Ace of Spades", "Don't Stop 'Til You Get Enough", "HUMBLE.", "Gymnopédie No. 1"):
        song = by_title(songs, title)
        why = f"{song['title']} by {song['artist']} fits your {song['mood']} mood."
        assert check_explanation(why, fact_for(song, songs), prefs, songs) is None, title


def test_grounding_rejects_other_real_songs_or_artists_and_invented_facts(songs):
    prefs = parse_preferences(prefs_json(), catalog_vocabulary(songs))
    song = by_title(songs, "Take Five")
    fact = fact_for(song, songs)
    assert check_explanation("Much like Blinding Lights, this is relaxing.", fact, prefs, songs)
    assert check_explanation("Reminds me of Miles Davis.", fact, prefs, songs)
    assert check_explanation("A classic released in 1959.", fact, prefs, songs)
    assert check_explanation("A calm jazz pick for you.", fact, prefs, songs) is None


def test_explanations_flow_end_to_end_on_the_catalog(songs):
    result = recommend_from_text("studying", songs, client=mock_client(), k=3, explain=True)
    assert result.ok
    shown = [r for r in result.recommendations if r.ai_explanation]
    assert shown and all(r.song["title"] in {s["title"] for s in songs} for r in result.recommendations)
