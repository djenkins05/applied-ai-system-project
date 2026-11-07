"""Data-quality tests for the unified 68-song data/songs.csv (18 original rows + 50 real songs). No Gemini, no network."""

import csv
import hashlib
from collections import Counter
from pathlib import Path

import pytest

from src.preferences import catalog_vocabulary
from src.recommender import STRATEGIES, load_songs

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "songs.csv"
FIELDS = "id,title,artist,genre,mood,energy,tempo_bpm,valence,danceability,acousticness".split(",")
UNIT_FIELDS = ("energy", "valence", "danceability", "acousticness")
ORIGINAL_SHA256 = "7ddfb193f8657ce5f5356df76128b7be388977a5f7d94b2dac9bf472d4b37806"

# Single-word titles and artists that could collide with ordinary words in an AI explanation. The grounding check
# is deliberately strict about them (documented limitation: the app then falls back to the engine's reasons). Adding a
# new single-word name must be a conscious decision.
REVIEWED_SINGLE_WORD_TITLES = {"Levels", "Levitating", "Strobe", "Hypnotize", "HUMBLE.", "Redbone", "Feather", "Nightcall"}
REVIEWED_SINGLE_WORD_ARTISTS = {"ABBA", "AC/DC", "Adele", "Avicii", "Eminem", "Kavinsky", "LoRoom", "MGMT", "Mario",
                                "Metallica", "Motörhead", "Nirvana", "Nujabes", "Skrillex", "TLC", "Voltline",
                                "deadmau5", "tomppabeats"}
RISKY_COMMON_WORDS = {"happy", "alright", "paranoid", "weightless", "affection", "queen", "journey", "future",
                      "spring", "juicy", "power", "love", "heaven", "music", "dance", "party", "chill"}


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(CSV))


def test_catalog_has_exactly_68_songs_with_the_expected_header(songs):
    with open(CSV, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == FIELDS
    assert len(songs) == 68 and sorted(s["id"] for s in songs) == list(range(1, 69))


def test_the_18_original_rows_are_byte_identical_to_the_module_3_file():
    lines = CSV.read_bytes().splitlines(keepends=True)
    assert hashlib.sha256(b"".join(lines[:19])).hexdigest() == ORIGINAL_SHA256


def test_every_row_has_correct_types_and_ranges(songs):
    for s in songs:
        assert isinstance(s["id"], int) and isinstance(s["tempo_bpm"], int)
        assert 40 <= s["tempo_bpm"] <= 220, s["title"]
        for f in UNIT_FIELDS:
            assert isinstance(s[f], float) and 0.0 <= s[f] <= 1.0, (s["title"], f)
        assert s["title"].strip() == s["title"] and s["artist"].strip() == s["artist"] and s["title"] and s["artist"]


def test_titles_are_unique_and_no_placeholder_remains(songs):
    titles = [s["title"].lower() for s in songs]
    assert len(set(titles)) == 68
    assert not any("tbd" in (s["title"] + s["artist"]).lower().split() for s in songs)


def test_vocabulary_is_unchanged_and_every_genre_has_at_least_four_songs(songs):
    vocab = catalog_vocabulary(songs)
    assert len(vocab.genres) == 15 and len(vocab.moods) == 14
    assert min(Counter(s["genre"] for s in songs).values()) >= 4
    assert min(Counter(s["mood"] for s in songs).values()) >= 2          # ominous has the fewest (2)


def test_single_word_names_are_reviewed_and_not_ordinary_words(songs):
    assert {s["title"] for s in songs if len(s["title"].split()) == 1} == REVIEWED_SINGLE_WORD_TITLES
    assert {s["artist"] for s in songs if len(s["artist"].split()) == 1} == REVIEWED_SINGLE_WORD_ARTISTS
    vocab = catalog_vocabulary(songs)
    words = RISKY_COMMON_WORDS | {g.lower() for g in vocab.genres} | {m.lower() for m in vocab.moods}
    for s in songs:
        for name in (s["title"], s["artist"]):
            if len(name.split()) == 1 and name not in ("Levels", "Mario"):   # documented limitation: pre-existing names
                assert name.lower() not in words, f"{name!r} is an ordinary word and would trip the grounding check"


def test_data_card_documents_the_estimates():
    card = (ROOT / "data" / "README.md").read_text()
    assert "approximate editorial estimates" in card and "not** Spotify" in card
    assert "ids 1 to 18" in card and "ids 19 to 68" in card


def test_strategy_weights_still_sum_to_four():
    for weights in STRATEGIES.values():
        assert abs(sum(weights.values()) - 4.0) < 1e-9


# --- data-quality corrections (rows 19-68 only), pinned so they cannot silently revert ---------------------------
CORRECTIONS = {
    "Bad and Boujee": {"artist": "Migos ft. Lil Uzi Vert", "valence": 0.50},
    "Gold Digger": {"artist": "Kanye West ft. Jamie Foxx"},
    "Sicko Mode": {"artist": "Travis Scott ft. Drake"},
    "Feather": {"genre": "hip-hop"},
    "As It Was": {"genre": "pop", "mood": "moody"},
    "Wake Me Up": {"acousticness": 0.20},
    "Discreet Music": {"acousticness": 0.25},
    "An Ending (Ascent)": {"acousticness": 0.30},
    "HUMBLE.": {"energy": 0.75},
    "Strobe": {"energy": 0.60},                       # deliberately unchanged
    "Stayin' Alive": {"mood": "intense"},             # deliberately unchanged
    "Blinding Lights": {"genre": "synthwave"},        # deliberately unchanged
}


def test_the_approved_corrections_are_in_place(songs):
    by_title = {s["title"]: s for s in songs}
    for title, expected in CORRECTIONS.items():
        for column, value in expected.items():
            assert by_title[title][column] == value, (title, column)
            assert by_title[title]["id"] >= 19, title             # only real-song rows are ever corrected


def test_featured_credits_are_consistent_across_songs(songs):
    credits = {s["title"]: s["artist"] for s in songs}
    assert credits["Bad and Boujee"].endswith("ft. Lil Uzi Vert") and credits["XO Tour Llif3"] == "Lil Uzi Vert"
    assert "ft." in credits["Gold Digger"] and "ft." in credits["Sicko Mode"]


def test_every_genre_still_has_four_songs_after_the_label_changes(songs):
    counts = Counter(s["genre"] for s in songs)
    assert min(counts.values()) >= 4 and counts["lofi"] >= 4 and counts["indie pop"] >= 4
