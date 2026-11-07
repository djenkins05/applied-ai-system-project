# AI Interactions Log

## AI-assisted development log (MoodMix AI)

Claude Code assisted with planning, implementing and testing MoodMix AI. MoodMix AI itself is **not** an agentic
application: it runs a fixed pipeline with no planning, tool selection or decision trace, so the agentic workflow and design
pattern stretch features are not claimed (see `docs/rubric_coverage.md`). The entries below record only decisions that
actually happened.

### Timeline

| Phase | Commit | What was built with AI help | Human checks and decisions |
|---|---|---|---|
| Setup | `0497d11` | Development environment and `CLAUDE.md` project rules (protect the Module 3 code, mock Gemini in tests, never log keys) | I set the rules before any AI feature was written |
| 1 | `a5433d3` | `src/preferences.py`: validate untrusted preferences (catalog labels only, clamp to 0-1) before they reach the engine | The recommender stays unchanged; the AI layer adapts to it |
| 2 | `724b122`, `79463c4` | `src/llm.py` (injectable Gemini client), `src/explain.py` (grounded explanations), CLI and mock client, live-run evidence | I ran the real command myself and pasted the output; the first live runs failed (see below) |
| 3 | `c7f85f3` | `src/guardrails.py`, `src/fallback.py`, `src/reliability_log.py`, 43-case guardrail harness | Three plan changes I required (below) |
| 4 | `11070a2` | `app.py`, `src/feedback.py`, `src/app_controller.py`, UI tests | Three plan changes I required (below) |
| 5 | `5e7c74d` | `diagrams/architecture.mmd`, README restructure, model card extension, rubric map | Evidence labelled real, mock or manual; Mermaid source parse-checked |
| 6 | `fe46099` | `evals/run_eval.py`, `evals/eval_cases.json`, saved reports, `tests/test_run_eval.py`, `docs/evidence/reproduce.md` | Expectations written before any output was inspected; one failed and was handled openly (below) |

### Suggestions accepted

- **Diagnose the opaque `llm_error`.** I asked Claude to investigate. It found that HTTP 400 and 404 fell through to a generic error
  class and that the status code was never printed, then classified 400/401/403/404/429 separately and added a sanitized diagnostic. Result: the next run showed `HTTP 404 NOT_FOUND` (retired default model). Verified by mocked tests and my live run.
- **Look the model ID up in Google AI Studio** instead of guessing one. I found `gemini-3.5-flash-lite` there, and the live run succeeded
  (`docs/evidence/live_gemini_run_1.md`).

### Suggestions rejected or revised

- **Hash of each request in the reliability log (rejected by me).** The Phase 3 plan included a short input hash. I required that logs contain no raw prompts and no input hashes, only operational metadata. The plan and code were revised and tests check it.
- **Broad injection detection (revised by me).** The plan's detector mentioned terms like "developer mode". I asked for a narrow detector aimed at clear override, prompt-reveal, role-impersonation and safeguard-bypass attempts, plus tests that "ignore distractions" and "forget my previous music preferences" still work.
- **Manual fallback (tightened by me).** I required it to be explicit: with no usable manual preferences the app returns a friendly error (`fallback_available=True`) and never builds recommendations from defaults. In the UI it is a button the user presses.
- **Phase 4 behaviour (my three changes).** Disliked songs are excluded with an Undo and a message when fewer songs remain; the page explains that feedback adjusts rule-based preferences and does not retrain Gemini; and Streamlit reruns must not erase the request, edits, results or feedback, with tests for that.
- **Existing tests (AI had to adapt, not edit).** A new input rule conflicted with an existing test (it sent the one-letter input "x"), so the rule was relaxed instead of editing the test. One existing expectation was deliberately changed (HTTP 400 now reports `bad_request` instead of `llm_error`) because that behaviour change was the point of the fix, and it was reported at the time.

- **Phase 6: the H1 expectation (revised with my approval, original preserved).** The harness scenario `H1-like-new-genre` originally
  expected that liking a jazz song (*Coffee Shop Stories*) would move it into the top 3. That expectation was written before the
  first run. The first run reported 113/114 scenarios and 645/646 checks and exited with code 1: the song rose from #5 to #4 and its
  score from 1.78 to 3.85, because four songs already matched both of the user's chosen genres and moods and scored 3.84 to 3.94.
  I approved revising the scenario, with two conditions: do not change the recommendation algorithm, and do not hide the original
  failure. H1 now checks the intended behavior (the liked song's score increases, its rank improves, the result is deterministic, and
  the ranking equals the original engine run on the adjusted preferences), no rank is hard-coded as a threshold, and the original
  top-3 expectation is kept as an ungraded finding (`H1-finding-top3-not-guaranteed`, status NOT MET, with the observed ranks and
  scores). `tests/test_run_eval.py` no longer allows any expected failure.

### Problems found by checking

- The first real run failed with a retired model (404), then a 504 and a 503. A timeout increase from 15 s to 45 s was made for the 504, but whether the timeout was the cause was never confirmed; the 503 was a Gemini overload.
- A UI test showed the interpretation summary lagging one rerun behind edits; the edit check was moved to the start of each run.
- While building the Phase 6 harness, one of my own expectations (G5, manual energy-only input) asked for a warning that energy-only
  input never produces; I corrected it before the first run because the expectation itself was wrong, not to make a result pass. A
  deliberate-breakage test then showed the harness crashing when a liked song fell outside the top 10 with a broken engine, so the finding
  code was made robust, and a vacuous always-pass check was removed.
- Four app screenshots from a real Gemini session (Offline demo AI off, confirmed by me) are saved in `docs/evidence/screenshots/`. Other planned screenshots (ranking modes, manual mode, guardrail rejection, failure fallback, limits) are not captured yet. The rendered architecture diagram is saved as `10_architecture_rendered.png`.

### What I learned from AI-assisted development

Throughout the development of MoodMix AI, I used Claude Code to help plan, implement, and test new features. However, I learned that AI-generated code and suggestions still require careful review. Some suggestions worked well, such as improving Gemini API error diagnostics, while others needed changes to better fit my project's requirements.

One important example was the feedback evaluation. The initial test expected a liked song to reach the top three recommendations, but the results showed that feedback improved the song's score and ranking without guaranteeing a top-three position. Rather than changing the recommendation algorithm to satisfy the test, I revised the evaluation to measure the actual intended behavior and preserved the original failure as documentation.

This experience helped me understand the importance of testing assumptions, protecting existing functionality, and using AI as a development assistant rather than treating its output as automatically correct.
