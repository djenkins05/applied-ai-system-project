# Song catalog data card (`songs.csv`)

`data/songs.csv` is ONE catalog of **68 songs**: the 18 songs from the Module 3 project plus 50 real, commercially released
songs. There is no catalog selector; the recommender, Gemini prompts, feedback and grounding checks all use this file.

## Schema
`id,title,artist,genre,mood,energy,tempo_bpm,valence,danceability,acousticness`. Ids are unique (1 to 68). Genres and moods use one
shared vocabulary (15 genres, 14 moods; every label appears). Only genre, mood, energy, valence and acousticness affect scoring;
`tempo_bpm` and `danceability` are carried for schema compatibility.

## Rows
- **ids 1 to 18:** the original Module 3 rows, unchanged (their first 19 lines are byte-identical to the original file; a test
  checks this). They are a mix of fictional songs and a few real titles (for example Levels, Clair de Lune, Enter Sandman).
  History, from the git log and `model_card.md` section 3: the course starter file had **10 songs** (ids 1 to 10, commit `4462397`,
  "add starter app", 2025-12-04), and I **added 8 more** (ids 11 to 18: Heart on Ice, Love Yourz, First Day Out, Let Me Love You,
  Rock with You, Levels, Clair de Lune, Enter Sandman) in commit `955909d` (2026-10-08). **The source of the numeric values of
  these 18 rows was not recorded**, so this card does not claim one. The original rows mostly use irregular two-decimal values
  while the 50 real-song rows mostly use steps of 0.05, which shows the two sets were produced differently.
- **ids 19 to 68:** 50 real songs. Titles and artists were checked against web sources on 2026-11-07 (Wikipedia, label and
  streaming pages), with some well-known titles confirmed only loosely; featured credits are written as "ft." in the artist field and
  classical entries credit the composer because many recordings exist.

## The numbers for ids 19 to 68 are estimates (read this)
Energy, valence, acousticness, danceability (0 to 1) and tempo (BPM) are **approximate editorial estimates** made by the project
author with AI assistance (Claude Code) from general familiarity with each song. They are **not** Spotify data, not any other
official audio-feature data, and were not measured from audio. Tempo values are rounded and may differ from other sources.
Genre and mood are one subjective label each (for example "lofi" here also covers chill instrumental hip-hop, and "indie pop"
stands in for indie rock and folk). No lyrics, audio or cover art are stored.

## Corrections after review (rows 19 to 68 only)
After a data-quality review the following were corrected (the 18 original rows were not touched): Bad and Boujee (artist
"Migos ft. Lil Uzi Vert", valence 0.35 to 0.50), Gold Digger (artist "Kanye West ft. Jamie Foxx"), Sicko Mode (artist "Travis Scott ft.
Drake"), Feather (genre lofi to hip-hop), As It Was (genre indie pop to pop; mood stays moody), Wake Me Up (acousticness 0.04 to
0.20), Discreet Music (0.70 to 0.25), An Ending (Ascent) (0.60 to 0.30) and HUMBLE. (energy 0.62 to 0.75). Deliberately not
changed: Strobe's energy (0.60), Stayin' Alive's mood and Blinding Lights' genre. Evaluation results from before the corrections are
frozen in `evals/results/history/68_song_before_data_corrections/`. A test pins the corrected values.

## Known inconsistencies you should know about
- **rap vs hip-hop is an arbitrary label split.** Rap: J. Cole, Kendrick Lamar, Kanye West, 50 Cent. Hip-hop: Rod Wave, Eminem,
  JAY-Z, The Notorious B.I.G., Feather. The original rows already had this split. Matching is by label, so asking for "rap" does not
  return the hip-hop songs and vice versa.
- **Tempo is ambiguous for some songs** because of half-time and double-time feel (for example Lose Yourself 171, XO Tour Llif3 155,
  Sicko Mode 155, Take Five 172 in 5/4, Back in Black 94). Tempo is never scored.
- **Acousticness for ambient and electronic pieces is a rough guess** (for example Music for Airports 1/1 at 0.85); treat it as a
  guide only.
- **Explanation grounding has limits with real songs.** AI explanations are checked against the catalog (other songs and artists,
  years, albums, lyrics, false scores). A true real-world fact that is not in the data (for example a guest vocalist or composer) is
  accepted, and so is an invented influence ("in the style of Madonna"). The check cannot judge general truthfulness, which is why
  the engine's scoring reasons are always shown next to any AI sentence.

## Limits and bias
68 songs only; the 50 real songs outnumber the 18 originals about 3 to 1, so results are now mostly real songs; mostly English-language
and Western popular music; "ominous" has 2 songs and "focused" and "reflective" 3 each; one label per song; label-based matching.
Some single-word names (for example "Levels", "Feather", the artist "Mario") can collide with ordinary words in an AI explanation, so
the grounding check may reject a harmless explanation (the app then shows the engine's reasons instead). This is a class project,
not a music service.
