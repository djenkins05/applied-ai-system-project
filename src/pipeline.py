"""
End-to-end MoodMix pipeline:

    text -> Gemini -> parse_preferences -> to_user_prefs -> recommend_songs (unchanged engine)
         -> optional Gemini explanations -> validation -> RecommendationResult

recommend_from_text() does not raise for expected failures; it returns ok=False with an
error_kind the UI can act on. The explanation step is optional: if it fails, times out,
hits a quota or fails validation, recommendations are still returned with the engine's
own scoring reasons (which are always included either way).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.explain import build_facts, format_interpretation, validate_explanations
from src.llm import (
    InputError,
    LLMAuthError,
    LLMError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    MissingAPIKeyError,
    as_client,
    check_input,
    interpret_preferences,
    request_explanations,
)
from src.preferences import MoodPreferences, PreferenceError, catalog_vocabulary, to_user_prefs
from src.recommender import DEFAULT_STRATEGY, STRATEGIES, recommend_songs

logger = logging.getLogger(__name__)

# (exception type, error_kind, user-safe message). Order matters: most specific first.
_FAILURES = (
    (InputError, "input", None),   # message comes from the exception itself
    (MissingAPIKeyError, "no_api_key",
     "No Gemini API key is set. Set GEMINI_API_KEY (see .env.example), or use manual preferences."),
    (LLMAuthError, "auth", "Gemini rejected the API key. Check GEMINI_API_KEY."),
    (LLMTimeoutError, "timeout", "Gemini took too long to respond. Please try again."),
    (LLMUnavailableError, "unavailable",
     "Gemini is unavailable or the quota was reached. Please try again later."),
    (LLMResponseError, "bad_response", "Gemini returned an unusable response. Please try again."),
    (PreferenceError, "invalid_preferences",
     "I couldn't turn that into music preferences. Try describing a mood, activity or situation."),
    (LLMError, "llm_error", "The Gemini request failed. Please try again."),
)


@dataclass
class RecommendedSong:
    rank: int
    song: Dict[str, Any]
    score: float
    reasons: List[str]                      # the engine's scoring reasons (always present)
    ai_explanation: Optional[str] = None    # validated Gemini sentence, if any

    @property
    def explanation_source(self) -> str:
        return "ai" if self.ai_explanation else "engine"


@dataclass
class RecommendationResult:
    ok: bool
    request: str = ""
    strategy: str = DEFAULT_STRATEGY
    prefs: Optional[MoodPreferences] = None
    interpretation: str = ""                # transparency text, see format_interpretation
    recommendations: List[RecommendedSong] = field(default_factory=list)
    explanation_note: Optional[str] = None  # why AI explanations are missing, if they are
    error_kind: Optional[str] = None
    error: Optional[str] = None


def _failure(error: Exception) -> tuple:
    for exc_type, kind, message in _FAILURES:
        if isinstance(error, exc_type):
            return kind, message or str(error)
    raise error


def recommend_from_text(
    text: str,
    songs: List[Dict],
    *,
    client: Any = None,
    k: int = 5,
    strategy: str = DEFAULT_STRATEGY,
    explain: bool = True,
) -> RecommendationResult:
    """Natural-language request -> engine-ranked recommendations with transparent explanations."""
    request = text if isinstance(text, str) else ""
    if strategy not in STRATEGIES:
        return RecommendationResult(
            ok=False, request=request, strategy=strategy, error_kind="input",
            error=f"Unknown ranking mode {strategy!r}. Choose from: {', '.join(STRATEGIES)}.",
        )

    gemini = as_client(client)
    try:
        request = check_input(text)
        prefs = interpret_preferences(request, catalog_vocabulary(songs), gemini)
    except (InputError, LLMError, PreferenceError) as error:
        kind, message = _failure(error)
        logger.warning("MoodMix request failed: %s (%s)", kind, type(error).__name__)
        return RecommendationResult(
            ok=False, request=request, strategy=strategy, error_kind=kind, error=message
        )

    # The unchanged Module 3 engine decides the ranking.
    ranked = recommend_songs(to_user_prefs(prefs), songs, k, strategy)
    recommendations = [
        RecommendedSong(rank=i, song=song, score=score, reasons=explanation.split("; "))
        for i, (song, score, explanation) in enumerate(ranked, start=1)
    ]

    note = None
    if explain and ranked:
        try:
            facts = build_facts(ranked)
            items = request_explanations(request, facts, gemini)
            checked = validate_explanations(items, facts, prefs, songs)
            for rec in recommendations:
                rec.ai_explanation = checked.trusted.get(rec.song["id"])
            if checked.problems:
                logger.warning("Dropped %d AI explanation(s): %s", len(checked.problems), checked.problems)
                note = "Some AI explanations were not trusted and were replaced by the engine's reasons."
        except Exception as error:  # noqa: BLE001 - optional step must never block recommendations
            logger.warning("AI explanations unavailable: %s", type(error).__name__)
            note = "AI explanations are unavailable right now; showing the engine's scoring reasons."

    return RecommendationResult(
        ok=True,
        request=request,
        strategy=strategy,
        prefs=prefs,
        interpretation=format_interpretation(request, prefs, strategy, getattr(gemini, "model", None)),
        recommendations=recommendations,
        explanation_note=note,
    )
