# Reproducing the evidence

Everything below runs **offline**: Gemini is scripted, canned or absent, and no API key or `.env` is needed. The one real
Gemini run (Example 1 in the README) cannot be reproduced offline; it needs your own key.
Last run on 2026-11-07, Python 3.12, macOS.

```bash
git clone <this repository> && cd applied-ai-system-project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 1. Test suite (Gemini mocked, network blocked)
```bash
python3 -m pytest
```
Expected: `501 passed, 3 xfailed`. The 3 xfails are the known-bug tests in `tests/test_recommender.py` (Module 3).

## 2. Comprehensive evaluation harness (new in Phase 6)
```bash
python evals/run_eval.py
```
Writes `evals/results/eval_report.txt` and `evals/results/eval_report.json`. Expected last lines (exit code 0):
```
New scenarios: 114/114 passed (7 informational items not graded: grounding probes and findings)
New checks: 647/647 passed. By basis: independent 219/219, specification 64/64, invariant 355/355, regression 9/9
Reused guardrail scenarios: 43/43 passed
Reproducible on rerun: True
Overall: PASS
```
The report also contains a documented, ungraded finding (`H1-finding-top3-not-guaranteed`): the original expectation that a liked
jazz song would reach the top 3 was not met (rank 5 -> 4, score 1.78 -> 3.85). Any failing graded scenario makes the exit code 1.

Check that two runs write identical reports:
```bash
python evals/run_eval.py > /dev/null; md5 -q evals/results/eval_report.json evals/results/eval_report.txt
python evals/run_eval.py > /dev/null; md5 -q evals/results/eval_report.json evals/results/eval_report.txt
```
(`md5sum` on Linux.) The two pairs of hashes must match. On 2026-11-07 both runs gave
`0d8ff9e8375fc6c3cac23c19cf73c406` (json) and `1cc6865611a507c2a353190ecf674981` (txt).

## 3. Guardrail demonstration (original, reused by the harness)
```bash
python evals/run_guardrails.py
```
Expected: `Summary: 43/43 passed, 0 failed`; writes `evals/results/guardrails.txt` and `.json`.

## 4. CLI smoke tests
```bash
python src/main.py --strategy all                                  # original Module 3 CLI, exit code 0
python3 -m src.moodmix_cli --mock "I need motivation to work out"  # offline mock, exit code 0
python3 -m src.moodmix_cli --genre lofi --mood chill --energy 0.3  # manual only, exit code 0
```
Captured outputs: `docs/evidence/examples/02_offline_mock_workout.txt` and `03_manual_only_lofi_chill.txt`.

## 5. Not reproducible offline
- Example 1 in the README (real Gemini, `docs/evidence/live_gemini_run_1.md`): `python3 -m src.moodmix_cli "I'm studying for finals"`
  with your own `GEMINI_API_KEY`. Wording and scores can differ between runs and model versions.
- A real-Gemini session through the Streamlit app, and the screenshots: not yet captured.
