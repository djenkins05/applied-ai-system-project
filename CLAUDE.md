# CLAUDE.md — MoodMix AI

## 1. Project Overview
MoodMix AI is my CodePath AI110 final project. It extends my Module 3 **Music Recommender Simulation**
into an interactive AI music assistant using **Python, Streamlit, and the Gemini API**.

**Original system (must keep working):** a content-based, CLI-first recommender.
- Loads an 18-song catalog from `data/songs.csv`
  (columns: id, title, artist, genre, mood, energy, tempo_bpm, valence, danceability, acousticness).
- `score_song(user_prefs, song, strategy)` scores each song out of `MAX_SCORE = 4.0` and returns
  `(score, reasons)`: genre match, mood match, and closeness of energy / valence / acousticness
  (`1 - |song - target|`).
- Five ranking strategies in `STRATEGIES` (`balanced` default, `classic`, `genre_first`, `mood_first`,
  `energy_focused`). Each strategy's weights must sum to 4.0 (asserted at import).
- `recommend_songs(user_prefs, songs, k, strategy)` returns top-k `(song, score, explanation)`;
  ties break by energy gap, then title.
- `Song`, `UserProfile`, and `Recommender` (OOP wrapper with `recommend` / `explain_recommendation`)
  are required by the tests.
- `src/main.py` is a CLI runner with 4 normal profiles + 9 adversarial profiles and `--strategy`.

## 2. Repository Structure
| Path | Purpose |
|---|---|
| `src/recommender.py` | Core scoring/ranking logic, dataclasses, `load_songs`. **Protected.** |
| `src/main.py` | CLI runner and the profile dictionaries. Run as `python src/main.py` (imports `from recommender import ...`). **Protected.** |
| `data/songs.csv` | 18-song catalog. **Protected.** |
| `tests/test_recommender.py` | 35 original pytest tests: 32 pass, 3 are `xfail(strict=True)` (imports `from src.recommender import ...`). **Protected.** |
| `README.md` | MoodMix AI overview, quick start, architecture, examples, testing and evaluation summary, then the preserved Module 3 documentation. |
| `model_card.md` | Model card: Module 3 sections 1–9, then the MoodMix AI extension (sections 10–16). |
| `ai_interactions.md` | AI-assisted development log (decisions, accepted and rejected suggestions). Stretch sections are intentionally not claimed. |
| `requirements.txt` | `pandas`, `pytest`, `streamlit`, `google-genai`, `python-dotenv`. |

Implemented MoodMix AI files (all new; the protected files above are unchanged):
- **UI / app logic:** `app.py` (Streamlit UI only), `.streamlit/config.toml` (dark theme), `src/ui_theme.py` (CSS and
  escaped HTML helpers, no logic), `src/app_controller.py` (UI-independent actions),
  `src/feedback.py` (like/dislike rules).
- **AI layer and safety:** `src/llm.py` (Gemini wrapper, injectable client), `src/preferences.py` (validation),
  `src/explain.py` (grounded explanations), `src/guardrails.py`, `src/fallback.py` (manual preferences),
  `src/reliability_log.py`, `src/pipeline.py`, `src/env.py`, `src/mock_llm.py`, `src/moodmix_cli.py`.
- **Diagram and docs:** `diagrams/architecture.mmd`, `docs/rubric_coverage.md`, `docs/evidence/`
  (`live_gemini_run_1.md`, `examples/`, `reproduce.md`, `phase4_ui_walkthrough.md`).
- **Evaluation:** `evals/run_eval.py` + `evals/eval_cases.json` (comprehensive harness), `evals/run_guardrails.py` +
  `evals/guardrail_cases.json` (43 guardrail cases, reused by the harness), saved reports in `evals/results/`.
- **Tests:** one new test file per module under `tests/` (all mock Gemini).

## 3. Final Project Goals and Required Features
1. **Integrated AI feature:** Gemini turns free-text mood/situation input ("rainy Sunday, need to focus")
   into structured preferences that feed the *existing* recommender, and writes a natural-language
   explanation of the results. The recommender, not the LLM, decides the ranking.
2. **Streamlit app** as the interactive front end (the CLI stays working), with **feedback-driven
   recommendations**: users can like/dislike each recommendation and adjust their preferences during
   the current session, and the next recommendations reflect that feedback.
3. **Mermaid architecture diagram** at `diagrams/architecture.mmd` (per CodePath assignment
   instructions) showing UI → input guardrails → Gemini → recommender → output validation → UI,
   plus the feedback loop, data, and test/eval components.
4. **Reproducible execution evidence:** saved command outputs/screenshots of real runs with fixed
   inputs, and exact commands to reproduce them.
5. **Reliability testing:** automated tests + logged failure handling for the AI layer.

**Explicit deliverable (+2-point stretch): evaluation harness.** `evals/run_eval.py` runs multiple
predefined inputs, prints a pass/fail summary, and saves reproducible results (fixed inputs,
deterministic where possible, output saved under `evals/results/`) that are documented in the README.

**Other stretch goals (only after required features are solid):** bounded agentic workflow (fixed
step/tool budget), specialized prompting (few-shot / schema-constrained output), multi-source
retrieval (e.g., catalog + extra song metadata).

## 4. Development Rules — Preserve Existing Functionality
- **Protect the original recommendation algorithm, existing tests, and CLI functionality.**
  Do **not** rewrite or reformat `src/recommender.py`, `src/main.py`, `tests/test_recommender.py`,
  or `data/songs.csv` unless I ask. `python src/main.py` (all `--strategy` options) must keep working.
  Feedback/preference adjustments are implemented in new modules by adjusting the preferences passed
  *into* `score_song`/`recommend_songs`, not by editing them.
- Prefer adding new modules that *call* existing functions (`score_song`, `recommend_songs`,
  `load_songs`, `Recommender`).
- Keep public names/signatures and the `STRATEGIES` weights-sum-to-4.0 invariant intact.
- Do not change existing tests to make them pass. Never remove or loosen an assertion.
- The 3 existing `xfail(strict=True)` tests document known bugs (empty prefs `KeyError`, negative
  scores from out-of-range energy, case-sensitive matching). Fixing one means removing its marker —
  propose that change to me first; don't fix them as a side effect.
- Before any change: run the test suite. After: run it again. Report both results faithfully.
- Make small, reviewable changes; one concern per change. If a task seems to require touching
  protected files, stop and ask.
- Don't invent facts about the code or results — read the file or run the command.

## 5. Coding Conventions and Modular Design
- Python 3, type hints and short docstrings (match the existing style in `recommender.py`).
- Keep layers separate: **UI** (`app.py`) → **AI layer** (`src/llm.py`, prompts) → **guardrails**
  (`src/guardrails.py`) → **recommender** (existing). The UI contains no scoring logic; the LLM
  wrapper contains no UI code.
- Gemini access goes through one wrapper with an injectable client so tests can mock it.
  Tests must never call the real API.
- Secrets: read `GEMINI_API_KEY` from the environment (or `.env`). Never hard-code or print keys.
  `.env` (and `.env.*`, `*.key`, `*.pem`, `secrets.*`, `logs/`) are git-ignored; `.env.example` stays tracked and
  contains no values. Never stage or print `.env`.
- LLM output is untrusted: request structured JSON, parse and validate it against the catalog's
  known genres/moods and 0–1 ranges before it reaches `score_song`.
- Add new dependencies to `requirements.txt` only when used; tell me which and why.
- Imports: the CLI uses `from recommender import ...` and tests use `from src.recommender import ...`.
  Follow whichever the file you're editing already uses; don't "fix" the discrepancy unasked.

## 6. Testing Requirements and Commands
```bash
pip install -r requirements.txt
pytest                                # current baseline: 501 passed, 3 xfailed
pytest -v tests/test_recommender.py   # original suite: 32 passed, 3 xfailed
python src/main.py --strategy all     # original CLI smoke test (run from repo root)
python -m src.moodmix_cli --mock "I need motivation to work out"   # offline mock CLI
python -m src.moodmix_cli --genre lofi --mood chill --energy 0.3   # manual-only CLI (no key)
streamlit run app.py                  # the Streamlit app
python evals/run_eval.py              # comprehensive evaluation harness (saves evals/results/eval_report.*)
python evals/run_guardrails.py        # 43-case guardrail evaluation (reused by the harness)
```
Exact reproduction steps and expected outputs: `docs/evidence/reproduce.md`.
- Baseline must stay green; new features ship with new tests (in new files, e.g.
  `tests/test_llm.py`, `tests/test_guardrails.py`, `tests/test_feedback.py`).
- Mock Gemini in unit tests. Cover: valid response, malformed JSON, unknown genre/mood, out-of-range
  numbers, empty/very long input, API error/timeout, missing key.
- **Evaluation harness (deliverable, implemented):** `python evals/run_eval.py` runs multiple predefined
  inputs, prints a pass/fail summary, and saves reproducible results to `evals/results/`. Feedback logic is
  tested (like/dislike and preference adjustments change subsequent rankings as expected, and reset cleanly).
  Keep expectations independent of the system under test, never weaken a threshold to make a check pass, and
  report real findings honestly.
- Reliability evidence = the harness output plus mocked-API tests, saved so I can cite them in the
  README and write-up.

## 7. Reliability, Guardrails, and Responsible AI
- **Input guardrails:** reject empty/oversized input; basic prompt-injection resistance (system
  prompt separate from user text; ignore instructions inside user input).
- **Output validation:** schema check; clamp or reject out-of-range values; map unknown genres/moods
  to "no match" rather than crashing.
- **Graceful fallback:** if Gemini fails or returns invalid output, fall back to manual preferences
  and the plain recommender; show a clear message. Timeouts and bounded retries only.
- **Grounding:** AI explanations may only reference songs and scores actually returned by the
  recommender — no invented songs, artists, or scores.
- **Transparency:** UI states that parts of the output are AI-generated; keep the score "reasons"
  visible.
- **Logging:** log errors and guardrail triggers (no API keys, minimal user text).
- **Known biases/limits to carry forward and be honest about** (from `model_card.md`): tiny 18-song
  catalog, 15 genres, label-based matching, no listening history, not for real music apps.
  Add an AI-specific section (hallucination, prompt injection, bias in mood interpretation).

## 8. Development Phases and Status
Phases 1–6 below use the numbering of the development commits (see `ai_interactions.md`).
1. **Preference validation layer** — done: `src/preferences.py`. (Baseline tests and the `.env` ignore rule were set up first.)
2. **AI layer** — done: Gemini wrapper, prompt → structured preferences, grounded explanations, mocked tests, CLI, one real live run.
3. **Guardrails & fallbacks** — done: input/output checks, manual fallback, reliability log, 43-case guardrail demo.
4. **Streamlit UI + feedback loop** — done: text input, strategy selector, results with score reasons + AI
   explanation, like/dislike and editable preferences (session state only), UI tests with a mocked Gemini.
5. **Architecture diagram & docs** — done: `diagrams/architecture.mmd`, README and model card updates, rubric map.
6. **Evaluation harness** — done: `evals/run_eval.py` (114 graded scenarios, 647 checks, reproducible, Gemini always
   scripted or canned) plus saved reports; one expectation (H1 top 3) is kept as a documented finding.
7. **Other stretch (optional)** — not demonstrated and not claimed: specialized prompting, bounded agentic workflow,
   multi-source retrieval.
8. **Final polish** — in progress: fresh-clone verification, reflection review (drafts are marked DRAFT until I approve
   them), four real-Gemini Streamlit screenshots are saved; remaining screenshots (ranking modes, manual mode, guardrails,
   failure fallback, limits) are pending my own captures; the rendered diagram is saved, then an approved merge and push.

## 9. Documentation and Grading Requirements
- **README.md:** keep existing content; add MoodMix AI overview, setup (including API key), run
  commands for CLI and Streamlit, architecture diagram, sample I/O, testing, limitations.
  Keep the Module 3 documentation preserved under its own heading; README code fences are balanced
  (checked) and should stay that way.
- **Mermaid architecture diagram** at `diagrams/architecture.mmd` (also embedded or linked in the
  README), matching the real code.
- **Evaluation harness results:** command, pass/fail summary, and saved results file documented in
  the README.
- **model_card.md:** extend (don't overwrite) with the AI feature, new risks, guardrails, eval
  results, and AI-assistance reflection.
- **Execution evidence:** commands + captured outputs + screenshots under `docs/evidence/`, with
  exact reproduction steps.
- **ai_interactions.md:** fill only the stretch sections actually attempted.
- Every claim in docs must be backed by something I ran; mark anything unverified as such.
- Before declaring done, check the work against the course rubric/assignment page (ask me for it
  if it isn't in the repo).

## 10. Git Safety Rules
- **Never** `git commit`, `git push`, `git merge`, `git rebase`, `git reset --hard`, force-push,
  amend, or delete branches/files without my explicit approval for that specific action.
- It's fine to run read-only git commands (`status`, `diff`, `log`).
- When I approve a commit: show `git status` and the diff summary first, stage specific files
  (no `git add -A`), never include `.env` or secrets, and use a clear message.
- Work on a feature branch, not directly on `main`, if I ask for commits.
- If unsure whether an action is destructive or outward-facing, ask first.
