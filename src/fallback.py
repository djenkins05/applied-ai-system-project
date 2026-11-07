"""
Manual-preference fallback for MoodMix AI.

When Gemini is unavailable, times out, or rejects a request, the user can still get recommendations
by entering preferences directly. The fallback is EXPLICIT: it only runs when usable manual
preferences were supplied. If none were, the caller returns a friendly error with
`fallback_available=True` and never invents defaults on the user's behalf.

Manual input goes through the same validation as Gemini output (parse_preferences), so labels
are canonicalized, unknown ones are dropped with a warning, and numbers are clamped to 0-1.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

from src.preferences import MoodPreferences, PreferenceError, Vocabulary, parse_preferences

# Pipeline error kinds for which the manual fallback is offered (see src/pipeline.py _FAILURES).
FALLBACKABLE_KINDS: FrozenSet[str] = frozenset({
    "no_api_key", "auth", "bad_request", "model_not_found", "unavailable", "timeout",
    "bad_response", "invalid_preferences", "llm_error", "input",
})


@dataclass
class ManualPreferences:
    """Preferences typed or selected by the user. Every field is optional."""
    genres: List[str] = field(default_factory=list)
    moods: List[str] = field(default_factory=list)
    energy: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None

    def has_any(self) -> bool:
        """True if the user supplied anything at all (it may still turn out to be unusable)."""
        return bool(self.genres or self.moods or any(
            value is not None for value in (self.energy, self.valence, self.acousticness)))


def manual_to_preferences(manual: ManualPreferences, vocab: Vocabulary) -> MoodPreferences:
    """
    Validate manual input into MoodPreferences, or raise PreferenceError if nothing is usable
    (for example only unknown genres were given). Never substitutes defaults for empty input.
    """
    if not manual.has_any():
        raise PreferenceError("no manual preferences were given")
    data: Dict[str, object] = {}
    if manual.genres:
        data["genres"] = list(manual.genres)
    if manual.moods:
        data["moods"] = list(manual.moods)
    for key, value in (("target_energy", manual.energy), ("target_valence", manual.valence),
                       ("target_acousticness", manual.acousticness)):
        if value is not None:
            data[key] = value
    return parse_preferences(data, vocab)


def available_options(vocab: Vocabulary) -> Dict[str, List[str]]:
    """Genres and moods the catalog supports, for building a manual form (Phase 4 UI)."""
    return {"genres": list(vocab.genres), "moods": list(vocab.moods)}


def options_hint(vocab: Vocabulary) -> str:
    """One-paragraph list of valid labels, for error messages."""
    return (f"Available genres: {', '.join(vocab.genres)}. "
            f"Available moods: {', '.join(vocab.moods)}.")


def format_manual_summary(prefs: MoodPreferences, strategy: str, reason: Optional[str] = None) -> str:
    """Transparency panel for manual (non-AI) preferences."""
    def value(number: Optional[float]) -> str:
        return "not set (skipped)" if number is None else f"{number:.2f}"

    lines = []
    if reason:
        lines.append(f"Using your manual preferences because Gemini could not be used ({reason}).")
    lines += [
        "Manual preferences (not AI-interpreted):",
        f"  Genres:        {', '.join(prefs.genres) if prefs.genres else 'none'}",
        f"  Moods:         {', '.join(prefs.moods) if prefs.moods else 'none'}",
        f"  Energy:        {value(prefs.target_energy)}",
        f"  Valence:       {value(prefs.target_valence)}",
        f"  Acousticness:  {value(prefs.target_acousticness)}",
        f"  Ranking mode:  {strategy}",
    ]
    return "\n".join(lines)
