# Historical results: 68-song catalog BEFORE the data-quality corrections (frozen)

Saved evaluation results from the first unified 68-song catalog, before the nine row corrections listed below were applied to
`data/songs.csv`. Kept as historical evidence; not regenerated. Current results are in `evals/results/`.

| File | Result | md5 |
|---|---|---|
| `eval_report.txt` / `.json` | 114/114 scenarios, 649/649 checks | txt `230e0cba2946783e1b2c639f820ca282`, json `113961b90f8c805974afdb2dc3cc9da3` |
| `unified_catalog.txt` / `.json` | 15/15 scenarios, 79/79 checks | txt `dd1346cef6b740048c20f8a97fdd1da0`, json `bcf7e0eb53b6b2f28362a6af18ddf2a2` |
| `guardrails.txt` / `.json` | 43/43 (unchanged by the corrections) | |
| `songs_before_corrections.csv` | the 68-row catalog these results were produced with | |

Corrections applied afterwards (rows 19-68 only; the 18 original rows are unchanged): Bad and Boujee (artist "Migos ft. Lil Uzi Vert",
valence 0.35 to 0.50), Gold Digger (artist "Kanye West ft. Jamie Foxx"), Sicko Mode (artist "Travis Scott ft. Drake"), Feather (genre
lofi to hip-hop), As It Was (genre indie pop to pop), Wake Me Up (acousticness 0.04 to 0.20), Discreet Music (acousticness 0.70 to
0.25), An Ending (Ascent) (acousticness 0.60 to 0.30), HUMBLE. (energy 0.62 to 0.75).

What changed in the results: no graded scenario or check changed outcome. The report text differs only in observations: the H1 finding
no longer lists Feather among songs matching both of the user's chosen labels (it is no longer lofi), the "sad request" check now
also lists Feather's mood "chill" among its top five, and the "original songs in the top 10" diagnostic for the study request went
from 4 to 5.
