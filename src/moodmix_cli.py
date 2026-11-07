"""
MoodMix AI command line.

Run from the repository root:

    python -m src.moodmix_cli "I'm studying for finals"            # real Gemini (needs GEMINI_API_KEY)
    python -m src.moodmix_cli --mock "I need motivation to work out"   # offline demo, no API call
    python -m src.moodmix_cli --genre lofi --mood chill --energy 0.3   # manual only: no API, no key
    python -m src.moodmix_cli "studying" --genre lofi --energy 0.3     # Gemini, manual fallback if it fails

This is separate from src/main.py, which still runs the original Module 3 simulation.
"""

import argparse
import sys
from pathlib import Path

from src.fallback import ManualPreferences
from src.llm import GeminiClient
from src.mock_llm import MockGemini
from src.pipeline import RecommendationResult, recommend_from_manual, recommend_from_text
from src.reliability_log import configure_reliability_log
from src.recommender import DEFAULT_STRATEGY, STRATEGIES, load_songs

SONGS_CSV = Path(__file__).resolve().parent.parent / "data" / "songs.csv"
WIDTH = 64
MAX_SCORE = 4.0


def render(result: RecommendationResult) -> str:
    """Format a pipeline result as text, always showing the engine's scoring reasons."""
    if not result.ok:
        return f"Could not make recommendations ({result.error_kind}): {result.error}"

    lines = [result.interpretation]
    if result.warnings:
        lines += ["", "Notes about your request:"] + [f"  - {note}" for note in result.warnings]
    lines += ["", "=" * WIDTH,
             f" Top {len(result.recommendations)} recommendations", "=" * WIDTH]
    for rec in result.recommendations:
        lines.append(f"\n{rec.rank}. {rec.song['title']}  by {rec.song['artist']}")
        lines.append(f"   Score: {rec.score:.2f} / {MAX_SCORE:.2f}")
        if rec.ai_explanation:
            lines.append(f"   AI says: {rec.ai_explanation}")
        lines.append("   Engine reasons:")
        lines += [f"     - {reason}" for reason in rec.reasons]
    if result.explanation_note:
        lines += ["", f"Note: {result.explanation_note}"]
    return "\n".join(lines)


def _score(value):
    """argparse type for 0-1 numbers; out-of-range values are clamped later with a warning."""
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MoodMix AI: describe what you want to hear")
    parser.add_argument("text", nargs="?", default=None,
                        help="your mood, activity or situation, in your own words "
                             "(omit it to use only the manual preference flags)")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=list(STRATEGIES))
    parser.add_argument("-k", type=int, default=5, help="number of songs (default: 5)")
    parser.add_argument("--mock", action="store_true",
                        help="use the offline mock instead of calling Gemini (no API key needed)")
    manual = parser.add_argument_group(
        "manual preferences",
        "Used alone: no Gemini call. Used with text: the fallback if Gemini fails.")
    manual.add_argument("--genre", action="append", default=[], metavar="GENRE",
                        help="a genre from the catalog (repeatable)")
    manual.add_argument("--mood", action="append", default=[], metavar="MOOD",
                        help="a mood from the catalog (repeatable)")
    manual.add_argument("--energy", type=_score, help="target energy, 0 to 1")
    manual.add_argument("--valence", type=_score, help="target positivity, 0 to 1")
    manual.add_argument("--acousticness", type=_score, help="target acousticness, 0 to 1")
    parser.add_argument("--log-file", metavar="PATH",
                        help="append reliability events (no user text, no keys) to this file")
    args = parser.parse_args(argv)

    configure_reliability_log(args.log_file)
    prefs = ManualPreferences(genres=args.genre, moods=args.mood, energy=args.energy,
                              valence=args.valence, acousticness=args.acousticness)
    songs = load_songs(str(SONGS_CSV))

    if args.text is None:
        if not prefs.has_any():
            parser.error("give a description in quotes and/or manual flags (--genre, --mood, --energy, ...)")
        result = recommend_from_manual(prefs, songs, k=args.k, strategy=args.strategy)
    else:
        if args.mock:
            print("[MOCK Gemini: canned answers, no API call]\n")
            client = GeminiClient(client=MockGemini(), model="mock")
        else:
            client = GeminiClient()   # reads GEMINI_API_KEY lazily; never printed
        result = recommend_from_text(
            args.text, songs, client=client, k=args.k, strategy=args.strategy,
            manual=prefs if prefs.has_any() else None,
        )
    print(render(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
