"""
Like/dislike feedback for MoodMix AI.

Feedback never retrains Gemini and never touches the recommender's scoring. It only changes the
*preferences passed into* the unchanged rule-based engine (and which songs are candidates):

    base preferences + feedback log ──adjust_preferences──► adjusted preferences ──► engine

The base preferences (what the user stated or edited) are never modified, so resetting feedback
restores the original behaviour and candidate pool exactly.

Rules (all constants below):
  - Genre / mood labels have a weight. A label in the base preferences starts at LABEL_BASE_WEIGHT,
    every like of a song with that label adds LIKE_LABEL_DELTA, every dislike adds DISLIKE_LABEL_DELTA.
    A label is used while its weight is above zero (capped at MAX_LABELS). So one like adds a new
    label, one dislike does not remove a label the user chose, and two dislikes do.
  - Energy (and valence / acousticness, only if the user already set them) move toward a liked song's
    value by LIKE_STEP and away from a disliked song's value by DISLIKE_STEP, replayed in the order
    the votes were made, clamped to [0, 1]. Unset targets stay unset: feedback never invents one.
  - Disliked songs are excluded from the candidate list for the current session.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.pipeline import RecommendationResult, recommend_from_preferences
from src.preferences import MAX_LABELS, MoodPreferences, to_user_prefs
from src.recommender import DEFAULT_STRATEGY, recommend_songs

LIKE = 1
DISLIKE = -1

LABEL_BASE_WEIGHT = 2
LIKE_LABEL_DELTA = 1
DISLIKE_LABEL_DELTA = -1
LIKE_STEP = 0.30
DISLIKE_STEP = 0.15
TARGET_FEATURES = ("energy", "valence", "acousticness")

HOW_FEEDBACK_WORKS = (
    "Likes and dislikes do not retrain Gemini or change the scoring rules. They adjust the "
    "preferences (genres, moods, energy, ...) that are passed to the rule-based recommender, and "
    "disliked songs are left out for this session. The engine's scoring reasons stay exactly as "
    "the engine computed them."
)


@dataclass
class FeedbackLog:
    """Chronological votes for the current session: song id -> LIKE or DISLIKE."""
    votes: Dict[int, int] = field(default_factory=dict)

    def set(self, song_id: int, vote: int) -> None:
        if vote not in (LIKE, DISLIKE):
            raise ValueError("vote must be LIKE (1) or DISLIKE (-1)")
        self.votes.pop(song_id, None)      # a re-vote counts as the most recent action
        self.votes[song_id] = vote

    def clear(self, song_id: int) -> None:
        self.votes.pop(song_id, None)

    def reset(self) -> None:
        self.votes.clear()

    def get(self, song_id: int) -> Optional[int]:
        return self.votes.get(song_id)

    @property
    def liked_ids(self) -> List[int]:
        return [i for i, v in self.votes.items() if v == LIKE]

    @property
    def disliked_ids(self) -> List[int]:
        return [i for i, v in self.votes.items() if v == DISLIKE]

    def __len__(self) -> int:
        return len(self.votes)


@dataclass
class AdjustedPreferences:
    prefs: MoodPreferences
    notes: List[str] = field(default_factory=list)   # plain-language "what feedback changed"


def _titles(names: List[str]) -> str:
    return ", ".join(names)


def _adjust_labels(base_labels: List[str], kind: str, votes: List[tuple], notes: List[str]) -> List[str]:
    """votes: (order, vote, label, title) for this label kind (genre or mood)."""
    weight: Dict[str, int] = {label: LABEL_BASE_WEIGHT for label in base_labels}
    touched: Dict[str, int] = {label: -1 for label in base_labels}
    liked_by: Dict[str, List[str]] = {}
    disliked_by: Dict[str, List[str]] = {}
    for order, vote, label, title in votes:
        delta = LIKE_LABEL_DELTA if vote == LIKE else DISLIKE_LABEL_DELTA
        weight[label] = weight.get(label, 0) + delta
        touched[label] = order
        (liked_by if vote == LIKE else disliked_by).setdefault(label, []).append(title)

    kept = sorted((l for l in weight if weight[l] > 0), key=lambda l: (-weight[l], -touched[l]))
    if len(kept) > MAX_LABELS:
        kept = kept[:MAX_LABELS]
    for label in kept:
        if label not in base_labels and label in liked_by:
            notes.append(f"Added {kind} {label} because you liked {_titles(liked_by[label])}.")
    for label in base_labels:
        if label not in kept:
            notes.append(f"Dropped {kind} {label} after you disliked {_titles(disliked_by.get(label, []))}.")
    # Keep base order first for stable display, then newly added labels.
    return [l for l in base_labels if l in kept] + [l for l in kept if l not in base_labels]


def adjust_preferences(
    base: MoodPreferences, log: FeedbackLog, songs: List[Dict[str, Any]]
) -> AdjustedPreferences:
    """Return new preferences reflecting the feedback log. `base` is not modified."""
    by_id = {song["id"]: song for song in songs}
    ordered = [(order, by_id[sid], vote) for order, (sid, vote) in enumerate(log.votes.items())
               if sid in by_id]
    notes: List[str] = []

    genres = _adjust_labels(
        list(base.genres), "genre", [(o, v, s["genre"], s["title"]) for o, s, v in ordered], notes)
    moods = _adjust_labels(
        list(base.moods), "mood", [(o, v, s["mood"], s["title"]) for o, s, v in ordered], notes)

    targets = {
        "energy": base.target_energy,
        "valence": base.target_valence,
        "acousticness": base.target_acousticness,
    }
    current = dict(targets)
    for _, song, vote in ordered:
        for feature in TARGET_FEATURES:
            if current[feature] is None:
                continue                                # never invent an unset preference
            gap = song[feature] - current[feature]
            step = LIKE_STEP * gap if vote == LIKE else -DISLIKE_STEP * gap
            current[feature] = min(1.0, max(0.0, current[feature] + step))
    for feature in TARGET_FEATURES:
        before, after = targets[feature], current[feature]
        if before is not None and abs(after - before) >= 0.005:
            notes.append(f"Moved your {feature} target from {before:.2f} to {after:.2f}.")

    prefs = MoodPreferences(
        genres=genres, moods=moods,
        target_energy=current["energy"],
        target_valence=current["valence"],
        target_acousticness=current["acousticness"],
        warnings=list(base.warnings),
    )
    return AdjustedPreferences(prefs=prefs, notes=notes)


@dataclass
class FeedbackOutcome:
    """Everything the UI needs to show after (re)ranking with feedback."""
    result: RecommendationResult
    adjusted: AdjustedPreferences
    excluded: List[Dict[str, Any]]            # disliked songs left out (newest vote last)
    requested_k: int
    baseline_titles: List[str]                # top picks without any feedback, for comparison
    message: Optional[str] = None             # shown when fewer than k songs remain


def recommend_with_feedback(
    base: MoodPreferences,
    log: FeedbackLog,
    songs: List[Dict[str, Any]],
    *,
    k: int = 5,
    strategy: str = DEFAULT_STRATEGY,
    client: Any = None,
    explain: bool = False,
    request: str = "",
    source: str = "gemini",
) -> FeedbackOutcome:
    """
    Adjust preferences from feedback, drop disliked songs, and rank with the unchanged engine.

    Gemini is contacted only when `explain` is True (and then only to write explanations).
    """
    adjusted = adjust_preferences(base, log, songs)
    disliked = set(log.disliked_ids)
    candidates = [song for song in songs if song["id"] not in disliked]
    excluded = [song for sid in log.disliked_ids for song in songs if song["id"] == sid]

    result = recommend_from_preferences(
        adjusted.prefs, candidates, request=request, client=client, k=k,
        strategy=strategy, explain=explain, source=source,
    )

    baseline_titles = [
        song["title"] for song, _, _ in recommend_songs(to_user_prefs(base), songs, k, strategy)
    ] if len(log) else []

    message = None
    shown = len(result.recommendations)
    if shown < k:
        if excluded:
            message = (f"Only {shown} of the {k} songs you asked for are left: {len(excluded)} disliked "
                       f"song(s) are excluded and the catalog has {len(songs)} songs. "
                       "Undo a dislike or reset feedback to bring them back.")
        else:
            message = f"The catalog only has {len(songs)} songs, so only {shown} can be shown."
    return FeedbackOutcome(result=result, adjusted=adjusted, excluded=excluded, requested_k=k,
                           baseline_titles=baseline_titles, message=message)
