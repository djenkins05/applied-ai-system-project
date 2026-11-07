import json
from pathlib import Path

import pytest

from src.preferences import (
    DEFAULT_ENERGY,
    MAX_LABELS,
    PREFERENCE_JSON_SCHEMA,
    MoodPreferences,
    PreferenceError,
    catalog_vocabulary,
    parse_preferences,
    to_user_prefs,
)
from src.recommender import load_songs, recommend_songs

CATALOG = Path(__file__).resolve().parent.parent / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(CATALOG))


@pytest.fixture(scope="module")
def vocab(songs):
    return catalog_vocabulary(songs)


VALID = {
    "genres": ["lofi", "ambient"],
    "moods": ["focused", "chill"],
    "target_energy": 0.3,
    "target_valence": 0.5,
    "target_acousticness": 0.7,
}


# --- Vocabulary ---------------------------------------------------------------

def test_vocabulary_matches_the_real_catalog(vocab):
    assert len(vocab.genres) == 15 and "EDM" in vocab.genres and "R&B" in vocab.genres
    assert len(vocab.moods) == 14 and "uplifting" in vocab.moods


def test_schema_describes_the_five_fields():
    assert set(PREFERENCE_JSON_SCHEMA["properties"]) == {
        "genres", "moods", "target_energy", "target_valence", "target_acousticness",
    }


# --- Happy paths and input formats --------------------------------------------

def test_valid_dict_parses_with_no_warnings(vocab):
    prefs = parse_preferences(VALID, vocab)
    assert prefs.genres == ["lofi", "ambient"]
    assert prefs.moods == ["focused", "chill"]
    assert (prefs.target_energy, prefs.target_valence, prefs.target_acousticness) == (0.3, 0.5, 0.7)
    assert prefs.warnings == []


def test_json_string_matches_dict(vocab):
    assert parse_preferences(json.dumps(VALID), vocab) == parse_preferences(VALID, vocab)


def test_json_inside_markdown_fences_is_parsed(vocab):
    fenced = "```json\n" + json.dumps(VALID) + "\n```"
    assert parse_preferences(fenced, vocab) == parse_preferences(VALID, vocab)


# --- Malformed responses ------------------------------------------------------

@pytest.mark.parametrize("raw", ["not json at all", "[1, 2, 3]", '"just text"', "", "   ", None, 42, ["lofi"]])
def test_malformed_responses_raise(vocab, raw):
    with pytest.raises(PreferenceError):
        parse_preferences(raw, vocab)


# --- Nothing usable: must fail, not succeed on a defaulted energy -------------

@pytest.mark.parametrize("raw", [
    {},
    "{}",
    {"genres": [], "moods": []},
    {"genres": ["k-pop"], "moods": ["nostalgic"]},
    {"target_energy": "loud", "target_valence": float("nan")},
    {"unrelated": 1},
])
def test_responses_with_nothing_usable_raise(vocab, raw):
    with pytest.raises(PreferenceError):
        parse_preferences(raw, vocab)


def test_one_usable_field_is_enough(vocab):
    assert parse_preferences({"genres": ["pop"]}, vocab).genres == ["pop"]
    assert parse_preferences({"moods": ["happy"]}, vocab).moods == ["happy"]
    assert parse_preferences({"target_valence": 0.2}, vocab).target_valence == 0.2


# --- Genres and moods ---------------------------------------------------------

def test_case_and_whitespace_are_canonicalized_to_catalog_spelling(vocab):
    prefs = parse_preferences({"genres": ["edm", " Lofi ", "r&b"], "moods": ["UPLIFTING"]}, vocab)
    assert prefs.genres == ["EDM", "lofi", "R&B"]
    assert prefs.moods == ["uplifting"]
    assert prefs.warnings == [f"target_energy missing; using neutral default {DEFAULT_ENERGY}"]


def test_unknown_labels_are_dropped_with_a_warning(vocab):
    prefs = parse_preferences({"genres": ["pop", "k-pop"], "moods": ["happy", "nostalgic"]}, vocab)
    assert prefs.genres == ["pop"] and prefs.moods == ["happy"]
    assert any("k-pop" in w for w in prefs.warnings)
    assert any("nostalgic" in w for w in prefs.warnings)


def test_lone_string_is_wrapped_in_a_list(vocab):
    assert parse_preferences({"genres": "jazz"}, vocab).genres == ["jazz"]


def test_non_list_and_non_text_entries_are_ignored_with_warnings(vocab):
    prefs = parse_preferences({"genres": {"pop": 1}, "moods": ["happy", 7, None]}, vocab)
    assert prefs.genres == [] and prefs.moods == ["happy"]
    assert len(prefs.warnings) >= 2


def test_duplicates_are_removed(vocab):
    assert parse_preferences({"genres": ["pop", "POP", "pop"]}, vocab).genres == ["pop"]


def test_long_lists_are_truncated_with_a_warning(vocab):
    prefs = parse_preferences({"genres": list(vocab.genres)}, vocab)
    assert len(prefs.genres) == MAX_LABELS
    assert any("kept the first" in w for w in prefs.warnings)


# --- Numbers ------------------------------------------------------------------

def test_missing_energy_defaults_with_a_warning_when_something_else_is_usable(vocab):
    prefs = parse_preferences({"genres": ["pop"]}, vocab)
    assert prefs.target_energy == DEFAULT_ENERGY
    assert any("target_energy" in w for w in prefs.warnings)


def test_missing_valence_and_acousticness_stay_none(vocab):
    prefs = parse_preferences({"genres": ["pop"], "target_energy": 0.8}, vocab)
    assert prefs.target_valence is None and prefs.target_acousticness is None
    assert prefs.warnings == []


def test_out_of_range_numbers_are_clamped_with_warnings(vocab):
    prefs = parse_preferences(
        {"target_energy": 1.7, "target_valence": -1, "target_acousticness": 0.5}, vocab
    )
    assert prefs.target_energy == 1.0 and prefs.target_valence == 0.0
    assert prefs.target_acousticness == 0.5
    assert len([w for w in prefs.warnings if "clamped" in w]) == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "high", [0.5], {"v": 1}])
def test_unusable_numbers_are_treated_as_missing(vocab, bad):
    prefs = parse_preferences({"genres": ["pop"], "target_valence": bad}, vocab)
    assert prefs.target_valence is None
    assert any("target_valence" in w for w in prefs.warnings)


def test_numeric_strings_are_coerced(vocab):
    assert parse_preferences({"target_energy": " 0.7 "}, vocab).target_energy == 0.7


def test_extra_keys_are_ignored_with_a_warning(vocab):
    prefs = parse_preferences({**VALID, "tempo": 120, "k": 50}, vocab)
    assert prefs.genres == ["lofi", "ambient"]
    assert any("k, tempo" in w for w in prefs.warnings)


# --- Adapter ------------------------------------------------------------------

def test_adapter_supplies_every_key_the_engine_needs():
    user_prefs = to_user_prefs(MoodPreferences(genres=["pop"], moods=["happy"], target_energy=0.8))
    assert user_prefs["favorite_genres"] == {"pop"}
    assert user_prefs["favorite_moods"] == {"happy"}
    assert user_prefs["target_energy"] == 0.8
    assert user_prefs["favorite_genre"] == "" and user_prefs["favorite_mood"] == ""


def test_adapter_omits_none_targets():
    user_prefs = to_user_prefs(MoodPreferences(genres=["pop"]))
    assert "target_valence" not in user_prefs and "target_acousticness" not in user_prefs


# --- Integration with the unmodified recommender ------------------------------

def test_adapter_output_runs_through_the_real_recommender(songs, vocab):
    user_prefs = to_user_prefs(parse_preferences(VALID, vocab))
    results = recommend_songs(user_prefs, songs, k=5)
    assert len(results) == 5
    assert all(0.0 <= score <= 4.0 for _, score, _ in results)
    assert results[0][0]["genre"] in {"lofi", "ambient"}


def test_lowercase_genre_from_the_model_now_matches(songs, vocab):
    prefs = parse_preferences({"genres": ["edm"], "moods": ["uplifting"], "target_energy": 0.95}, vocab)
    top, score, _ = recommend_songs(to_user_prefs(prefs), songs, k=1)[0]
    assert top["title"] == "Levels"
    assert score > 3.5


def test_labels_that_all_get_dropped_still_run_without_a_crash(songs, vocab):
    prefs = parse_preferences({"genres": ["k-pop"], "target_energy": 0.5}, vocab)
    results = recommend_songs(to_user_prefs(prefs), songs, k=3)
    assert len(results) == 3
    assert all(0.0 <= score <= 4.0 for _, score, _ in results)


def test_clamped_energy_never_produces_negative_scores(songs, vocab):
    prefs = parse_preferences({"genres": ["pop"], "target_energy": -5}, vocab)
    results = recommend_songs(to_user_prefs(prefs), songs, k=len(songs), strategy="classic")
    assert all(score >= 0.0 for _, score, _ in results)


@pytest.mark.parametrize("strategy", ["balanced", "classic", "genre_first", "mood_first", "energy_focused"])
def test_missing_valence_and_acousticness_can_still_reach_four_points(songs, vocab, strategy):
    prefs = parse_preferences({"genres": ["EDM"], "moods": ["uplifting"], "target_energy": 0.95}, vocab)
    results = recommend_songs(to_user_prefs(prefs), songs, k=1, strategy=strategy)
    assert results[0][1] <= 4.0 + 1e-9
    assert results[0][1] > 3.9
