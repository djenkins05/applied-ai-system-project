"""
Regression tests for AI-explanation grounding with the real song titles and artists in the unified catalog.

Written BEFORE the fixes in src/explain.py: each "fix" test failed first (see the numbered defects), and each
"still rejected" test guards against loosening the check. Gemini is never called.
"""

from pathlib import Path

import pytest

from src.explain import build_facts, check_explanation
from src.preferences import catalog_vocabulary, parse_preferences
from src.recommender import load_songs

CATALOG = Path(__file__).resolve().parent.parent / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(CATALOG))


@pytest.fixture(scope="module")
def prefs(songs):
    return parse_preferences({"genres": ["lofi"], "moods": ["chill"], "target_energy": 0.3}, catalog_vocabulary(songs))


def verdict(title, why, songs, prefs):
    song = next(s for s in songs if s["title"] == title)
    fact = build_facts([(song, 3.5, "genre match: lofi (+1.0)")])["songs"][0]
    return check_explanation(why, fact, prefs, songs)


# 1. "by <Artist>." at the end of a sentence (also affects the original catalog)
def test_credit_at_the_end_of_a_sentence_is_accepted(songs, prefs):
    assert verdict("Library Rain", "A soft lofi pick by Paper Lanterns.", songs, prefs) is None
    assert verdict("Moonlight Sonata (1st Movement)", "A reflective piece by Ludwig van Beethoven.", songs, prefs) is None
    assert verdict("Library Rain", "Soft and slow, by Paper Lanterns, with a calm feel.", songs, prefs) is None


def test_a_wrong_credit_is_still_rejected_with_punctuation(songs, prefs):
    assert "unknown artist" in verdict("Library Rain", "A soft lofi pick by Someone Else.", songs, prefs)
    assert verdict("Library Rain", "A soft lofi pick by Max Pulse.", songs, prefs) is not None


# 2. featured credits: a song's primary artist must not count as "another artist"
def test_own_primary_artist_and_full_credit_are_accepted_for_a_featured_song(songs, prefs):
    assert verdict("Feather", "Nujabes built this chill hip-hop beat.", songs, prefs) is None
    assert verdict("Feather", "Feather by Nujabes ft. Cise Starr & Akin is chill.", songs, prefs) is None
    assert verdict("Uptown Funk", "Mark Ronson and Bruno Mars bring a happy pop groove.", songs, prefs) is None
    assert verdict("Aruarian Dance", "Nujabes keeps it chill.", songs, prefs) is None


# 3. a featured artist named on the WRONG song must be rejected
def test_featured_artist_on_the_wrong_song_is_rejected(songs, prefs):
    assert "another artist" in verdict("Levitating", "Bruno Mars shines on this pop track.", songs, prefs)
    assert "another artist" in verdict("Take Five", "Alicia Keys would love this.", songs, prefs)
    assert "another artist" in verdict("Library Rain", "Cise Starr adds a verse.", songs, prefs)


def test_a_real_artist_who_is_another_catalog_artist_is_rejected(songs, prefs):
    assert "another artist" in verdict("Library Rain", "This track by Taylor Swift is soothing.", songs, prefs)
    assert "another song" in verdict("Library Rain", "Like Blinding Lights, but calm.", songs, prefs)


# 4. hyphen continuation: "Feather-light" is not a mention of the song "Feather"
def test_hyphenated_word_is_not_a_title_mention(songs, prefs):
    assert verdict("Library Rain", "Feather-light piano keeps it relaxed.", songs, prefs) is None
    assert "another song" in verdict("Library Rain", "Reminds me of Feather.", songs, prefs)


# 5. curly apostrophes must not hide a mention of another song
def test_curly_apostrophes_do_not_hide_another_songs_title(songs, prefs):
    assert "another song" in verdict("Library Rain", "Pairs well with Don’t Stop ’Til You Get Enough.", songs, prefs)
    assert "another song" in verdict("Library Rain", "Pairs well with Livin’ on a Prayer.", songs, prefs)
    assert verdict("Don't Stop 'Til You Get Enough", "Don’t Stop ’Til You Get Enough is an uplifting disco pick.",
                   songs, prefs) is None


# 6. an abbreviated quoted title (without the parenthetical) is the song's own title
def test_quoted_title_without_the_parenthetical_is_accepted(songs, prefs):
    assert verdict("Moonlight Sonata (1st Movement)", '"Moonlight Sonata" is slow and reflective.', songs, prefs) is None
    assert verdict("Moonlight Sonata (1st Movement)", '"Moonlight Sonata (1st Movement)" is slow.', songs, prefs) is None
    assert "unknown title" in verdict("Moonlight Sonata (1st Movement)", '"Moonlight Serenade" is slow.', songs, prefs)


# 7. documented limitation (NOT changed): ambiguous single-word names are rejected, which is the safe direction
@pytest.mark.parametrize("why", ["Levels of energy stay low and calm.", "Mario would approve."])
def test_ambiguous_single_word_names_remain_rejected_by_design(why, songs, prefs):
    assert verdict("Take Five", why, songs, prefs) is not None


def test_rejection_still_covers_the_original_unsupported_claims(songs, prefs):
    for why in ("Released in 2019 to wide acclaim.", "It runs at 200 bpm.", "A perfect match for your request.",
                "A great metal track for studying."):
        assert verdict("Library Rain", why, songs, prefs) is not None


# --- credits added by the data corrections ---------------------------------------------------------------------
def test_a_true_featured_artist_is_accepted_on_the_song_that_features_them(songs, prefs):
    assert verdict("Bad and Boujee", "Migos and Lil Uzi Vert trade playful trap verses.", songs, prefs) is None
    assert verdict("XO Tour Llif3", "Lil Uzi Vert delivers a melancholic trap track.", songs, prefs) is None
    assert verdict("Gold Digger", "Kanye West and Jamie Foxx make a playful rap hit.", songs, prefs) is None
    assert verdict("Sicko Mode", "Travis Scott and Drake share this moody trap track.", songs, prefs) is None


def test_a_featured_artist_is_still_rejected_on_an_unrelated_song(songs, prefs):
    assert "another artist" in verdict("Take Five", "Lil Uzi Vert would enjoy this.", songs, prefs)
    assert "another artist" in verdict("Levitating", "Drake guests on this pop track.", songs, prefs)


def test_known_limit_true_real_world_names_outside_the_data_are_not_verifiable(songs, prefs):
    # Documented limitation, asserted so it is not forgotten: the check only knows catalog names.
    assert verdict("Wake Me Up", "Aloe Blacc's vocals lift this uplifting EDM track.", songs, prefs) is None
    assert verdict("Levitating", "A playful pop track in the style of Madonna.", songs, prefs) is None
