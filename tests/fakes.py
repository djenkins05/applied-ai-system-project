"""Scripted fake Gemini client shared by the Phase 2 tests. Never touches the network."""

import json
from typing import Any, Dict, List


class FakeAPIError(Exception):
    """Looks like an SDK APIError: has an HTTP status code."""

    def __init__(self, code: int):
        super().__init__(f"fake http {code}")
        self.code = code


class ReadTimeout(Exception):
    """Looks like a network timeout (classified by name)."""


class _Response:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """
    Mimics client.models.generate_content. `interpret` and `explain` script the answers for
    the two kinds of call. Each is a str (returned), an Exception (raised), or a list of
    those consumed one per call (the last item repeats).
    """

    def __init__(self, interpret: Any = None, explain: Any = None):
        self._script = {"interpret": interpret, "explain": explain}
        self.calls: List[Dict[str, Any]] = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        kind = "explain" if "explanations" in config["response_json_schema"]["properties"] else "interpret"
        self.calls.append({"kind": kind, "model": model, "contents": contents, "config": config})
        script = self._script[kind]
        if isinstance(script, list):
            script = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(script, Exception):
            raise script
        return _Response(script)

    def kinds(self) -> List[str]:
        return [call["kind"] for call in self.calls]


def prefs_json(**overrides) -> str:
    data = {
        "genres": ["lofi", "ambient"],
        "moods": ["focused", "chill"],
        "target_energy": 0.3,
        "target_valence": 0.5,
        "target_acousticness": 0.8,
    }
    data.update(overrides)
    return json.dumps(data)


def explanations_json(pairs) -> str:
    return json.dumps({"explanations": [{"song_id": i, "why": w} for i, w in pairs]})
