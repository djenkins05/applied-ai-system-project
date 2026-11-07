# Historical 18-song baseline (frozen)

These four files are the saved evaluation results from when `data/songs.csv` had **18 songs**, copied byte-for-byte from git
commit `1631a47` (identical to the earlier Phase 6 results). They are kept as historical evidence and are **not**
regenerated. Current results for the 68-song catalog are in `evals/results/eval_report.*`, `guardrails.*` and
`unified_catalog.*`; do not compare the two sets directly because the catalog differs.

| File | Result |
|---|---|
| `eval_report.txt` / `.json` | 114/114 scenarios, 647/647 checks, 1 documented finding (H1); md5 `1cc6865611a507c2a353190ecf674981` (txt), `0d8ff9e8375fc6c3cac23c19cf73c406` (json) |
| `guardrails.txt` / `.json` | 43/43 |

Reproduce the 18-song results: check out commit `1631a47` (or the `29bc98b` commit before the merge) and run
`python evals/run_eval.py` and `python evals/run_guardrails.py`. The first 18 rows of today's `data/songs.csv` are
identical to that file, but the harness expectations were written for the 18-song catalog.
