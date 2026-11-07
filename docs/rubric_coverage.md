# Rubric coverage map

Maps each CodePath AI110 rubric item to the implementation, tests and evidence in this repository. "Status" is stated
conservatively: anything not run or not captured is marked as such. Last updated 2026-11-07 (after Phase 6).

## Required categories (3 points each)

| # | Requirement | Implementation | Tests | Evidence | Status |
|---|---|---|---|---|---|
| 1 | Identify the original project and its scope | Original Module 3 recommender: `src/recommender.py`, `src/main.py`, `data/songs.csv` (18 original rows, now part of a 68-song catalog; 5 ranking strategies, CLI) | `tests/test_recommender.py` (32 pass, 3 xfail) | README "Original project (Module 3)" and the preserved "Original Project" section; `model_card.md` sections 1 to 9 | Covered |
| 2 | Substantial integrated AI feature that changes system behavior | Gemini turns free text into preferences that set the ranking (`src/llm.py`, `src/preferences.py`, `src/pipeline.py`); grounded AI explanations (`src/explain.py`); reliability layer (`src/guardrails.py`, `src/fallback.py`); feedback loop (`src/feedback.py`); UI (`app.py`) | `tests/test_llm.py`, `tests/test_preferences.py`, `tests/test_pipeline.py`, `tests/test_explain.py`, `tests/test_feedback.py` | `docs/evidence/live_gemini_run_1.md` (real run); `model_card.md` section 10; real-Gemini Streamlit session screenshots `docs/evidence/screenshots/01` to `04` (Offline demo AI off, author-confirmed) | Covered. Real-model quality was not measured (model card section 12) |
| 3 | Mermaid architecture diagram with source code that matches the system | `diagrams/architecture.mmd`, embedded in the README; rendered image `docs/evidence/screenshots/10_architecture_rendered.png` | `tests/test_docs.py` (embedded copy is identical; names real modules) | Source parses with Mermaid 11.4.1 (`mermaid.parse`, checked 2026-11-07); rendered image saved as `docs/evidence/screenshots/10_architecture_rendered.png` (captured by the author, unedited) | Covered |
| 4 | Functional end-to-end workflow, reproducible commands, 2 to 3 sample inputs and outputs | CLI `src/moodmix_cli.py`, app `app.py` | `tests/test_pipeline.py`, `tests/test_cli_manual.py`, `tests/test_app_ui.py` | README "Sample end-to-end examples": 1 real Gemini run, 1 offline mock run, 1 manual-only run (labelled); `docs/evidence/examples/`; exact reproduction commands in `docs/evidence/reproduce.md`; four app screenshots in `docs/evidence/screenshots/` (`01_homepage`, `02_edit_preferences`, `03_recommendation_cards`, `04_feedback_notes`; real Gemini, Offline demo AI off, author-confirmed) | Covered. One real Gemini CLI run plus one real-Gemini Streamlit session (screenshots only; the offline mock run and the scripted evaluation harness are separate and never call real Gemini) |
| 5 | Functional reliability, evaluation or guardrails with documented evidence | `src/guardrails.py`, `src/fallback.py`, `src/llm.py` (error classes, sanitized diagnostics), `src/reliability_log.py` | `tests/test_guardrails.py`, `tests/test_fallback.py`, `tests/test_llm_errors.py`, `tests/test_reliability_log.py`, `tests/test_pipeline_phase3.py`, `tests/test_run_eval.py` (includes deliberate-breakage self-tests) | `evals/results/guardrails.txt` and `.json` (43/43); `evals/results/eval_report.txt` and `.json` (114/114 new scenarios, 649/649 checks, 2 documented findings; 68-song catalog); `model_card.md` sections 11 and 12 | Covered, with the caveat that Gemini is simulated or canned in every automated scenario |
| 6 | Complete README: install, setup, execution, testing, sample I/O | `README.md` | `tests/test_docs.py` | README "Quick start", "Architecture", "Sample end-to-end examples", "Testing and evidence" | Covered |
| 7 | Model card extension with AI collaboration reflection (one accepted, one rejected or revised and why), limitations, ethics | `model_card.md` sections 10 to 18 (limitations: sections 13 and 17; **system limitations and future improvements: section 18**; ethics: section 14) | `tests/test_docs.py` (paths cited exist) | `model_card.md` section 15; `model_card.md` section 18 ("System Limitations and Future Improvements", first person, about the 68-song version); `ai_interactions.md` | Covered. The author reviewed and approved the reflection (`model_card.md` section 15 and `ai_interactions.md`) |

## Optional stretch categories (2 points each)

| # | Stretch | Status | Notes |
|---|---|---|---|
| 1 | Enhanced RAG (custom indexing or multiple retrieval sources, before/after improvement) | **Not yet demonstrated** | There is no retrieval step. The catalog is scored directly. |
| 2 | Agentic multi-step workflow with planning, tool calls, checking and decision traces | **Not yet demonstrated** | The pipeline is a fixed sequence of steps with no planning or tool selection and no decision trace. Claude Code development logs are not counted. |
| 3 | Specialized prompting with a measurable baseline-versus-specialized comparison | **Not yet demonstrated** | Prompts use a JSON schema, delimiters and few rules, but there is no baseline prompt and no measured comparison, so this is not claimed. |
| 4 | Evaluation harness running multiple predefined inputs with a pass/fail summary | **Demonstrated** (with caveats) | `evals/run_eval.py` runs 114 graded scenarios (649 checks, labelled by basis) plus 7 ungraded items (6 grounding probes and 1 documented finding) across 9 categories, and reuses the 43 guardrail scenarios from `evals/run_guardrails.py` separately. It prints a pass/fail summary and saves `evals/results/eval_report.txt` and `.json`, identical across reruns. Result: 114/114 scenarios and 647/647 checks pass, exit code 0. Covered by `tests/test_run_eval.py`, which includes deliberate-breakage self-tests and no allow-list of expected failures. Gemini is scripted or canned, so this does not measure real-model quality. |

## Evaluation finding (documented, not a gap)
The original expectation for `H1-like-new-genre` (a liked jazz song reaches the top 3) was **not met**: it rose from #5 to #4 and its
score from 1.78 to 3.85. After review, H1 was changed to check the intended behavior and the original expectation is kept as the
ungraded finding `H1-finding-top3-not-guaranteed` in `evals/results/eval_report.txt`. Feedback influences rankings but does not
guarantee a top-k position. No threshold was set to the observed rank, and the recommendation algorithm was not changed.

## Catalog change (one unified `data/songs.csv`, 68 songs)
The catalog now holds 68 songs: the 18 original Module 3 rows (unchanged) plus 50 real songs whose energy, valence, acousticness,
danceability and tempo are **approximate editorial estimates, not Spotify data** (`data/README.md`). There is no selector. Effects on
the evidence: the earlier evaluation (114/114 scenarios, 647/647 checks, 43/43 guardrails) is frozen in
`evals/results/history/18_song_baseline/`; the 68-song results are `evals/results/eval_report.*` (114/114, 649/649, 2 documented
findings: H1 and the replaced A1 expectation), `guardrails.*` (43/43, unchanged) and `unified_catalog.*` (15/15 scenarios, 79/79 checks).
After a review, nine real-song rows were corrected (the results before are frozen in `evals/results/history/68_song_before_data_corrections/`; no graded outcome changed). Grounding fixes for real names are covered by `tests/test_explain_real_names.py`. The four app screenshots and the rendered
diagram image were captured with the 18-song catalog.

## Known gaps
- The author has visually reviewed the redesigned app and saved four real screenshots (`docs/evidence/screenshots/01` to `04`), and the author confirms they show a real Gemini session (Offline demo AI off). **Completed: real-Gemini Streamlit screenshot evidence.** Other screenshots (ranking modes, manual mode, guardrail rejection, failure fallback, limits) are still to capture (checklist in `docs/evidence/phase4_ui_walkthrough.md`).
- Real-Gemini Streamlit evidence is four screenshots of one session; there is no recording or saved transcript, and only one real CLI run. Real-model interpretation quality is not measured, and the automated evaluation still uses scripted or canned Gemini.
- Stretch 1, 2 and 3 are not demonstrated.
- Work is on branch `feature/streamlit-ui`, not merged to `main`.
- The four app screenshots and `10_architecture_rendered.png` were captured before the catalog grew to 68 songs; the diagram source now says "68 songs (18 original + 50 real)" and the saved render still shows the older label (re-render if you want them to match).
- The real songs' numeric ratings are estimates, not official data; the grounding check rejects some harmless explanations that contain ambiguous single-word names.
