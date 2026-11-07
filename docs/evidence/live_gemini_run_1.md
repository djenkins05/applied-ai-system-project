# Live Gemini run 1 (successful)

Real call to the Gemini API through the MoodMix CLI. Output below is copied exactly as the
user captured it in their terminal; nothing was added or edited. Timestamp and exact date were
not recorded.

- **Command:** `GEMINI_MODEL=gemini-3.5-flash-lite python3 -m src.moodmix_cli "I'm studying for finals"`
- **Model used:** `gemini-3.5-flash-lite` (shown in the output as `model: gemini-3.5-flash-lite`)
- **Ranking mode:** `balanced` (default)
- **Interpreted preferences:** genres none; moods focused, chill; energy 0.25; valence and acousticness not set
- **Recommended songs:** Spacewalk Thoughts (2.63), Library Rain (2.53), Focus Flow (2.47), Midnight Coding (2.44), Clair de Lune (1.19), all scores out of 4.00

## Captured output

```text
AI-generated interpretation of your request (please check it):
  Your request:  I'm studying for finals
  Genres:        none
  Moods:         focused, chill
  Energy:        0.25
  Valence:       not set (skipped)
  Acousticness:  not set (skipped)
  Ranking mode:  balanced   (model: gemini-3.5-flash-lite)

================================================================
 Top 5 recommendations
================================================================

1. Spacewalk Thoughts  by Orbit Bloom
   Score: 2.63 / 4.00
   AI says: This chill ambient track provides a calm atmosphere.
   Engine reasons:
     - mood match: chill (+1.33)
     - energy 0.28 vs target 0.25 (+1.29)

2. Library Rain  by Paper Lanterns
   Score: 2.53 / 4.00
   AI says: It features a chill lofi style to help you relax.
   Engine reasons:
     - mood match: chill (+1.33)
     - energy 0.35 vs target 0.25 (+1.20)

3. Focus Flow  by LoRoom
   Score: 2.47 / 4.00
   AI says: This focused lofi song is designed to keep you on track.
   Engine reasons:
     - mood match: focused (+1.33)
     - energy 0.40 vs target 0.25 (+1.13)

4. Midnight Coding  by LoRoom
   Score: 2.44 / 4.00
   AI says: A chill lofi tune that brings a relaxed vibe.
   Engine reasons:
     - mood match: chill (+1.33)
     - energy 0.42 vs target 0.25 (+1.11)

5. Clair de Lune  by Claude Debussy
   Score: 1.19 / 4.00
   AI says: This classical piece creates a dreamy environment.
   Engine reasons:
     - energy 0.14 vs target 0.25 (+1.19)
```

## Errors observed before this run (earlier attempts, same command)

Captured diagnostics from the CLI. The HTTP status and Google's message are what the API returned;
no cause beyond that text is claimed.

| Model | Observed error | Message returned by the API (truncated by our 200-char limit where shown) |
|---|---|---|
| `gemini-2.5-flash` | HTTP 404 NOT_FOUND | "This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash ..." |
| `gemini-3.8-flash` | HTTP 504 DEADLINE_EXCEEDED | "Deadline expired before operation could complete." (seen with a 15 s client timeout) |
| `gemini-3.8-flash` | HTTP 503 UNAVAILABLE | "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later." |

## Reproduce

1. Put a valid key in `.env` as `GEMINI_API_KEY=...` (see `.env.example`).
2. From the repository root, run the command above (or leave `GEMINI_MODEL` unset: the default is now `gemini-3.5-flash-lite`).
3. Gemini's wording and the exact scores may differ between runs or model versions; this file records one real run only.
