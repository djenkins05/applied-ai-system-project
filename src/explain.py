"""
Grounding and display helpers for MoodMix AI explanations.

The recommender's own scores and reasons are the ground truth. Gemini may add one
"why it fits" sentence per song; validate_explanations() rejects any sentence that
cannot be trusted, and the caller falls back to the engine's reasons for that song.

What the checks catch (and what they cannot):
  - Catches: invalid/duplicate song ids, other catalog songs or artists, quoted or
    "by <Name>" titles/artists that are not this song's, metadata we do not have
    (years, albums, lyrics, chart claims), a different genre than the song's, false
    score claims, and wrong energy/valence/acousticness/bpm values.
  - Harmless numbers in ordinary prose ("two hours", "3 AM") are allowed.
  - Cannot prove vague claims ("perfect for rainy days") are true, which is why the
    engine's scoring reasons are always shown next to any AI sentence.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.preferences import MoodPreferences, catalog_vocabulary

MAX_WHY_CHARS = 300
SCORE_TOLERANCE = 0.06      # allows 1-decimal rounding of a 2-decimal score
FEATURE_TOLERANCE = 0.06
FEATURES = ("energy", "valence", "acousticness", "danceability")

_NUM = r"(\d+(?:\.\d+)?)"
_UNSUPPORTED_WORDS = re.compile(
    r"\b(album|albums|released|lyrics?|featuring|feat\.?|grammy|billboard|charts?|platinum|"
    r"record label|sampled?)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_SCORE_CLAIMS = (
    re.compile(_NUM + r"\s*(?:/|out of)\s*4(?:\.0+)?\b", re.IGNORECASE),
    re.compile(r"\bscor(?:e|ed|es|ing)\b[^.\d]{0,20}" + _NUM, re.IGNORECASE),
)
_POINTS_CLAIM = re.compile(_NUM + r"\s*points?\b", re.IGNORECASE)
_PERCENT_CLAIM = re.compile(_NUM + r"\s*%\s*(?:match|fit|score)", re.IGNORECASE)
_PERFECT_CLAIM = re.compile(r"\b(?:perfect|flawless|maximum|max)\s+(?:score|match)\b", re.IGNORECASE)
_FEATURE_CLAIM = re.compile(r"\b(" + "|".join(FEATURES) + r")\b[^.\d]{0,15}(\d*\.\d+|\d+)", re.IGNORECASE)
_BPM_CLAIM = re.compile(r"(\d+)\s*bpm", re.IGNORECASE)
_QUOTED = re.compile(r'"([^"]{2,60})"|“([^”]{2,60})”')
_BY_NAME = re.compile(r"\bby\s+([A-Z][\w'.&-]*(?:\s+[A-Z][\w'.&-]*){0,3})")


@dataclass
class CheckedExplanations:
    """Result of validating Gemini's explanations."""
    trusted: Dict[int, str] = field(default_factory=dict)   # song_id -> accepted sentence
    problems: List[str] = field(default_factory=list)       # why anything was rejected


def build_facts(recommendations: Sequence[Tuple[Dict, float, str]]) -> Dict[str, Any]:
    """Ground-truth records taken straight from the engine's own output."""
    songs = []
    for song, score, explanation in recommendations:
        songs.append({
            "song_id": song["id"],
            "title": song["title"],
            "artist": song["artist"],
            "genre": song["genre"],
            "mood": song["mood"],
            "energy": song["energy"],
            "valence": song["valence"],
            "acousticness": song["acousticness"],
            "danceability": song["danceability"],
            "tempo_bpm": song["tempo_bpm"],
            "score": round(score, 2),
            "reasons": explanation.split("; "),
        })
    return {"songs": songs}


def _word_in(needle: str, haystack: str, ignore_case: bool, join_hyphen: bool = False) -> bool:
    """Whole-word search. With join_hyphen, a hyphen continues the word ("Feather-light" is not "Feather")."""
    flags = re.IGNORECASE if ignore_case else 0
    before, after = (r"(?<![\w-])", r"(?![\w-])") if join_hyphen else (r"(?<!\w)", r"(?!\w)")
    return re.search(before + re.escape(needle) + after, haystack, flags) is not None


def _normalize(text: str) -> str:
    """Straight apostrophes, so "Don’t Stop ’Til…" (curly) cannot hide a mention of "Don't Stop 'Til…"."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


_FEATURED = re.compile(r"\s+ft\.?\s+", re.IGNORECASE)
_FEATURED_SPLIT = re.compile(r"\s*(?:,|&|\band\b)\s*", re.IGNORECASE)


def _credits(artist: str) -> List[str]:
    """Credited names of an artist field: "Nujabes ft. Cise Starr & Akin" -> Nujabes, Cise Starr, Akin."""
    parts = _FEATURED.split(artist, maxsplit=1)
    names = [parts[0].strip()]
    if len(parts) == 2:
        names += [name.strip() for name in _FEATURED_SPLIT.split(parts[1]) if name.strip()]
    return names


def _reason_points(fact: Dict[str, Any]) -> List[float]:
    values = []
    for reason in fact.get("reasons", []):
        values += [float(v) for v in re.findall(r"\(\+(\d+(?:\.\d+)?)\)", reason)]
    return values


def check_explanation(
    why: Any, fact: Dict[str, Any], prefs: MoodPreferences, catalog: Sequence[Dict]
) -> Optional[str]:
    """Return a description of the first problem found, or None if the text is trustworthy."""
    if not isinstance(why, str) or not why.strip():
        return "empty explanation"
    if len(why) > MAX_WHY_CHARS:
        return "explanation too long"

    why = _normalize(why)
    own_title, own_artist = fact["title"], fact["artist"]
    own_credits = {name.lower() for name in _credits(own_artist)} | {own_artist.lower()}
    vocab = catalog_vocabulary(list(catalog))

    # Other songs or artists from the catalog. A credited name that is also credited on THIS song (the
    # primary artist or a featured artist) is not "another artist"; a featured artist on the wrong song is.
    for other in catalog:
        if other["id"] == fact["song_id"]:
            continue
        if other["title"] != own_title and _word_in(_normalize(other["title"]), why, ignore_case=False,
                                                    join_hyphen=True):
            return f"mentions another song: {other['title']!r}"
        for name in {other["artist"], *_credits(other["artist"])}:
            if name.lower() in own_credits:
                continue
            if _word_in(name, why, ignore_case=True):
                return f"mentions another artist: {name!r}"

    # Quoted titles/names and "by <Name>" credits must be this song's own.
    short_title = re.sub(r"\s*\([^)]*\)\s*$", "", own_title).lower()      # "Moonlight Sonata (1st Movement)"
    allowed_names = {own_title.lower(), short_title, own_artist.lower(), *own_credits,
                     *(g.lower() for g in vocab.genres), *(m.lower() for m in vocab.moods)}
    for match in _QUOTED.finditer(why):
        quoted = (match.group(1) or match.group(2)).strip().lower()
        if quoted not in allowed_names:
            return f"quotes an unknown title or name: {quoted!r}"
    for match in _BY_NAME.finditer(why):
        credited = match.group(1).strip().rstrip(".,;:!?").lower()       # "by Paper Lanterns." ends a sentence
        if credited not in own_artist.lower():
            return f"credits an unknown artist: {match.group(1)!r}"

    # Metadata we do not have.
    if _YEAR.search(why):
        return "mentions a year (no release data)"
    unsupported = _UNSUPPORTED_WORDS.search(why)
    if unsupported:
        return f"mentions unsupported detail: {unsupported.group(0)!r}"

    # A different genre than this song's.
    own_genre = fact["genre"].lower()
    for genre in vocab.genres:
        low = genre.lower()
        if low != own_genre and low not in own_genre and _word_in(genre, why, ignore_case=True):
            return f"names a different genre: {genre!r}"

    # False score claims.
    score = fact["score"]
    claimed = [float(m.group(1)) for pattern in _SCORE_CLAIMS for m in pattern.finditer(why)]
    claimed_points = [float(m.group(1)) for m in _POINTS_CLAIM.finditer(why)]
    for value in claimed:
        if abs(value - score) > SCORE_TOLERANCE:
            return f"false score claim: {value:g} (actual {score:.2f})"
    allowed_points = _reason_points(fact) + [score]
    for value in claimed_points:
        if not any(abs(value - ok) <= SCORE_TOLERANCE for ok in allowed_points):
            return f"false points claim: {value:g}"
    for match in _PERCENT_CLAIM.finditer(why):
        if abs(float(match.group(1)) - score / 4 * 100) > 1.5:
            return f"false match percentage: {match.group(1)}%"
    if _PERFECT_CLAIM.search(why) and score < 3.95:
        return f"claims a perfect score but the score is {score:.2f}"

    # Wrong feature values and tempo.
    for match in _FEATURE_CLAIM.finditer(why):
        value = float(match.group(2))
        if value > 1.0:
            continue
        name = match.group(1).lower()
        allowed = [fact[name]]
        target = getattr(prefs, f"target_{name}", None)
        if target is not None:
            allowed.append(target)
        if not any(abs(value - ok) <= FEATURE_TOLERANCE for ok in allowed):
            return f"wrong {name} value: {value:g}"
    for match in _BPM_CLAIM.finditer(why):
        if abs(int(match.group(1)) - fact["tempo_bpm"]) > 1:
            return f"wrong tempo: {match.group(1)} bpm"

    return None


def validate_explanations(
    items: Sequence[Any],
    facts: Dict[str, Any],
    prefs: MoodPreferences,
    catalog: Sequence[Dict],
) -> CheckedExplanations:
    """Keep only explanations that pass every check; record why the rest were dropped."""
    by_id = {fact["song_id"]: fact for fact in facts["songs"]}
    result = CheckedExplanations()
    seen: set = set()
    duplicated: set = set()

    for item in items:
        song_id = item.get("song_id") if isinstance(item, dict) else None
        if isinstance(song_id, bool) or not isinstance(song_id, int) or song_id not in by_id:
            result.problems.append(f"invalid song id: {song_id!r}")
            continue
        if song_id in seen:
            duplicated.add(song_id)
            continue
        seen.add(song_id)
        problem = check_explanation(item.get("why"), by_id[song_id], prefs, catalog)
        if problem:
            result.problems.append(f"song {song_id}: {problem}")
        else:
            result.trusted[song_id] = item["why"].strip()

    for song_id in duplicated:
        result.trusted.pop(song_id, None)
        result.problems.append(f"song {song_id}: duplicate explanation")
    return result


def format_interpretation(
    request_text: str, prefs: MoodPreferences, strategy: str, model: Optional[str] = None
) -> str:
    """Plain-text 'how I read your request' panel, shown before any recommendation."""
    def value(number: Optional[float]) -> str:
        return "not set (skipped)" if number is None else f"{number:.2f}"

    lines = [
        "AI-generated interpretation of your request (please check it):",
        f"  Your request:  {request_text}",
        f"  Genres:        {', '.join(prefs.genres) if prefs.genres else 'none'}",
        f"  Moods:         {', '.join(prefs.moods) if prefs.moods else 'none'}",
        f"  Energy:        {value(prefs.target_energy)}",
        f"  Valence:       {value(prefs.target_valence)}",
        f"  Acousticness:  {value(prefs.target_acousticness)}",
        f"  Ranking mode:  {strategy}" + (f"   (model: {model})" if model else ""),
    ]
    if prefs.warnings:
        lines.append("  Adjustments made while checking the AI's answer:")
        lines += [f"    - {warning}" for warning in prefs.warnings]
    return "\n".join(lines)
