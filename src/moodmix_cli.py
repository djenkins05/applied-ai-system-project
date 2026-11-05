"""
MoodMix AI command line.

Run from the repository root:

    python -m src.moodmix_cli "I'm studying for finals"            # real Gemini (needs GEMINI_API_KEY)
    python -m src.moodmix_cli --mock "I need motivation to work out"   # offline demo, no API call

This is separate from src/main.py, which still runs the original Module 3 simulation.
"""

import argparse
import sys
from pathlib import Path

from src.llm import GeminiClient
from src.mock_llm import MockGemini
from src.pipeline import RecommendationResult, recommend_from_text
from src.recommender import DEFAULT_STRATEGY, STRATEGIES, load_songs

SONGS_CSV = Path(__file__).resolve().parent.parent / "data" / "songs.csv"
WIDTH = 64
MAX_SCORE = 4.0


def render(result: RecommendationResult) -> str:
    """Format a pipeline result as text, always showing the engine's scoring reasons."""
    if not result.ok:
        return f"Could not make recommendations ({result.error_kind}): {result.error}"

    lines = [result.interpretation, "", "=" * WIDTH,
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MoodMix AI: describe what you want to hear")
    parser.add_argument("text", help="your mood, activity or situation, in your own words")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=list(STRATEGIES))
    parser.add_argument("-k", type=int, default=5, help="number of songs (default: 5)")
    parser.add_argument("--mock", action="store_true",
                        help="use the offline mock instead of calling Gemini (no API key needed)")
    args = parser.parse_args(argv)

    if args.mock:
        print("[MOCK Gemini: canned answers, no API call]\n")
        client = GeminiClient(client=MockGemini(), model="mock")
    else:
        client = GeminiClient()   # reads GEMINI_API_KEY lazily; never printed

    result = recommend_from_text(
        args.text, load_songs(str(SONGS_CSV)), client=client, k=args.k, strategy=args.strategy
    )
    print(render(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
