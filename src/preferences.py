"""
Structured preference layer for MoodMix AI.

Sits between untrusted input (e.g. a Gemini response) and the Module 3 recommender:

    raw response -> parse_preferences() -> MoodPreferences -> to_user_prefs() -> recommend_songs()

This module never imports or changes the recommender. It only produces the plain
dict that score_song / recommend_songs already accept.
"""

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

MAX_LABELS = 5            # most genres (and most moods) kept from one response
DEFAULT_ENERGY = 0.5      # neutral target used only when other usable preferences exist
TARGET_FIELDS = ("target_energy", "target_valence", "target_acousticness")
KNOWN_KEYS = {"genres", "moods", *TARGET_FIELDS}

# JSON Schema describing the response we want. NOTE: not yet verified against the
# Gemini SDK's structured-output format; confirm and adapt it in Phase 2.
PREFERENCE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "genres": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_LABELS},
        "moods": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_LABELS},
        "target_energy": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "target_valence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "target_acousticness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


class PreferenceError(ValueError):
    """Raised when a response is malformed or contains no usable preference."""


class Vocabulary(NamedTuple):
    """The genres and moods that exist in the song catalog."""
    genres: Tuple[str, ...]
    moods: Tuple[str, ...]


@dataclass
class MoodPreferences:
    """Validated preferences. Targets are in [0, 1]; valence/acousticness may be None (skipped)."""
    genres: List[str] = field(default_factory=list)
    moods: List[str] = field(default_factory=list)
    target_energy: float = DEFAULT_ENERGY
    target_valence: Optional[float] = None
    target_acousticness: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


def catalog_vocabulary(songs: List[Dict]) -> Vocabulary:
    """Collect the genres and moods present in the loaded songs (so it tracks the CSV)."""
    return Vocabulary(
        genres=tuple(sorted({song["genre"] for song in songs})),
        moods=tuple(sorted({song["mood"] for song in songs})),
    )


def _load_object(raw: Union[str, Dict, None]) -> Dict[str, Any]:
    """Turn a dict or JSON string (optionally in ``` fences) into a dict, or raise."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise PreferenceError("malformed response: expected a JSON object")

    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise PreferenceError(f"malformed response: invalid JSON ({error.msg})") from error
    if not isinstance(data, dict):
        raise PreferenceError("malformed response: JSON is not an object")
    return data


def _clean_labels(
    value: Any, canonical: Dict[str, str], kind: str, warnings: List[str]
) -> List[str]:
    """Validate a genre/mood list: canonicalize case, drop unknowns, dedupe, cap length."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        warnings.append(f"ignored {kind}: expected a list of strings")
        return []

    cleaned: List[str] = []
    for item in value:
        if not isinstance(item, str):
            warnings.append(f"dropped non-text {kind} entry: {item!r}")
            continue
        match = canonical.get(item.strip().lower())
        if match is None:
            warnings.append(f"dropped unknown {kind[:-1]}: {item.strip()!r}")
        elif match not in cleaned:
            cleaned.append(match)

    if len(cleaned) > MAX_LABELS:
        warnings.append(f"kept the first {MAX_LABELS} {kind}")
        cleaned = cleaned[:MAX_LABELS]
    return cleaned


def _clean_number(value: Any, name: str, warnings: List[str]) -> Optional[float]:
    """Return a float clamped to [0, 1], or None if the value is absent or unusable."""
    if value is None:
        return None
    if isinstance(value, bool):
        warnings.append(f"ignored {name}: {value!r} is not a number")
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            warnings.append(f"ignored {name}: {value!r} is not a number")
            return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        warnings.append(f"ignored {name}: {value!r} is not a finite number")
        return None

    number = float(value)
    clamped = min(1.0, max(0.0, number))
    if clamped != number:
        warnings.append(f"clamped {name} from {number:g} to {clamped:g}")
    return clamped


def parse_preferences(raw: Union[str, Dict, None], vocab: Vocabulary) -> MoodPreferences:
    """
    Validate a raw response into MoodPreferences, or raise PreferenceError.

    The response must contain at least one usable preference (a known genre, a known
    mood, or a valid numeric target) *before* any default is applied, so a response
    like {} fails instead of succeeding on a defaulted energy.
    """
    data = _load_object(raw)
    warnings: List[str] = []

    extra = sorted(str(key) for key in data if key not in KNOWN_KEYS)
    if extra:
        warnings.append(f"ignored unknown keys: {', '.join(extra)}")

    genre_lookup = {g.lower(): g for g in vocab.genres}
    mood_lookup = {m.lower(): m for m in vocab.moods}
    genres = _clean_labels(data.get("genres"), genre_lookup, "genres", warnings)
    moods = _clean_labels(data.get("moods"), mood_lookup, "moods", warnings)
    energy, valence, acousticness = (
        _clean_number(data.get(name), name, warnings) for name in TARGET_FIELDS
    )

    # Usability check happens on what the response actually said, before defaults.
    if not (genres or moods or any(n is not None for n in (energy, valence, acousticness))):
        detail = f" ({'; '.join(warnings)})" if warnings else ""
        raise PreferenceError("could not understand preferences: nothing usable" + detail)

    if energy is None:
        energy = DEFAULT_ENERGY
        warnings.append(f"target_energy missing; using neutral default {DEFAULT_ENERGY}")

    return MoodPreferences(
        genres=genres,
        moods=moods,
        target_energy=energy,
        target_valence=valence,
        target_acousticness=acousticness,
        warnings=warnings,
    )


def to_user_prefs(prefs: MoodPreferences) -> Dict[str, Any]:
    """
    Build the dict score_song / recommend_songs accept, without changing them.

    - Empty genre/mood sets would hit the engine's single-value fallback and raise
      KeyError, so the fallback keys are always supplied as "" (matches no song).
    - Valence/acousticness targets that are None are omitted, so the engine skips
      them and rescales the remaining weights.
    """
    user_prefs: Dict[str, Any] = {
        "favorite_genres": set(prefs.genres),
        "favorite_moods": set(prefs.moods),
        "favorite_genre": "",
        "favorite_mood": "",
        "target_energy": prefs.target_energy,
    }
    if prefs.target_valence is not None:
        user_prefs["target_valence"] = prefs.target_valence
    if prefs.target_acousticness is not None:
        user_prefs["target_acousticness"] = prefs.target_acousticness
    return user_prefs
