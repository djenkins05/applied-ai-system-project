"""
UI-independent application logic for the MoodMix Streamlit app (no Streamlit import here).

`app.py` keeps one `AppState` in `st.session_state` and calls these functions; tests drive the same
functions directly. Rules this module guarantees:

  - Gemini is contacted only by `submit_text` (one interpretation, plus optional explanations) and
    `request_explanations` (explicit). Voting, undoing, resetting feedback, editing preferences and
    changing the ranking mode or song count re-rank offline with the rule-based engine.
  - A failed or rejected request never erases the user's draft text, edited preferences, current
    recommendations or feedback. Only a *successful* new text request resets feedback.
  - The manual fallback is never automatic; the user chooses it (`switch_mode`).
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.fallback import ManualPreferences, available_options, manual_to_preferences
from src.feedback import DISLIKE, LIKE, FeedbackLog, FeedbackOutcome, recommend_with_feedback
from src.pipeline import RecommendationResult, recommend_from_manual, recommend_from_text
from src.preferences import MoodPreferences, PreferenceError, Vocabulary, catalog_vocabulary
from src.recommender import DEFAULT_STRATEGY, STRATEGIES

MODE_AI = "ai"
MODE_MANUAL = "manual"
ORIGIN_AI = "ai"          # preferences as Gemini inferred them
ORIGIN_EDITED = "edited"  # Gemini's reading, edited by the user
ORIGIN_MANUAL = "manual"  # entered by the user
MIN_K, MAX_K = 3, 10
DEFAULT_K = 5


@dataclass
class AppState:
    mode: str = MODE_AI
    strategy: str = DEFAULT_STRATEGY
    k: int = DEFAULT_K
    draft_text: str = ""                  # what is typed in the box (kept across reruns)
    request_text: str = ""                # the text last sent to Gemini
    base_prefs: Optional[MoodPreferences] = None
    ai_prefs: Optional[MoodPreferences] = None
    origin: str = ""
    prefs_version: int = 0                # bumped when the edit widgets must reload from base_prefs
    feedback: FeedbackLog = field(default_factory=FeedbackLog)
    outcome: Optional[FeedbackOutcome] = None
    ai_why: Dict[int, str] = field(default_factory=dict)   # validated AI explanations, by song id
    notice: Optional[str] = None
    error: Optional[RecommendationResult] = None


def prefs_to_manual(prefs: MoodPreferences) -> ManualPreferences:
    """Preferences as the edit widgets show them (2-decimal sliders, unset = None)."""
    def r(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)
    return ManualPreferences(
        genres=list(prefs.genres), moods=list(prefs.moods), energy=r(prefs.target_energy),
        valence=r(prefs.target_valence), acousticness=r(prefs.target_acousticness),
    )


class AppController:
    """Holds the catalog; every action takes the AppState (and a client where Gemini is needed)."""

    def __init__(self, songs: List[Dict[str, Any]]):
        self.songs = songs
        self.vocab: Vocabulary = catalog_vocabulary(songs)

    # --- read-only helpers -------------------------------------------------------
    @property
    def options(self) -> Dict[str, List[str]]:
        """Genres and moods straight from the CSV, for the manual controls."""
        return available_options(self.vocab)

    @property
    def max_k(self) -> int:
        return min(MAX_K, len(self.songs))

    # --- internal ------------------------------------------------------------------
    def recompute(self, state: AppState) -> None:
        """Re-rank offline (no Gemini) from base preferences + feedback."""
        if state.base_prefs is None:
            state.outcome = None
            return
        state.outcome = recommend_with_feedback(
            state.base_prefs, state.feedback, self.songs, k=state.k, strategy=state.strategy,
            request=state.request_text,
            source="manual" if state.origin == ORIGIN_MANUAL else "gemini",
        )

    # --- Gemini-backed actions ---------------------------------------------------------
    def submit_text(self, state: AppState, text: str, client: Any, *, explain: bool = True
                    ) -> RecommendationResult:
        """Interpret `text` with Gemini and rank. On failure, previous state is left intact."""
        state.draft_text = text
        result = recommend_from_text(text, self.songs, client=client, k=state.k,
                                     strategy=state.strategy, explain=explain)
        if not result.ok:
            state.error = result
            return result
        state.error = None
        state.request_text = result.request
        state.ai_prefs = copy.deepcopy(result.prefs)
        state.base_prefs = copy.deepcopy(result.prefs)
        state.origin = ORIGIN_AI
        state.prefs_version += 1
        state.feedback.reset()                      # a new request is a new intent
        state.ai_why = {r.song["id"]: r.ai_explanation for r in result.recommendations
                        if r.ai_explanation}
        state.notice = result.explanation_note
        self.recompute(state)
        return result

    def request_explanations(self, state: AppState, client: Any) -> None:
        """Explicitly ask Gemini to explain the current picks (one bounded call)."""
        if state.base_prefs is None or not state.request_text:
            return
        outcome = recommend_with_feedback(
            state.base_prefs, state.feedback, self.songs, k=state.k, strategy=state.strategy,
            client=client, explain=True, request=state.request_text)
        state.ai_why.update({r.song["id"]: r.ai_explanation
                             for r in outcome.result.recommendations if r.ai_explanation})
        state.notice = outcome.result.explanation_note
        state.outcome = outcome

    # --- manual preferences ---------------------------------------------------------------
    def submit_manual(self, state: AppState, manual: ManualPreferences) -> RecommendationResult:
        """First manual request (explicit). Invalid input sets a friendly error, nothing else."""
        result = recommend_from_manual(manual, self.songs, k=state.k, strategy=state.strategy)
        if not result.ok:
            state.error = result
            return result
        state.error = None
        state.base_prefs = copy.deepcopy(result.prefs)
        state.origin = ORIGIN_MANUAL
        state.prefs_version += 1
        state.notice = result.explanation_note
        self.recompute(state)
        return result

    def apply_edit(self, state: AppState, manual: ManualPreferences) -> bool:
        """Apply edited preferences live (offline). Feedback is kept. Returns True if applied."""
        try:
            prefs = manual_to_preferences(manual, self.vocab)
        except PreferenceError:
            return False
        state.base_prefs = prefs
        if state.origin == ORIGIN_AI:
            state.origin = ORIGIN_EDITED
        self.recompute(state)
        return True

    def reset_to_ai(self, state: AppState) -> None:
        """Restore Gemini's original reading of the request (feedback is kept)."""
        if state.ai_prefs is None:
            return
        state.base_prefs = copy.deepcopy(state.ai_prefs)
        state.origin = ORIGIN_AI
        state.prefs_version += 1
        self.recompute(state)

    # --- feedback (all offline) --------------------------------------------------------------
    def vote(self, state: AppState, song_id: int, vote: int) -> None:
        """Like/dislike a song; voting the same way again removes the vote."""
        if state.feedback.get(song_id) == vote:
            state.feedback.clear(song_id)
        else:
            state.feedback.set(song_id, vote)
        self.recompute(state)

    def like(self, state: AppState, song_id: int) -> None:
        self.vote(state, song_id, LIKE)

    def dislike(self, state: AppState, song_id: int) -> None:
        self.vote(state, song_id, DISLIKE)

    def undo(self, state: AppState, song_id: int) -> None:
        """Remove one vote (used by the 'Undo' control for excluded songs)."""
        state.feedback.clear(song_id)
        self.recompute(state)

    def reset_feedback(self, state: AppState) -> None:
        """Clear all votes; the original candidate pool and ranking return immediately."""
        state.feedback.reset()
        self.recompute(state)

    # --- settings (all offline) ---------------------------------------------------------------
    def change_strategy(self, state: AppState, strategy: str) -> None:
        if strategy in STRATEGIES and strategy != state.strategy:
            state.strategy = strategy
            self.recompute(state)

    def set_k(self, state: AppState, k: int) -> None:
        k = max(MIN_K, min(self.max_k, int(k)))
        if k != state.k:
            state.k = k
            self.recompute(state)

    def switch_mode(self, state: AppState, mode: str) -> None:
        """Explicit mode change (also how the user takes the manual fallback). Nothing is erased."""
        if mode in (MODE_AI, MODE_MANUAL):
            state.mode = mode
            if mode == MODE_MANUAL:
                state.error = None

    def reset_all(self, state: AppState) -> None:
        """Back to a blank session (keeps the version counter increasing so widgets reload)."""
        version = state.prefs_version + 1
        fresh = AppState()
        state.__dict__.update(fresh.__dict__)
        state.prefs_version = version
