from pathlib import Path

import pytest

from src.explain import (
    MAX_WHY_CHARS,
    build_facts,
    check_explanation,
    format_interpretation,
    validate_explanations,
)
from src.preferences import MoodPreferences, parse_preferences, catalog_vocabulary, to_user_prefs
from src.recommender import load_songs, recommend_songs

CATALOG = Path(__file__).resolve().parent.parent / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(CATALOG))


@pytest.fixture(scope="module")
def prefs(songs):
    return parse_preferences(
        {"genres": ["lofi", "ambient"], "moods": ["focused", "chill"], "target_energy": 0.3,
         "target_valence": 0.5, "target_acousticness": 0.8},
        catalog_vocabulary(songs),
    )


@pytest.fixture(scope="module")
def ranked(songs, prefs):
    return recommend_songs(to_user_prefs(prefs), songs, 5)


@pytest.fixture(scope="module")
def facts(ranked):
    return build_facts(ranked)


@pytest.fixture(scope="module")
def top(facts):
    return facts["songs"][0]     # Library Rain by Paper Lanterns (lofi, chill)


def problem(why, top, prefs, songs):
    return check_explanation(why, top, prefs, songs)


# --- Facts come from the engine -------------------------------------------------

def test_facts_match_the_engine_output_exactly(ranked, facts):
    assert len(facts["songs"]) == len(ranked)
    for fact, (song, score, explanation) in zip(facts["songs"], ranked):
        assert fact["song_id"] == song["id"] and fact["title"] == song["title"]
        assert fact["artist"] == song["artist"] and fact["score"] == round(score, 2)
        assert fact["reasons"] == explanation.split("; ")


# --- Trustworthy text passes, harmless numbers are allowed ----------------------

@pytest.mark.parametrize("why", [
    "A calm lofi track that suits a long study session.",
    "Quiet and acoustic, ideal for two hours of focused reading.",
    "Perfect for those 3 AM cram sessions.",
    "Its chill mood and gentle energy keep you focused.",
    'Library Rain by Paper Lanterns is a soft lofi option.',
    'The track "Library Rain" has a relaxed pace.',
])
def test_harmless_text_and_numbers_are_accepted(why, top, prefs, songs):
    assert problem(why, top, prefs, songs) is None


def test_true_score_and_feature_claims_are_accepted(top, prefs, songs):
    score = top["score"]
    assert problem(f"It scores {score:.2f} out of 4 for you.", top, prefs, songs) is None
    assert problem(f"Its energy of {top['energy']:.2f} is close to your target.", top, prefs, songs) is None
    assert problem(f"Runs at {top['tempo_bpm']} bpm.", top, prefs, songs) is None


# --- Untrustworthy text is rejected ---------------------------------------------

@pytest.mark.parametrize("why, expected", [
    ("Similar to Gym Hero in spirit.", "another song"),
    ("Reminds you of Max Pulse.", "another artist"),
    ('A cousin of "Midnight Dreams" for sure.', "unknown title"),
    ("This track by Taylor Swift is soothing.", "unknown artist"),
    ("Released in 2019 to wide acclaim.", "year"),
    ("From the album Rainy Days.", "unsupported"),
    ("Its lyrics speak of calm.", "unsupported"),
    ("A great metal track for studying.", "different genre"),
    ("It scores 4.0 out of 4 for you.", "false score"),
    ("It earns 9 points from the engine.", "false points"),
    ("A 99% match for your request.", "percentage"),
    ("A perfect match for your request.", "perfect"),
    ("Its energy of 0.99 is exactly your target.", "energy"),
    ("It runs at 200 bpm.", "tempo"),
    ("", "empty"),
    ("   ", "empty"),
    ("x" * (MAX_WHY_CHARS + 1), "too long"),
])
def test_untrustworthy_text_is_rejected(why, expected, top, prefs, songs):
    found = problem(why, top, prefs, songs)
    assert found is not None and expected in found


def test_non_string_why_is_rejected(top, prefs, songs):
    assert problem(None, top, prefs, songs) is not None


def test_own_artist_second_song_is_not_flagged_as_another_artist(songs, prefs):
    # Neon Echo has two songs; mentioning that artist for either one is fine.
    ranked = recommend_songs(to_user_prefs(prefs), songs, len(songs))
    facts = build_facts(ranked)
    neon = next(f for f in facts["songs"] if f["artist"] == "Neon Echo")
    assert problem("A track by Neon Echo that fits.", neon, prefs, songs) is None


# --- validate_explanations ------------------------------------------------------

def test_valid_explanations_for_every_song_are_trusted(facts, prefs, songs):
    items = [{"song_id": f["song_id"], "why": "A gentle pick for focus."} for f in facts["songs"]]
    result = validate_explanations(items, facts, prefs, songs)
    assert set(result.trusted) == {f["song_id"] for f in facts["songs"]} and result.problems == []


def test_invalid_song_ids_are_dropped(facts, prefs, songs):
    items = [{"song_id": 999, "why": "ok"}, {"song_id": "4", "why": "ok"},
             {"song_id": True, "why": "ok"}, {"why": "no id"}, "garbage", None]
    result = validate_explanations(items, facts, prefs, songs)
    assert result.trusted == {} and len(result.problems) == 6


def test_duplicate_ids_are_untrusted(facts, prefs, songs):
    sid = facts["songs"][0]["song_id"]
    items = [{"song_id": sid, "why": "First."}, {"song_id": sid, "why": "Second."}]
    result = validate_explanations(items, facts, prefs, songs)
    assert sid not in result.trusted
    assert any("duplicate" in p for p in result.problems)


def test_missing_songs_simply_have_no_ai_text(facts, prefs, songs):
    sid = facts["songs"][0]["song_id"]
    result = validate_explanations([{"song_id": sid, "why": "Fits."}], facts, prefs, songs)
    assert list(result.trusted) == [sid]


def test_one_bad_explanation_does_not_discard_the_good_ones(facts, prefs, songs):
    a, b = facts["songs"][0]["song_id"], facts["songs"][1]["song_id"]
    items = [{"song_id": a, "why": "Released in 2019."}, {"song_id": b, "why": "Calm and steady."}]
    result = validate_explanations(items, facts, prefs, songs)
    assert list(result.trusted) == [b] and len(result.problems) == 1


# --- Transparency display -------------------------------------------------------

def test_interpretation_shows_every_field_and_the_warnings():
    prefs = MoodPreferences(genres=["pop"], moods=[], target_energy=0.8,
                            warnings=["dropped unknown genre: 'k-pop'"])
    text = format_interpretation("party time", prefs, "balanced", model="m1")
    for expected in ("AI-generated", "party time", "pop", "0.80", "not set (skipped)",
                     "balanced", "m1", "dropped unknown genre: 'k-pop'"):
        assert expected in text
    assert "Moods:         none" in text
