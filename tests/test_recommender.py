from pathlib import Path

import pytest

from src.recommender import (
    STRATEGIES,
    Recommender,
    Song,
    UserProfile,
    load_songs,
    recommend_songs,
    score_song,
)

def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


# ---------------------------------------------------------------------------
# Scoring logic (score_song / recommend_songs / load_songs)
# ---------------------------------------------------------------------------

def make_song(title="Song", genre="pop", mood="happy", energy=0.5, valence=0.5, acousticness=0.5):
    return {
        "id": 0, "title": title, "artist": "Artist", "genre": genre, "mood": mood,
        "energy": energy, "tempo_bpm": 100, "valence": valence,
        "danceability": 0.5, "acousticness": acousticness,
    }


def make_prefs(**overrides):
    prefs = {
        "favorite_genres": {"pop"},
        "favorite_moods": {"happy"},
        "target_energy": 0.5,
        "target_valence": 0.5,
        "target_acousticness": 0.5,
    }
    prefs.update(overrides)
    return prefs


def test_perfect_match_scores_max_in_classic_mode():
    score, _ = score_song(make_prefs(), make_song())
    assert score == pytest.approx(4.0)


def test_no_label_match_scores_only_energy_closeness():
    song = make_song(genre="metal", mood="intense", energy=0.9)
    score, reasons = score_song(make_prefs(target_energy=0.5), song, "classic")
    assert score == pytest.approx(1.0 - 0.4)
    assert len(reasons) == 1 and reasons[0].startswith("energy")


def test_genre_match_is_worth_two_points_and_mood_one_in_classic_mode():
    base, _ = score_song(make_prefs(), make_song(genre="metal", mood="intense"), "classic")
    with_genre, _ = score_song(make_prefs(), make_song(genre="pop", mood="intense"), "classic")
    with_mood, _ = score_song(make_prefs(), make_song(genre="metal", mood="happy"), "classic")
    assert with_genre - base == pytest.approx(2.0)
    assert with_mood - base == pytest.approx(1.0)


def test_classic_mode_ignores_valence_and_acousticness():
    near, _ = score_song(make_prefs(), make_song(valence=0.5, acousticness=0.5), "classic")
    far, _ = score_song(make_prefs(), make_song(valence=0.0, acousticness=1.0), "classic")
    assert near == pytest.approx(far)


@pytest.mark.parametrize("strategy", [s for s in STRATEGIES if s != "classic"])
def test_other_modes_reward_matching_valence_and_acousticness(strategy):
    near, _ = score_song(make_prefs(), make_song(valence=0.5, acousticness=0.5), strategy)
    far, _ = score_song(make_prefs(), make_song(valence=0.0, acousticness=1.0), strategy)
    assert near > far


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_every_strategy_caps_at_four_points(strategy):
    assert sum(STRATEGIES[strategy].values()) == pytest.approx(4.0)
    score, _ = score_song(make_prefs(), make_song(), strategy)
    assert score == pytest.approx(4.0)


def test_missing_valence_and_acousticness_targets_are_skipped():
    prefs = make_prefs()
    del prefs["target_valence"], prefs["target_acousticness"]
    score, reasons = score_song(prefs, make_song(), "mood_first")
    assert score == pytest.approx(4.0)  # weights are rescaled over the signals that are used
    assert not any(r.startswith(("valence", "acousticness")) for r in reasons)


def test_recommend_songs_returns_k_results_sorted_high_to_low():
    songs = [make_song("A", genre="metal", mood="intense", energy=0.9),
             make_song("B"),
             make_song("C", genre="pop", mood="intense", energy=0.6)]
    results = recommend_songs(make_prefs(), songs, k=2)
    assert len(results) == 2
    assert [r[0]["title"] for r in results] == ["B", "C"]
    assert results[0][1] >= results[1][1]


def test_ties_break_by_energy_gap_then_title():
    # Both songs have no label match. Energy gaps differ, so the closer one wins.
    closer = make_song("Z closer", genre="x", mood="x", energy=0.55)
    farther = make_song("A farther", genre="x", mood="x", energy=0.70)
    results = recommend_songs(make_prefs(), [farther, closer], k=2)
    assert results[0][0]["title"] == "Z closer"

    # Identical songs tie fully, so the title decides.
    twin_b = make_song("B twin")
    twin_a = make_song("A twin")
    results = recommend_songs(make_prefs(), [twin_b, twin_a], k=2)
    assert [r[0]["title"] for r in results] == ["A twin", "B twin"]


def test_strategy_changes_the_winner_in_the_genre_trap_case():
    # Wants metal, but also a calm, chill vibe.
    prefs = make_prefs(favorite_genres={"metal"}, favorite_moods={"chill"}, target_energy=0.2)
    loud_metal = make_song("Loud Metal", genre="metal", mood="ominous", energy=0.97)
    calm_chill = make_song("Calm Chill", genre="ambient", mood="chill", energy=0.28)

    classic = recommend_songs(prefs, [calm_chill, loud_metal], k=1, strategy="classic")[0][0]["title"]
    mood_first = recommend_songs(prefs, [calm_chill, loud_metal], k=1, strategy="mood_first")[0][0]["title"]
    assert classic == "Loud Metal"
    assert mood_first == "Calm Chill"


def test_reason_text_lists_each_scored_signal():
    _, reasons = score_song(make_prefs(), make_song(), "mood_first")
    assert any(r.startswith("genre match") for r in reasons)
    assert any(r.startswith("mood match") for r in reasons)
    assert any(r.startswith("valence") for r in reasons)


def test_load_songs_reads_the_catalog_with_numeric_types():
    import hashlib

    csv_path = Path(__file__).resolve().parent.parent / "data" / "songs.csv"
    songs = load_songs(str(csv_path))
    assert len(songs) == 68                        # fixed catalog: 18 original rows + 50 real songs
    assert sorted(song["id"] for song in songs) == list(range(1, 69))
    # the 18 original rows (header + first 18 lines) are byte-identical to the original Module 3 file
    original = b"".join(csv_path.read_bytes().splitlines(keepends=True)[:19])
    assert hashlib.sha256(original).hexdigest() == "7ddfb193f8657ce5f5356df76128b7be388977a5f7d94b2dac9bf472d4b37806"
    for song in songs:                             # types and ranges for EVERY song, not just the first
        assert isinstance(song["id"], int) and isinstance(song["tempo_bpm"], int)
        for field in ("energy", "valence", "danceability", "acousticness"):
            assert isinstance(song[field], float) and 0.0 <= song[field] <= 1.0


# ---------------------------------------------------------------------------
# Known problems found during evaluation.
# Each is marked xfail(strict=True): it passes the day the bug is fixed and
# the test then fails loudly, reminding you to remove the marker.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="empty genre/mood sets fall through to a missing key (KeyError)")
def test_empty_preferences_do_not_crash():
    prefs = make_prefs(favorite_genres=set(), favorite_moods=set())
    score_song(prefs, make_song())


@pytest.mark.xfail(strict=True, reason="out-of-range energy targets produce negative scores")
def test_scores_are_never_negative():
    song = make_song(genre="metal", mood="intense", energy=0.9)  # no label match
    score, _ = score_song(make_prefs(target_energy=-1.0), song, "classic")
    assert score >= 0.0


@pytest.mark.xfail(strict=True, reason="genre and mood matching is case-sensitive ('edm' != 'EDM')")
def test_genre_and_mood_matching_ignores_case():
    prefs = make_prefs(favorite_genres={"edm"}, favorite_moods={"UPLIFTING"})
    song = make_song(genre="EDM", mood="uplifting")
    score, _ = score_song(prefs, song)
    assert score == pytest.approx(4.0)


def test_recommender_class_ranks_by_score_not_list_order():
    rec = Recommender([
        Song(1, "Chill Lofi Loop", "A", "lofi", "chill", 0.4, 80, 0.6, 0.5, 0.9),
        Song(2, "Test Pop Track", "A", "pop", "happy", 0.8, 120, 0.9, 0.8, 0.2),
    ])
    user = UserProfile("pop", "happy", 0.8, False)
    results = rec.recommend(user, k=2)
    assert [s.title for s in results] == ["Test Pop Track", "Chill Lofi Loop"]
    assert all(isinstance(s, Song) for s in results)


def test_recommender_class_respects_k_and_strategy():
    songs = [
        Song(1, "Loud Metal", "A", "metal", "ominous", 0.97, 123, 0.2, 0.5, 0.01),
        Song(2, "Calm Chill", "A", "ambient", "chill", 0.28, 60, 0.6, 0.4, 0.9),
    ]
    user = UserProfile("metal", "chill", 0.2, True)
    assert len(Recommender(songs).recommend(user, k=1)) == 1
    assert Recommender(songs, strategy="classic").recommend(user, k=1)[0].title == "Loud Metal"
    assert Recommender(songs, strategy="mood_first").recommend(user, k=1)[0].title == "Calm Chill"


def test_explain_recommendation_names_the_song_score_and_reasons():
    rec = make_small_recommender()
    user = UserProfile("pop", "happy", 0.8, False)
    explanation = rec.explain_recommendation(user, rec.songs[0])
    assert "Test Pop Track" in explanation
    assert "4.00 / 4.00" in explanation
    assert "genre match: pop" in explanation and "mood match: happy" in explanation


def test_balanced_mode_lets_a_mood_and_energy_fit_beat_a_genre_only_match():
    # Wants metal, but also a calm, chill vibe.
    prefs = make_prefs(favorite_genres={"metal"}, favorite_moods={"chill"}, target_energy=0.2)
    loud_metal = make_song("Loud Metal", genre="metal", mood="ominous", energy=0.97)
    calm_chill = make_song("Calm Chill", genre="ambient", mood="chill", energy=0.28)
    top = recommend_songs(prefs, [loud_metal, calm_chill], k=1, strategy="balanced")[0][0]
    assert top["title"] == "Calm Chill"


def test_balanced_mode_gives_genre_no_more_weight_than_any_other_signal():
    weights = STRATEGIES["balanced"]
    assert weights["genre"] <= min(weights["mood"], weights["energy"])


def test_balanced_is_the_default_mode():
    from src.recommender import DEFAULT_STRATEGY
    assert DEFAULT_STRATEGY == "balanced"
    song, prefs = make_song(), make_prefs()
    assert score_song(prefs, song) == score_song(prefs, song, "balanced")


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_a_profile_missing_targets_can_still_reach_four_points(strategy):
    prefs = {"favorite_genres": {"pop"}, "favorite_moods": {"happy"}, "target_energy": 0.5}
    score, _ = score_song(prefs, make_song(), strategy)
    assert score == pytest.approx(4.0)

