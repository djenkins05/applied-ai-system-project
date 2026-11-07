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
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.fallback import (
    FALLBACKABLE_KINDS,
    ManualPreferences,
    format_manual_summary,
    manual_to_preferences,
    options_hint,
)
from src.guardrails import friendly_warnings, screen_ai_text, screen_input
from src.reliability_log import log_event
from src.explain import build_facts, format_interpretation, validate_explanations
from src.llm import (
    InputError,
    LLMAuthError,
    LLMBadRequestError,
    LLMError,
    LLMModelNotFoundError,
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
    (LLMBadRequestError, "bad_request",
     "Gemini rejected the request as invalid (HTTP 400). See the diagnostic line below."),
    (LLMModelNotFoundError, "model_not_found",
     "The Gemini model was not found (HTTP 404). Check GEMINI_MODEL."),
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
    # Phase 3 additions (all defaulted, so existing callers are unaffected):
    warnings: List[str] = field(default_factory=list)   # plain-language notes for the user
    source: str = "gemini"                  # "gemini" or "manual": where the preferences came from
    used_fallback: bool = False             # True if manual prefs replaced a failed Gemini call
    fallback_reason: Optional[str] = None
    fallback_available: bool = False        # True on failure: manual preferences can still work
    guardrail_flags: List[str] = field(default_factory=list)   # categories only, never text


def _failure(error: Exception) -> tuple:
    for exc_type, kind, message in _FAILURES:
        if isinstance(error, exc_type):
            return kind, message or str(error)
    raise error


FALLBACK_HINT = "You can still get recommendations by entering your preferences manually."


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _failed(request: str, strategy: str, kind: str, message: str, *,
            fallback_available: bool = True, flags: Optional[List[str]] = None) -> RecommendationResult:
    if fallback_available:
        message = f"{message}\n  {FALLBACK_HINT}"
    return RecommendationResult(
        ok=False, request=request, strategy=strategy, error_kind=kind, error=message,
        fallback_available=fallback_available, guardrail_flags=flags or [],
    )


def _screen_ai_items(items: List[Any]) -> tuple:
    """Drop explanation items whose text carries links, markup or instructions."""
    kept, dropped = [], 0
    for item in items:
        why = item.get("why") if isinstance(item, dict) else None
        if isinstance(item, dict) and why is not None and screen_ai_text(why):
            dropped += 1
        else:
            kept.append(item)
    return kept, dropped


def recommend_from_preferences(
    prefs: MoodPreferences,
    songs: List[Dict],
    *,
    request: str = "",
    client: Any = None,
    k: int = 5,
    strategy: str = DEFAULT_STRATEGY,
    explain: bool = True,
    source: str = "gemini",
    fallback_reason: Optional[str] = None,
    explanation_note: Optional[str] = None,
) -> RecommendationResult:
    """
    Validated preferences -> engine-ranked recommendations (the unchanged Module 3 engine).

    Shared by the text path and the manual path; the Phase 4 UI can call it directly when the
    user edits preferences. Gemini explanations are requested only if `explain` is True.
    """
    gemini = as_client(client) if explain else None
    ranked = recommend_songs(to_user_prefs(prefs), songs, k, strategy)
    recommendations = [
        RecommendedSong(rank=i, song=song, score=score, reasons=explanation.split("; "))
        for i, (song, score, explanation) in enumerate(ranked, start=1)
    ]

    note = explanation_note
    if explain and ranked:
        try:
            facts = build_facts(ranked)
            items = request_explanations(request, facts, gemini)
            items, unsafe = _screen_ai_items(items)
            checked = validate_explanations(items, facts, prefs, songs)
            for rec in recommendations:
                rec.ai_explanation = checked.trusted.get(rec.song["id"])
            dropped = unsafe + len(checked.problems)
            if dropped:
                log_event("explanations_dropped", dropped_explanations=dropped, source=source)
                note = "Some AI explanations were not trusted and were replaced by the engine's reasons."
        except Exception as error:  # noqa: BLE001 - optional step must never block recommendations
            logger.warning("AI explanations unavailable: %s", type(error).__name__)
            log_event("explanations_unavailable", error_kind=type(error).__name__, source=source)
            note = "AI explanations are unavailable right now; showing the engine's scoring reasons."

    if source == "manual":
        interpretation = format_manual_summary(prefs, strategy, fallback_reason)
    else:
        interpretation = format_interpretation(request, prefs, strategy, getattr(gemini, "model", None))
    return RecommendationResult(
        ok=True,
        request=request,
        strategy=strategy,
        prefs=prefs,
        interpretation=interpretation,
        recommendations=recommendations,
        explanation_note=note,
        warnings=friendly_warnings(prefs),
        source=source,
        used_fallback=fallback_reason is not None,
        fallback_reason=fallback_reason,
    )


def recommend_from_manual(
    manual: ManualPreferences,
    songs: List[Dict],
    *,
    k: int = 5,
    strategy: str = DEFAULT_STRATEGY,
) -> RecommendationResult:
    """Manual-only mode: validated user preferences -> recommendations. Makes no Gemini call."""
    if strategy not in STRATEGIES:
        return _failed("", strategy, "input",
                       f"Unknown ranking mode {strategy!r}. Choose from: {', '.join(STRATEGIES)}.",
                       fallback_available=False)
    vocab = catalog_vocabulary(songs)
    try:
        prefs = manual_to_preferences(manual, vocab)
    except PreferenceError:
        has_any = manual.has_any()
        message = ("I couldn't use those preferences: none of the genres or moods are in this "
                   f"catalog. {options_hint(vocab)}" if has_any
                   else f"No preferences were entered. {options_hint(vocab)}")
        log_event("manual_rejected", error_kind="invalid_manual", source="manual")
        return _failed("", strategy, "invalid_manual", message, fallback_available=False)
    log_event("manual_request", source="manual")
    return recommend_from_preferences(
        prefs, songs, k=k, strategy=strategy, explain=False, source="manual",
        explanation_note="Manual mode: showing the engine's scoring reasons (no AI explanations).",
    )


def recommend_from_text(
    text: str,
    songs: List[Dict],
    *,
    client: Any = None,
    k: int = 5,
    strategy: str = DEFAULT_STRATEGY,
    explain: bool = True,
    manual: Optional[ManualPreferences] = None,
) -> RecommendationResult:
    """
    Natural-language request -> engine-ranked recommendations with transparent explanations.

    Input is screened first (empty/oversized/gibberish/prompt-injection are rejected before any
    Gemini call). If Gemini fails and usable `manual` preferences were supplied, they are used and
    the result says so (`used_fallback`). Without them, the failure result has
    `fallback_available=True`; nothing is ever generated from silent defaults.
    """
    request = text if isinstance(text, str) else ""
    if strategy not in STRATEGIES:
        return _failed(request, strategy, "input",
                       f"Unknown ranking mode {strategy!r}. Choose from: {', '.join(STRATEGIES)}.",
                       fallback_available=False)

    started = time.monotonic()
    screen = screen_input(text)
    if not screen.ok:
        log_event("input_rejected", error_kind="input", guardrail=screen.category,
                  input_chars=len(request), latency_ms=_elapsed_ms(started))
        return _failed(request, strategy, "input", screen.message, flags=screen.flags)
    request = screen.cleaned

    gemini = as_client(client)
    vocab = catalog_vocabulary(songs)
    try:
        prefs = interpret_preferences(request, vocab, gemini)
    except (InputError, LLMError, PreferenceError) as error:
        kind, message = _failure(error)
        diagnostic = getattr(error, "diagnostic", "")
        logger.warning("MoodMix request failed: %s (%s)%s", kind, type(error).__name__,
                       f" [{diagnostic}]" if diagnostic else "")
        if diagnostic:
            message = f"{message}\n  Diagnostic: {diagnostic}"

        used_manual = manual is not None and manual.has_any() and kind in FALLBACKABLE_KINDS
        log_event("llm_failure", error_kind=kind, status_code=getattr(error, "status_code", None),
                  api_status=getattr(error, "api_status", None), model=getattr(gemini, "model", None),
                  latency_ms=_elapsed_ms(started), input_chars=len(request), used_fallback=used_manual)
        if used_manual:
            try:
                fallback_prefs = manual_to_preferences(manual, vocab)
            except PreferenceError:
                return _failed(request, strategy, kind,
                               f"{message}\n  Your manual preferences could not be used either "
                               f"(no known genres or moods). {options_hint(vocab)}")
            return recommend_from_preferences(
                fallback_prefs, songs, request=request, client=gemini, k=k, strategy=strategy,
                explain=False, source="manual", fallback_reason=message.split("\n")[0],
                explanation_note="Gemini was unavailable, so AI explanations are off; "
                                 "showing the engine's scoring reasons.",
            )
        return _failed(request, strategy, kind, message)

    log_event("request_ok", model=getattr(gemini, "model", None), latency_ms=_elapsed_ms(started),
              input_chars=len(request), source="gemini", used_fallback=False)
    return recommend_from_preferences(
        prefs, songs, request=request, client=gemini, k=k, strategy=strategy, explain=explain,
    )
