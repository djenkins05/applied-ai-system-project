"""
Guardrail and reliability demonstration for MoodMix AI.

Runs fixed, offline cases (Gemini is always simulated; no network, no API key, no .env) through the
real pipeline, prints a PASS/FAIL line per case, and saves reproducible results to
evals/results/guardrails.txt and evals/results/guardrails.json (no timestamps, so reruns match).

    python evals/run_guardrails.py          # from the repository root

Exit code is 0 only if every case passes.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.fallback import ManualPreferences                        # noqa: E402
from src.llm import GeminiClient                                  # noqa: E402
from src.pipeline import recommend_from_manual, recommend_from_text  # noqa: E402
from src.recommender import load_songs                            # noqa: E402

CASES_PATH = ROOT / "evals" / "guardrail_cases.json"
RESULTS_DIR = ROOT / "evals" / "results"
COMMAND = "python evals/run_guardrails.py"


# --- Simulated Gemini ----------------------------------------------------------

class SimulatedAPIError(Exception):
    """Shaped like the SDK's APIError: HTTP code, status word, message."""

    def __init__(self, code: int):
        status = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 404: "NOT_FOUND",
                  429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE"}.get(code, "ERROR")
        super().__init__(f"simulated http {code}")
        self.code, self.status, self.message = code, status, f"simulated {status}"


class ReadTimeout(Exception):
    """Classified as a timeout by name."""


class ScriptedClient:
    """Mimics client.models.generate_content with scripted answers; records every call."""

    def __init__(self, interpret: Any, explain: Any):
        self._script = {"interpret": interpret, "explain": explain}
        self.calls: List[str] = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        kind = "explain" if "explanations" in config["response_json_schema"]["properties"] else "interpret"
        self.calls.append(kind)
        script = self._script[kind]
        if isinstance(script, list):
            script = script.pop(0) if len(script) > 1 else script[0]
        return _realize(script, kind, contents)


class _Response:
    def __init__(self, text):
        self.text = text


def _realize(item: Dict[str, Any], kind: str, contents: str) -> _Response:
    if "error" in item:
        raise SimulatedAPIError(item["error"])
    if item.get("timeout"):
        raise ReadTimeout()
    if item.get("empty"):
        return _Response(None)
    if "json" in item:
        return _Response(json.dumps(item["json"]))
    if "raw" in item:
        return _Response(item["raw"])
    if "generic" in item or "hostile" in item:
        facts = json.loads(contents.split("<facts>\n", 1)[1].rsplit("\n</facts>", 1)[0])
        generic = item.get("generic", "A gentle pick for focus.")
        entries = []
        for n, song in enumerate(facts["songs"]):
            why = item["hostile"] if ("hostile" in item and n == 0) else generic
            entries.append({"song_id": song["song_id"], "why": why})
        return _Response(json.dumps({"explanations": entries}))
    raise ValueError(f"unknown scripted item: {item}")


# --- Running cases -------------------------------------------------------------

def build_client(case: Dict[str, Any], defaults: Dict[str, Any]):
    spec = case.get("gemini", {})
    if spec.get("missing_key"):
        return GeminiClient(), None            # no key in the environment -> MissingAPIKeyError
    scripted = ScriptedClient(spec.get("interpret", defaults["interpret"]),
                              spec.get("explain", defaults["explain"]))
    return GeminiClient(client=scripted, sleep=lambda _s: None), scripted


def observe(result, scripted, calls_before: int = 0) -> Dict[str, Any]:
    return {
        "ok": result.ok, "error_kind": result.error_kind, "source": result.source if result.ok else None,
        "used_fallback": result.used_fallback, "fallback_available": result.fallback_available,
        "guardrail": result.guardrail_flags, "rec_count": len(result.recommendations),
        "gemini_calls": (len(scripted.calls) - calls_before) if scripted else 0,   # per step
    }


def check(expect: Dict[str, Any], result, scripted, calls_before: int = 0) -> List[str]:
    """Return a list of failed expectations (empty means PASS)."""
    seen = observe(result, scripted, calls_before)
    failures = []
    for key in ("ok", "error_kind", "source", "used_fallback", "fallback_available",
                "guardrail", "rec_count", "gemini_calls"):
        if key in expect and seen[key] != expect[key]:
            failures.append(f"{key}: expected {expect[key]!r}, got {seen[key]!r}")
    recs = result.recommendations
    if expect.get("no_recommendations") and recs:
        failures.append("expected no recommendations")
    if "error_contains" in expect and expect["error_contains"] not in (result.error or ""):
        failures.append(f"error missing {expect['error_contains']!r}")
    for fragment in expect.get("warnings_contain", []):
        if not any(fragment in w for w in result.warnings):
            failures.append(f"warnings missing {fragment!r}")
    if "note_contains" in expect and expect["note_contains"] not in (result.explanation_note or ""):
        failures.append(f"note missing {expect['note_contains']!r}")
    if expect.get("first_ai_none") and not (recs and recs[0].ai_explanation is None and recs[0].reasons):
        failures.append("first AI explanation should be dropped and engine reasons kept")
    if expect.get("first_ai_present") and not (recs and recs[0].ai_explanation):
        failures.append("first AI explanation missing")
    if expect.get("all_ai_none") and any(r.ai_explanation for r in recs):
        failures.append("AI explanations should be absent")
    if result.ok and any(not r.reasons for r in recs):
        failures.append("every recommendation must keep its engine reasons")
    return failures


def step_text(step: Dict[str, Any]) -> str:
    if "text_repeat" in step:
        return step["text_repeat"]["unit"] * step["text_repeat"]["times"]
    return step.get("text", "")


def run_step(step: Dict[str, Any], client, scripted, songs) -> Any:
    manual = ManualPreferences(**step["manual"]) if "manual" in step else None
    if step.get("mode") == "manual":
        return recommend_from_manual(manual, songs)
    return recommend_from_text(step_text(step), songs, client=client,
                               manual=manual if manual and manual.has_any() else None)


def run_all() -> Dict[str, Any]:
    spec = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    songs = load_songs(str(ROOT / "data" / "songs.csv"))
    results = []
    for case in spec["cases"]:
        client, scripted = build_client(case, spec["gemini_defaults"])
        steps = case.get("steps") or [case]
        step_results = []
        for index, step in enumerate(steps, start=1):
            before = len(scripted.calls) if scripted else 0
            result = run_step(step, client, scripted, songs)
            failures = check(step["expect"], result, scripted, before)
            step_results.append({"step": index, "passed": not failures, "failures": failures,
                                 "observed": observe(result, scripted, before)})
        results.append({"id": case["id"], "group": case["group"], "description": case["description"],
                        "passed": all(s["passed"] for s in step_results), "steps": step_results})
    passed = sum(r["passed"] for r in results)
    return {"command": COMMAND, "total": len(results), "passed": passed,
            "failed": len(results) - passed, "cases": results}


def format_report(report: Dict[str, Any]) -> str:
    lines = ["MoodMix AI guardrail and reliability evaluation",
             f"Command: {report['command']}",
             "Gemini is simulated in every case (no network, no API key, no .env).",
             f"Cases: {report['total']}", ""]
    group = None
    for case in report["cases"]:
        if case["group"] != group:
            group = case["group"]
            lines += [f"-- {group} --"]
        lines.append(f"[{'PASS' if case['passed'] else 'FAIL'}] {case['id']}: {case['description']}")
        for step in case["steps"]:
            o = step["observed"]
            label = f"  step {step['step']}: " if len(case["steps"]) > 1 else "    "
            lines.append(f"{label}ok={o['ok']} kind={o['error_kind']} source={o['source']} "
                         f"fallback_used={o['used_fallback']} fallback_available={o['fallback_available']} "
                         f"guardrail={o['guardrail']} recs={o['rec_count']} gemini_calls={o['gemini_calls']}")
            lines += [f"      FAILED: {f}" for f in step["failures"]]
    lines += ["", f"Summary: {report['passed']}/{report['total']} passed, {report['failed']} failed"]
    return "\n".join(lines) + "\n"


def isolate_environment() -> None:
    """Never read a real key or .env during the run; keep pipeline logs out of the report."""
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GEMINI_MODEL", None)
    os.environ["MOODMIX_DISABLE_DOTENV"] = "1"
    logging.disable(logging.CRITICAL)


def main() -> int:
    isolate_environment()
    report = run_all()
    text = format_report(report)
    print(text, end="")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "guardrails.txt").write_text(text, encoding="utf-8")
    (RESULTS_DIR / "guardrails.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
