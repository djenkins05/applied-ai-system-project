"""
Offline stand-in for Gemini, used by `python -m src.moodmix_cli --mock` and in tests.

It mimics `client.models.generate_content(model=, contents=, config=)` with canned,
keyword-based answers. It makes no network calls, needs no API key, and is NOT a
substitute for the real model: it only recognises a handful of example phrases.
"""

import json
import re
from typing import Any, Dict, List

# keyword -> canned preferences (labels exist in data/songs.csv)
_SCENARIOS = (
    (("study", "finals", "focus", "homework", "coding"),
     {"genres": ["lofi", "ambient", "classical"], "moods": ["focused", "chill"],
      "target_energy": 0.3, "target_valence": 0.5, "target_acousticness": 0.8}),
    (("workout", "gym", "motivation", "run", "lift"),
     {"genres": ["EDM", "pop", "metal"], "moods": ["uplifting", "intense"],
      "target_energy": 0.95, "target_valence": 0.8, "target_acousticness": 0.05}),
    (("rain", "sad", "heartbreak", "lonely", "melanchol"),
     {"genres": ["hip-hop", "rap"], "moods": ["melancholic", "reflective"],
      "target_energy": 0.4, "target_valence": 0.2, "target_acousticness": 0.4}),
    (("party", "dance", "celebrat"),
     {"genres": ["pop", "disco", "EDM"], "moods": ["happy", "playful", "uplifting"],
      "target_energy": 0.85, "target_valence": 0.9, "target_acousticness": 0.1}),
    (("sleep", "relax", "unwind", "calm"),
     {"genres": ["ambient", "classical", "jazz"], "moods": ["relaxed", "dreamy", "chill"],
      "target_energy": 0.2, "target_valence": 0.4, "target_acousticness": 0.9}),
)


class _Response:
    def __init__(self, text: str):
        self.text = text


class _Models:
    def __init__(self, owner: "MockGemini"):
        self._owner = owner

    def generate_content(self, *, model: str, contents: str, config: Dict[str, Any]) -> _Response:
        self._owner.calls.append({"model": model, "contents": contents, "config": config})
        properties = config["response_json_schema"]["properties"]
        if "explanations" in properties:
            return _Response(json.dumps(self._explain(contents)))
        return _Response(json.dumps(self._interpret(contents)))

    @staticmethod
    def _interpret(contents: str) -> Dict[str, Any]:
        text = contents.lower()
        for keywords, prefs in _SCENARIOS:
            if any(word in text for word in keywords):
                return prefs
        return {}   # unusable input -> the pipeline reports invalid_preferences

    @staticmethod
    def _explain(contents: str) -> Dict[str, List[Dict[str, Any]]]:
        facts = json.loads(re.search(r"<facts>\n(.*)\n</facts>", contents, re.DOTALL).group(1))
        return {"explanations": [
            {"song_id": song["song_id"],
             "why": f"This {song['mood']} {song['genre']} pick suits what you described."}
            for song in facts["songs"]
        ]}


class MockGemini:
    """Drop-in for a google-genai client in demos and tests. `calls` records every request."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.models = _Models(self)
