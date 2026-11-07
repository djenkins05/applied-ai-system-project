# Rubric coverage map

Maps each CodePath AI110 rubric item to the implementation, tests and evidence in this repository. "Status" is stated
conservatively: anything not run or not captured is marked as such. Last updated 2026-11-07.

## Required categories (3 points each)

| # | Requirement | Implementation | Tests | Evidence | Status |
|---|---|---|---|---|---|
| 1 | Identify the original project and its scope | Original Module 3 recommender: `src/recommender.py`, `src/main.py`, `data/songs.csv` (18 songs, 5 ranking strategies, CLI) | `tests/test_recommender.py` (32 pass, 3 xfail) | README "Original project (Module 3)" and the preserved "Original Project" section; `model_card.md` sections 1 to 9 | Covered |
| 2 | Substantial integrated AI feature that changes system behavior | Gemini turns free text into preferences that set the ranking (`src/llm.py`, `src/preferences.py`, `src/pipeline.py`); grounded AI explanations (`src/explain.py`); reliability layer (`src/guardrails.py`, `src/fallback.py`); feedback loop (`src/feedback.py`); UI (`app.py`) | `tests/test_llm.py`, `tests/test_preferences.py`, `tests/test_pipeline.py`, `tests/test_explain.py`, `tests/test_feedback.py` | `docs/evidence/live_gemini_run_1.md` (real run); `model_card.md` section 10 | Covered. Real-model quality was not measured (model card section 12) |
| 3 | Mermaid architecture diagram with source code that matches the system | `diagrams/architecture.mmd`, embedded in the README | `tests/test_docs.py` (embedded copy is identical; names real modules) | Source parses with Mermaid 11.4.1 (`mermaid.parse`, checked 2026-11-07) | Covered. A rendered image has not been captured |
| 4 | Functional end-to-end workflow, reproducible commands, 2 to 3 sample inputs and outputs | CLI `src/moodmix_cli.py`, app `app.py` | `tests/test_pipeline.py`, `tests/test_cli_manual.py`, `tests/test_app_ui.py` | README "Sample end-to-end examples": 1 real Gemini run, 1 offline mock run, 1 manual-only run (labelled); `docs/evidence/examples/` | Covered. Only one real Gemini run exists; none through the Streamlit app |
| 5 | Functional reliability, evaluation or guardrails with documented evidence | `src/guardrails.py`, `src/fallback.py`, `src/llm.py` (error classes, sanitized diagnostics), `src/reliability_log.py` | `tests/test_guardrails.py`, `tests/test_fallback.py`, `tests/test_llm_errors.py`, `tests/test_reliability_log.py`, `tests/test_pipeline_phase3.py` | `evals/results/guardrails.txt` and `.json` (43/43, simulated Gemini); `model_card.md` sections 11 and 12 | Covered, with the caveat that Gemini is simulated in the guardrail cases |
| 6 | Complete README: install, setup, execution, testing, sample I/O | `README.md` | `tests/test_docs.py` | README "Quick start", "Architecture", "Sample end-to-end examples", "Testing and evidence" | Covered |
| 7 | Model card extension with AI collaboration reflection (one accepted, one rejected or revised and why), limitations, ethics | `model_card.md` sections 10 to 16 | `tests/test_docs.py` (paths cited exist) | `model_card.md` section 15; `ai_interactions.md` | Drafted. Reflection is a first-person DRAFT that needs your review |

## Optional stretch categories (2 points each)

| # | Stretch | Status | Notes |
|---|---|---|---|
| 1 | Enhanced RAG (custom indexing or multiple retrieval sources, before/after improvement) | **Not yet demonstrated** | There is no retrieval step. The catalog is scored directly. |
| 2 | Agentic multi-step workflow with planning, tool calls, checking and decision traces | **Not yet demonstrated** | The pipeline is a fixed sequence of steps with no planning or tool selection and no decision trace. Claude Code development logs are not counted. |
| 3 | Specialized prompting with a measurable baseline-versus-specialized comparison | **Not yet demonstrated** | Prompts use a JSON schema, delimiters and few rules, but there is no baseline prompt and no measured comparison, so this is not claimed. |
| 4 | Evaluation harness running multiple predefined inputs with a pass/fail summary | **Demonstrated for guardrails and reliability; broader harness planned** | `evals/run_guardrails.py` runs 43 predefined cases and saves a pass/fail summary (`evals/results/guardrails.txt`), covered by `tests/test_guardrail_eval.py`. Gemini is simulated. A dedicated evals/run_eval.py (planned for Phase 6, does not exist yet) will cover broader end-to-end inputs. |

## Known gaps
- No screenshots captured yet (checklist in `docs/evidence/phase4_ui_walkthrough.md`).
- No recorded real-Gemini session through the Streamlit app.
- Diagram verified by parsing only; no rendered image has been captured.
- Model card reflection and `ai_interactions.md` are drafts awaiting review.
- Work is on branch `feature/streamlit-ui`, not merged to `main`.
- `CLAUDE.md` still describes planned files as "not yet created".
