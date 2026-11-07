"""Feedback logic: adjusts the preferences passed to the unchanged engine; reset is exact."""

import copy

import pytest

from src.feedback import (
    DISLIKE, DISLIKE_STEP, LIKE, LIKE_STEP, FeedbackLog, adjust_preferences, recommend_with_feedback,
)
from src.preferences import MAX_LABELS, MoodPreferences, to_user_prefs
from src.recommender import STRATEGIES, load_songs, recommend_songs

# song ids in data/songs.csv
SUNRISE, MIDNIGHT, STORM, LIBRARY, GYM, SPACEWALK, COFFEE, NIGHTDRIVE, FOCUS = 1, 2, 3, 4, 5, 6, 7, 8, 9
LEVELS, CLAIR, SANDMAN = 16, 17, 18


@pytest.fixture(scope="module")
def songs():
    return load_songs("data/songs.csv")


@pytest.fixture(scope="module")
def small(songs):
    """A small isolated catalog (the first 18 rows) so shortfall conditions do not depend on the production catalog size."""
    assert len(songs) >= 18 and songs[0]["id"] == 1 and songs[17]["id"] == 18
    return songs[:18]


def base(**kw):
    data = dict(genres=["lofi"], moods=["chill"], target_energy=0.3)
    data.update(kw)
    return MoodPreferences(**data)


def log_of(*pairs):
    log = FeedbackLog()
    for song_id, vote in pairs:
        log.set(song_id, vote)
    return log


# --- FeedbackLog -------------------------------------------------------------

def test_log_records_clears_and_resets():
    log = log_of((1, LIKE), (2, DISLIKE))
    assert log.liked_ids == [1] and log.disliked_ids == [2] and len(log) == 2
    log.clear(1)
    assert log.get(1) is None and len(log) == 1
    log.reset()
    assert len(log) == 0


def test_revote_replaces_and_moves_to_the_end():
    log = log_of((1, LIKE), (2, LIKE))
    log.set(1, DISLIKE)
    assert list(log.votes) == [2, 1] and log.disliked_ids == [1] and log.liked_ids == [2]


def test_invalid_vote_is_rejected():
    with pytest.raises(ValueError):
        FeedbackLog().set(1, 5)


# --- Label rules ---------------------------------------------------------------

def test_no_feedback_changes_nothing(songs):
    adjusted = adjust_preferences(base(), FeedbackLog(), songs)
    assert adjusted.prefs.genres == ["lofi"] and adjusted.prefs.moods == ["chill"]
    assert adjusted.prefs.target_energy == 0.3 and adjusted.notes == []


def test_a_like_adds_the_songs_new_genre_and_mood(songs):
    adjusted = adjust_preferences(base(), log_of((COFFEE, LIKE)), songs)       # jazz / relaxed
    assert adjusted.prefs.genres == ["lofi", "jazz"] and adjusted.prefs.moods == ["chill", "relaxed"]
    assert any("Added genre jazz because you liked Coffee Shop Stories" in n for n in adjusted.notes)
    assert any("Added mood relaxed" in n for n in adjusted.notes)


def test_one_dislike_keeps_a_label_the_user_chose_two_remove_it(songs):
    one = adjust_preferences(base(), log_of((LIBRARY, DISLIKE)), songs)
    assert "lofi" in one.prefs.genres and "chill" in one.prefs.moods
    two = adjust_preferences(base(), log_of((LIBRARY, DISLIKE), (MIDNIGHT, DISLIKE)), songs)
    assert "lofi" not in two.prefs.genres and "chill" not in two.prefs.moods
    assert any("Dropped genre lofi after you disliked" in n for n in two.notes)


def test_likes_and_dislikes_net_out(songs):
    votes = [(LIBRARY, DISLIKE), (MIDNIGHT, DISLIKE), (FOCUS, LIKE)]   # lofi: 2-1-1+1 = 1 -> kept
    assert "lofi" in adjust_preferences(base(), log_of(*votes), songs).prefs.genres


def test_disliking_a_song_with_an_unchosen_label_adds_nothing(songs):
    adjusted = adjust_preferences(base(), log_of((GYM, DISLIKE)), songs)
    assert adjusted.prefs.genres == ["lofi"] and "pop" not in adjusted.prefs.genres


def test_label_cap(songs):
    likes = [(i, LIKE) for i in (SUNRISE, STORM, COFFEE, NIGHTDRIVE, LEVELS, CLAIR, SANDMAN)]
    adjusted = adjust_preferences(base(), log_of(*likes), songs)
    assert len(adjusted.prefs.genres) <= MAX_LABELS and len(adjusted.prefs.moods) <= MAX_LABELS
    assert "lofi" in adjusted.prefs.genres            # the user's own label has the highest weight


# --- Numeric targets -------------------------------------------------------------

def test_like_moves_energy_toward_the_song_by_the_documented_step(songs):
    adjusted = adjust_preferences(base(), log_of((GYM, LIKE)), songs)            # energy 0.93
    assert adjusted.prefs.target_energy == pytest.approx(0.3 + LIKE_STEP * (0.93 - 0.3))
    assert any("Moved your energy target from 0.30" in n for n in adjusted.notes)


def test_dislike_moves_energy_away_from_the_song(songs):
    adjusted = adjust_preferences(base(target_energy=0.5), log_of((GYM, DISLIKE)), songs)
    assert adjusted.prefs.target_energy == pytest.approx(0.5 - DISLIKE_STEP * (0.93 - 0.5))
    assert adjusted.prefs.target_energy < 0.5


def test_targets_are_clamped_to_zero_one(songs):
    low = adjust_preferences(base(target_energy=0.0), log_of((GYM, DISLIKE), (SANDMAN, DISLIKE)), songs)
    assert low.prefs.target_energy == 0.0
    high = adjust_preferences(base(target_energy=1.0), log_of((CLAIR, DISLIKE)), songs)
    assert 0.0 <= high.prefs.target_energy <= 1.0


def test_unset_valence_and_acousticness_stay_unset(songs):
    adjusted = adjust_preferences(base(), log_of((GYM, LIKE), (CLAIR, LIKE)), songs)
    assert adjusted.prefs.target_valence is None and adjusted.prefs.target_acousticness is None


def test_set_valence_and_acousticness_are_adjusted(songs):
    prefs = base(target_valence=0.5, target_acousticness=0.5)
    adjusted = adjust_preferences(prefs, log_of((CLAIR, LIKE)), songs)           # val .29 acou .98
    assert adjusted.prefs.target_valence < 0.5 < adjusted.prefs.target_acousticness


def test_votes_are_replayed_in_order(songs):
    a = adjust_preferences(base(), log_of((GYM, LIKE), (CLAIR, LIKE)), songs).prefs.target_energy
    b = adjust_preferences(base(), log_of((CLAIR, LIKE), (GYM, LIKE)), songs).prefs.target_energy
    assert a != b and a == adjust_preferences(base(), log_of((GYM, LIKE), (CLAIR, LIKE)), songs).prefs.target_energy


def test_base_is_never_mutated_and_reset_restores_it(songs):
    original = base(warnings=["x"])
    snapshot = copy.deepcopy(original)
    log = log_of((GYM, LIKE), (LIBRARY, DISLIKE))
    adjust_preferences(original, log, songs)
    assert original == snapshot
    log.reset()
    again = adjust_preferences(original, log, songs).prefs
    assert (again.genres, again.moods, again.target_energy) == (["lofi"], ["chill"], 0.3)


def test_unknown_song_ids_are_ignored(songs):
    assert adjust_preferences(base(), log_of((9999, LIKE)), songs).notes == []


# --- Ranking with the unchanged engine ---------------------------------------------

def test_without_feedback_it_equals_the_engine_directly(songs):
    out = recommend_with_feedback(base(), FeedbackLog(), songs, k=5)
    expected = recommend_songs(to_user_prefs(base()), songs, 5)
    assert [(r.song["id"], r.score) for r in out.result.recommendations] == \
           [(s["id"], sc) for s, sc, _ in expected]
    assert out.message is None and out.excluded == [] and out.baseline_titles == []


def test_engine_reasons_are_preserved_with_feedback(songs):
    out = recommend_with_feedback(base(), log_of((COFFEE, LIKE)), songs, k=5)
    adjusted_prefs = adjust_preferences(base(), log_of((COFFEE, LIKE)), songs).prefs
    expected = recommend_songs(to_user_prefs(adjusted_prefs), songs, 5)
    assert [r.reasons for r in out.result.recommendations] == [e.split("; ") for _, _, e in expected]
    assert all(r.reasons for r in out.result.recommendations)


def test_disliked_songs_never_appear_and_are_listed_as_excluded(songs):
    first = recommend_with_feedback(base(), FeedbackLog(), songs, k=5).result.recommendations[0]
    out = recommend_with_feedback(base(), log_of((first.song["id"], DISLIKE)), songs, k=5)
    assert first.song["id"] not in [r.song["id"] for r in out.result.recommendations]
    assert [s["id"] for s in out.excluded] == [first.song["id"]]
    assert len(out.result.recommendations) == 5          # replaced by the next best song


def test_liking_a_new_genre_pulls_that_genre_up(songs):
    before = [r.song["id"] for r in recommend_with_feedback(base(), FeedbackLog(), songs, k=5).result.recommendations]
    after = [r.song["id"] for r in
             recommend_with_feedback(base(), log_of((COFFEE, LIKE)), songs, k=5).result.recommendations]
    assert COFFEE not in before[:2] and after.index(COFFEE) < (before.index(COFFEE) if COFFEE in before else 99)


def test_baseline_titles_show_the_ranking_without_feedback(songs):
    out = recommend_with_feedback(base(), log_of((COFFEE, LIKE)), songs, k=5)
    expected = [s["title"] for s, _, _ in recommend_songs(to_user_prefs(base()), songs, 5)]
    assert out.baseline_titles == expected


def test_shortfall_message_when_too_few_songs_remain(small):
    dislikes = [(s["id"], DISLIKE) for s in small[:16]]                # 2 songs left
    out = recommend_with_feedback(base(), log_of(*dislikes), small, k=5)
    assert len(out.result.recommendations) == 2
    assert "Only 2 of the 5" in out.message and "Undo a dislike or reset feedback" in out.message


def test_all_songs_disliked_gives_an_empty_list_not_a_crash(songs):
    out = recommend_with_feedback(base(), log_of(*[(s["id"], DISLIKE) for s in songs]), songs, k=5)
    assert out.result.ok and out.result.recommendations == [] and out.message


def test_reset_restores_the_original_candidate_pool(small):
    log = log_of(*[(s["id"], DISLIKE) for s in small[:16]])
    log.reset()
    out = recommend_with_feedback(base(), log, small, k=5)
    assert len(out.result.recommendations) == 5 and out.message is None and out.excluded == []


def test_undo_restores_one_song(songs):
    top = recommend_with_feedback(base(), FeedbackLog(), songs, k=5).result.recommendations[0].song["id"]
    log = log_of((top, DISLIKE))
    log.clear(top)
    out = recommend_with_feedback(base(), log, songs, k=5)
    assert out.result.recommendations[0].song["id"] == top


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_every_strategy_works_with_feedback(songs, strategy):
    out = recommend_with_feedback(base(), log_of((COFFEE, LIKE), (GYM, DISLIKE)), songs, k=5, strategy=strategy)
    assert out.result.ok and len(out.result.recommendations) == 5
    assert GYM not in [r.song["id"] for r in out.result.recommendations]
    assert all(0.0 <= r.score <= 4.0 for r in out.result.recommendations)


def test_feedback_makes_no_gemini_call_by_default(songs):
    class Boom:
        models = None
        def __getattr__(self, name):
            raise AssertionError("Gemini must not be called")
    out = recommend_with_feedback(base(), log_of((COFFEE, LIKE)), songs, k=5, client=Boom())
    assert out.result.ok


def test_adjusted_preferences_are_deterministic(songs):
    log = log_of((COFFEE, LIKE), (GYM, DISLIKE), (FOCUS, LIKE))
    assert adjust_preferences(base(), log, songs) == adjust_preferences(base(), log, songs)
