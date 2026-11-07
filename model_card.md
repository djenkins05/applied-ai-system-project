# 🎧 Model Card: MoodMix AI

> **MoodMix AI extends my Module 3 recommender.** Sections 1 to 9 describe the original Module 3 recommender (named MatchVibe 1.0 at the time) and are kept as written. Sections 10 to 16 add the Gemini-powered MoodMix AI features, their evaluation, risks and my AI collaboration reflection.

## 1. Model Name

**MoodMix AI**

MoodMix AI is the full system: a Gemini-powered interpretation step, a Streamlit app, guardrails and feedback, wrapped around my original Module 3 recommender, **MatchVibe 1.0**. MatchVibe 1.0 is still the component that ranks songs, and sections 2 to 9 below describe it.

MatchVibe 1.0 is a small music recommender that checks if a song's vibe matches what you asked for.

---

## 2. Goal / Task

MatchVibe tries to answer one question: "Which songs should this person hear next?"

It takes a taste profile. The profile has favorite genres, favorite moods, and target levels for energy, valence (how upbeat), and acousticness. It scores every song in the catalog. Then it returns the top 5 songs. Each song comes with a short reason, like "genre match: pop (+1.0)".

It does not predict what a person will like in real life. It only finds songs that match what the person typed.

---

## 3. Data Used

- **Size:** 18 songs in `data/songs.csv`.
- **Origin:** The starter file had 10 songs. I added 8 more, so I could cover hip-hop, rap, trap, R&B, disco, EDM, classical, and metal.
- **Features per song:** title, artist, genre, mood, energy, tempo, valence, danceability, and acousticness.
- **Features the score actually uses:** genre, mood, energy, valence, and acousticness in the default `balanced` mode. Tempo and danceability are never scored. The original `classic` mode uses only genre, mood, and energy.
- **Genres:** 15 in total. 13 of them have only one song.
- **Moods:** 14 in total, like chill, happy, intense, and melancholic.
- **Limits:**
  - The catalog is tiny.
  - No song has energy between 0.55 and 0.74.
  - There is no country, Latin, K-pop, Afrobeats, folk, or reggae.
  - Two artists (LoRoom and Neon Echo) have 2 songs each.

---

## 4. Algorithm Summary

Each song gets points. The song with the most points wins.

The default mode is called **balanced**. No single signal can decide the ranking.

| Question | Points |
|---|---|
| Is the song's genre one of your favorites? | +1.0 |
| Is the song's mood one of your favorites? | +1.0 |
| How close is the song's energy to your target? | 0 to +1.0 |
| How close is the song's valence (how upbeat) to your target? | 0 to +0.5 |
| How close is the song's acousticness to your target? | 0 to +0.5 |

The best possible score is 4.0.

The "how close" points are `weight x (1 - the gap)`. A song with the exact value you want gets the full points. A song far away gets close to zero.

If a profile leaves out a target, the other weights are scaled up so the best possible score is still 4.0.

If two songs tie, the one with the closer energy goes first. If they still tie, the title decides.

### Other ranking modes

You can switch modes in `main.py` or with `--strategy`. Each mode splits the same 4 points differently. `classic` is my first formula. I kept it as an experiment. The Evaluation section below was run on the default `balanced` mode.

| Mode | Genre | Mood | Energy | Valence | Acousticness |
|---|---|---|---|---|---|
| `balanced` (default) | 1.0 | 1.0 | 1.0 | 0.5 | 0.5 |
| `classic` (original) | 2.0 | 1.0 | 1.0 | 0 | 0 |
| `genre_first` | 2.5 | 0.5 | 0.5 | 0.25 | 0.25 |
| `mood_first` | 0.5 | 2.0 | 0.5 | 0.75 | 0.25 |
| `energy_focused` | 0.5 | 0.5 | 2.0 | 0.5 | 0.5 |

`balanced` is my fix for the genre problem below. Genre is worth no more than any other signal, so a good mood and energy fit can beat a genre-only match. In the Genre Trap test, it put a calm song first instead of Enter Sandman. For Happy Pop, it moved "Rooftop Lights" above "Gym Hero". The tradeoffs of every mode are in Experiment 2 in the README.

---

## 5. Observed Behavior / Biases

These come from running `python src/main.py` in the default `balanced` mode. The full output is in the README.

### Genre no longer decides the ranking

In balanced mode, a genre match is worth 1 point. A song needs more than the right label to win.

The *Genre Trap* profile shows this. It asked for metal, but also for calm, quiet music (energy 0.20). The calm song "Spacewalk Thoughts" came first with 2.83 points. "Enter Sandman" is not in the top 5.

In my first formula (`classic`), genre was worth 2 points. "Enter Sandman" came first with 2.23 points, even though its energy is 0.97. That is why I changed the default.

### Why "Gym Hero" still shows up for Happy Pop fans

"Gym Hero" is a loud workout song. It is a strange pick for someone who wants happy pop. But its numbers look a lot like happy pop. It is upbeat (valence 0.77), and its energy (0.93) is close to the 0.80 target. It also carries the plain "pop" label.

| Song | Genre | Mood | Energy | Valence | Acousticness | Score |
|---|---|---|---|---|---|---|
| Sunrise City | pop (+1.0) | happy (+1.0) | +0.98 | +0.48 | +0.49 | **3.95** |
| Rooftop Lights | indie pop (no point) | happy (+1.0) | +0.96 | +0.49 | +0.43 | **2.88** |
| **Gym Hero** | **pop (+1.0)** | intense (no point) | +0.87 | +0.48 | +0.42 | **2.78** |

"Rooftop Lights" sounds the most like happy pop. It beats "Gym Hero" by only 0.10 points. "Rooftop Lights" gets its label point from its mood. "Gym Hero" gets its label point from the genre. The system sees "indie pop" and "pop" as two unrelated things, so "Rooftop Lights" gets nothing for its genre.

Only two songs have the plain "pop" label. Once "Sunrise City" is used up, "Gym Hero" is the only other song that can get the genre point. In `classic` mode, that point was worth 2, and "Gym Hero" ranked #2 above "Rooftop Lights". Now it ranks #3.

### The same middle songs show up everywhere

"Midnight Coding" is in the top 5 for 9 of the 12 profiles that run. "Love Yourz" is in 6 lists. "Let Me Love You" is in 5.

These songs have middle values for energy, valence, and acousticness. A middle song is never far from any target. So it collects decent points for almost any profile. In `classic` mode, "Midnight Coding" was in 7 lists. Scoring valence and acousticness gave middle songs more ways to score.

### Other patterns I found

- **Small genres get small lists.** A jazz fan (Dead Center) gets one strong match. "Coffee Shop Stories" scores 3.57. The other four songs are filler near 1.7 to 1.8. A lofi fan gets three real matches.
- **Scores bunch together.** The gap between #1 and #5 averages 1.63 across 8 test profiles. In `classic` mode it was 2.25. So near-ties are more common.
- **Filter bubble.** The top 5 for `low_energy` has three lofi songs, and two come from LoRoom. Every mode returns about 4 different genres in 5 songs. Changing the weights does not add variety.
- **Exact spelling needed.** "edm" does not match "EDM". "hip-hop", "rap", and "trap" count as three unrelated genres.
- **Energy gap is not fair to everyone.** A target of 0.0 can never score above 3.86. A target in the middle can get closer to 4.0. So scores are not comparable between people.
- **No "I don't know".** When nothing matches (*Wrong Case*, *Unknown Tastes*), the system still shows 5 songs. Nothing tells the user that no genre or mood matched.
- **Bad input is hidden, not caught.** In *Impossible Energy*, every energy line is negative, like "+-0.82". But the totals stay above zero, because valence and acousticness add points. An empty profile still crashes the program.
- **Energy and acousticness still move together.** In this catalog the correlation is -0.92. In *Calm Genre, Max Energy*, "Storm Runner" is loud but not acoustic, so it earns only +0.08 for acousticness. A listener who wants loud acoustic music is still not served.

---

## 6. Evaluation Process

I tested 13 profiles by running `python src/main.py`. I read the top 5 songs for each one. All of the output is in the README.

- **4 normal listeners:** `my_taste` (reflective hip-hop), `high_energy` (EDM, metal, trap), `low_energy` (classical, ambient, lofi), and `happy_pop` (pop, happy, energy 0.8).
- **9 trick listeners:** built to confuse the system.
  - *Sad Banger*: high energy but a sad mood.
  - *Calm Genre, Max Energy*: calm genres but maximum energy.
  - *Genre Trap*: metal, but quiet.
  - *Impossible Energy*: energy of -1.
  - *Wrong Case*: wrong capital letters.
  - *Unknown Tastes*: genres not in the catalog.
  - *Likes Everything*: every genre and mood.
  - *Empty Prefs*: no tastes at all.
  - *Dead Center*: energy 0.5 with one jazz match.

For normal listeners, I asked, "Would a person agree with these songs?" For trick listeners, I asked, "Does the system notice a problem, or does it quietly return something?"

I also ran two experiments, with my first formula (`classic`) as the baseline.

- **Experiment 1:** I cut the genre weight in half (2.0 to 1.0) and doubled the energy weight (1.0 to 2.0). The top 5 stayed the same for the three original normal listeners. *Genre Trap* finally put a calm song first. But now energy could beat genre and mood, so the bias just moved. The doubled energy weight also made the below-zero scores worse. I put the weights back.
- **Experiment 2:** I added valence and acousticness and built five ranking modes. I measured each one on 8 profiles. `balanced` fixed Genre Trap and the Gym Hero problem, so I made it the default. `genre_first` kept the genre problem. `mood_first` ignored energy requests. `energy_focused` washed out taste. The full tradeoffs are in the README.

### What surprised me

- **Likes Everything and Unknown Tastes still look the same.** They get the same 5 songs in the same order. Only the scores differ, by exactly 2.0. That is the genre point plus the mood point.
- **A listener with no matches gets almost the `my_taste` list.** *Unknown Tastes* shares 4 of its 5 songs with `my_taste`. Their number targets are close. When no label matches, the numbers decide.
- **Opposite energy, same top songs.** *Calm Genre, Max Energy* and `low_energy` both put "Spacewalk Thoughts" and "Clair de Lune" on top. One wants silence and one wants max energy. Genre and mood points (2 of 4) drown out the energy wish.
- **A valence target helps a little.** For *Sad Banger*, "Enter Sandman" (loud, valence 0.22) now makes the top 5. But "Levels" (valence 0.94) still wins, because genre, energy, and acousticness carry it.
- **The default hides a bug.** *Impossible Energy* has negative energy points, but the totals look normal.
- **Typos matter.** A lowercase "edm" hides every EDM song.
- **Empty is worse than everything.** "Likes Everything" works. "Empty Prefs" crashes.

### Profile pairs

**Normal listeners**

- **`high_energy` vs `low_energy`:** No songs in common. One list is loud and electric. The other is soft and acoustic. This is the clearest sign the system works.
- **`my_taste` vs `high_energy`:** Only "First Day Out" is shared. It is trap and very loud, so it fits both.
- **`my_taste` vs `low_energy`:** Only "Midnight Coding" is shared. It is gentle, and its numbers are close to what `my_taste` wants. It shows up for the numbers, not for taste.
- **`happy_pop` vs `high_energy`:** Two songs are shared, "Gym Hero" and "Sunrise City". For `high_energy` both are a good fit. They are loud and upbeat. For `happy_pop`, "Gym Hero" gets in on the pop label and the numbers.
- **`happy_pop` vs `low_energy`:** Nothing in common. That is what I expect for pop vs classical.

**Trick listeners**

- **Sad Banger vs `high_energy`:** Both want energy 0.95, and three songs are shared ("Levels", "First Day Out", "Enter Sandman"). Sad Banger adds sad moods, so two quiet sad songs take places 2 and 3. "Enter Sandman" is the closest thing to a sad banger, but it sits at #4. The system adds up wishes. It does not combine them.
- **Calm Genre, Max Energy vs `low_energy`:** 4 of 5 songs are shared, and the top two are the same. Only the loud filler differs. "Storm Runner" is #5 for Calm Genre, Max Energy.
- **Genre Trap vs `high_energy`:** "Enter Sandman" is #3 for `high_energy` and fits. It is not in the Genre Trap top 5, which is right for someone who wants calm music. Genre Trap's list shares 4 songs with the calm `low_energy` list.
- **Impossible Energy vs `happy_pop`:** Both are pop and happy, and both put "Sunrise City", "Rooftop Lights", and "Gym Hero" on top in that order. The only difference is the energy target. The impossible one still works, and only places 4 and 5 change.
- **Wrong Case vs `high_energy`:** Same taste, different capital letters. `high_energy` gets 3.92 for "Levels". Wrong Case gets nothing above 1.80.
- **Unknown Tastes vs `my_taste`:** Unknown Tastes has no matches. It shares 4 songs with `my_taste`, including "Love Yourz" at #1. So the numbers are the fallback.
- **Likes Everything vs Unknown Tastes:** Same 5 songs, same order. When everything matches, the labels stop meaning anything.
- **Likes Everything vs Empty Prefs:** Listing everything works. Listing nothing crashes. That is backwards for a brand new user.
- **Dead Center vs Unknown Tastes:** Both want energy 0.5. One jazz match moves "Coffee Shop Stories" to #1. Places 2 to 5 are the same four songs as places 1 to 4 for Unknown Tastes. One match moves one song, and the numbers do the rest.

---

## 7. Intended Use and Non-Intended Use

### Intended use

- Classroom learning. It shows how a content-based recommender turns data into a ranking.
- Practice with scoring rules, test profiles, and bias checks.
- Small demos where a person types in their tastes and gets 5 songs and the reasons why.

### Not intended for

- **Real music apps.** The catalog has 18 songs. That is far too small.
- **Judging anyone's taste.** A low score only means "does not match the labels".
- **Serious decisions.** For example, picking which artists get promoted.
- **Users outside the catalog.** If your music is not in these 15 genres, the results are just energy matches.
- **Learning from listening history.** It has none. It does not know who you are or what you skipped.

---

## 8. Ideas for Improvement

1. **Test the modes with real listeners.** I picked every weight by hand. Next I would ask people which top 5 they like best. Then I could choose the weights from real answers instead of my own guesses.
2. **Add variety and fix labels.** Limit the top 5 to 2 songs per genre or artist. Group related genres, like hip-hop, rap, and trap. Lowercase all text before matching. Give partial credit for close moods.
3. **Validate input and add songs.** Clamp energy points so they never go below 0. Reject empty profiles with a clear message. Add songs in the empty energy range (0.55 to 0.74) and for the genres with only one song.

---

## 9. Personal Reflection

### My biggest learning moment

My biggest learning moment was seeing how hard it is to build a scoring formula without too much bias. Every weight I picked favored someone. When I made genre worth less, energy took over. The bias did not go away. It just moved.

Building five ranking modes made this clearer. Each mode just picks which bias you accept. `balanced` fixed the Genre Trap and "Gym Hero" problems. But it also made the scores bunch together. A few middle-valued songs now show up everywhere. "Midnight Coding" is in 9 of the 12 lists that run. And no mode added variety.

I also learned that real recommenders probably need a lot of data to find the best formula. I picked every weight by hand, using 18 songs. To do better, I would need real listeners to tell me which top 5 they like.

### How AI tools helped me, and when I double-checked them

AI helped most when I wanted to test something. It helped me build the trick profiles and run them quickly. It helped me write tests. It also helped me work out the scoring formula and try the ranking modes.

I still had to check its work, because some of it was wrong:

- One test it wrote used a song that matched genre and mood. So the test did not catch the negative-score bug it was meant to catch. Running the tests showed it.
- The run command in the README did not work. I only found out by running it.
- Some comparisons in this model card were worded too loosely. For example, one said two lists were "the same" when only two songs overlapped.
- A new default mode could only reach 3.5 out of 4.0 for one kind of profile. A check on the score math found it.

The AI could write the code and the explanations fast. But I had to be the one to run everything and confirm the claims matched what the program printed.

### What surprised me about simple algorithms

I was surprised by how much a simple formula can feel like it "knows" me. I only typed in a few inputs. Depending on the profile, the top 5 songs still felt like songs I would really listen to.

Then the trick profiles showed the other side. A listener who likes everything and a listener who matches nothing got the same five songs in the same order. The system was only adding up points. It never understood the music.

### What I would try next

I would add more songs first. The catalog has gaps in energy, and 13 of the 15 genres have only one song. Then I would fine-tune the formula so there is less bias. I would start with the fixes in the Ideas for Improvement section:

- Test the modes with real listeners.
- Limit how many songs from one genre or artist show up.
- Catch bad input, like empty profiles and impossible energy targets.

---

# Part 2: MoodMix AI extension

## 10. The integrated AI feature

**What Gemini does.** Gemini reads a free-text description ("I'm studying for finals") and returns structured
preferences: up to five genres and moods from the catalog, and target energy, valence and acousticness between 0 and 1. It
can also write one short sentence per recommended song explaining the fit.

**What Gemini does not do.** It never ranks or scores songs. The original recommender in `src/recommender.py`
(unchanged) is the only component that ranks, and its scoring reasons are always shown next to any AI sentence.

**How it is constrained.**
- The request asks for JSON that matches a schema built from the catalog's own genres and moods, with temperature 0.
- The user's text is sent inside delimiter tags and the prompt tells the model to treat it as data.
- Gemini's answer is untrusted: `parse_preferences` keeps only genres and moods that exist in the catalog, clamps numbers
  to 0 to 1, and rejects an answer with nothing usable. It does not fall back to defaults.
- Explanations are checked against the engine's own facts (`src/explain.py`); an explanation that names another song or
  artist, invents a year, album or score, or contains a link, markup or instructions is dropped and the engine's reasons
  are shown instead.

**Other behaviour added around it.**
- A manual-only mode (no Gemini call) and an explicit, user-triggered manual fallback after a failure.
- Like/dislike feedback in the Streamlit app. It adjusts the preferences passed to the engine and excludes disliked
  songs for the session. It does not retrain Gemini and does not change the scoring rules.

**Data.** The catalog is unchanged (18 songs, 15 genres, 14 moods). The user's text is sent to Google's Gemini API, and for
explanations so are the facts of the recommended songs (title, artist, genre, mood, audio features, score, reasons).

## 11. Guardrails and reliability

- **Input screening** (`src/guardrails.py`): empty, over 500 characters, symbols-only and repeated-character input are
  rejected before any API call, along with clear prompt-injection attempts (override instructions, reveal hidden prompts,
  impersonate system or developer roles, bypass safeguards). The detector is deliberately narrow so requests like
  "I need music to ignore distractions" still work; tests cover both malicious and legitimate wording.
- **Failure handling** (`src/llm.py`, `src/pipeline.py`): timeouts and one bounded retry; HTTP 400, 401/403, 404, 429 and
  5xx are classified separately with a sanitized diagnostic (status code and a redacted message, never keys or request text).
- **Fallback:** if Gemini fails, the app shows a friendly error and offers manual preferences. It does not create
  recommendations from defaults.
- **Reliability log** (`src/reliability_log.py`): opt-in; records event type, error category, HTTP status, latency, input
  length and guardrail category. It never records user text, hashes of it, or keys.
- **Transparency:** the interface labels AI-generated content and shows the engine's reasons.

## 12. Evaluation (what was actually run)

| Evidence | Result |
|---|---|
| Automated tests (`python3 -m pytest`; Gemini always mocked, network blocked) | 501 passed, 3 xfailed (the 3 are known-bug tests from Module 3), run 2026-11-07 |
| Comprehensive harness (`python evals/run_eval.py`, scripted or canned Gemini, no network) | 114/114 new scenarios and 647/647 checks passed across 9 categories (recommendation correctness, mock mood scenarios, invalid input, prompt structure, malformed responses, API failures, manual fallback, feedback, grounding); identical on rerun; saved in `evals/results/eval_report.txt` and `.json`. Plus one documented finding (below) |
| Guardrail and reliability cases (`python evals/run_guardrails.py`, 43 fixed cases, simulated Gemini) | 43/43 passed; saved in `evals/results/guardrails.txt` and `.json`; identical across reruns |
| One real Gemini run through the CLI (`gemini-3.5-flash-lite`) | succeeded; output in `docs/evidence/live_gemini_run_1.md` |
| Errors observed with real Gemini before that run | HTTP 404 for `gemini-2.5-flash` (the API said it is no longer available to new users), then HTTP 504 and HTTP 503 for `gemini-3.8-flash`; causes of the 503/504 were not established |

**A finding about feedback.** My first expectation for liking a jazz song (`H1-like-new-genre`) was that it would reach the top 3. It
moved from #5 (score 1.78) to #4 (score 3.85): four songs already matched both of the user's chosen genres and moods and scored
3.84 to 3.94, so one like could not overtake all of them. The first run reported this as a failure (113/114 scenarios). After review
I replaced the scenario with checks of the intended behavior (the liked song's score and rank improve, the result is deterministic,
and the ranking equals the original engine on the adjusted preferences) and kept the original top-3 expectation in the report as a
documented finding with its observed numbers. I did not hard-code rank #4, and I did not change the recommendation algorithm. The
lesson for users is that feedback influences rankings but does not guarantee a specific top-k position, because other songs may still
be stronger matches. This is a property of the tiny catalog and the feedback rules, not something I tuned away.

**Explanation grounding, honestly.** On 25 sentences labelled independently of the validator (within its documented coverage:
fabricated metadata, unsafe text and faithful sentences), it rejected all 19 bad ones and accepted all 6 faithful ones. On 6
probes outside that coverage (plausible false wording, vague claims, and metadata not in its list such as "the 90s" or "won
awards") it accepted all 6. The checks catch fabricated metadata, not general untruth, and they do not guarantee that an
explanation is correct. The labelled set is small and constructed, so these counts are a regression check, not an accuracy estimate.

**Metrics I chose not to report.** Precision, recall or NDCG against human relevance, success rates, average scores, diversity
percentages and latency would be misleading here: 18 songs (13 of 15 genres with one song), many score ties, scripted Gemini and
hand-written labels. Reproduction commands: `docs/evidence/reproduce.md`.

**What was not measured.** There is no measurement of how accurately Gemini interprets real inputs, no user study, and no
baseline-versus-AI comparison. The guardrail cases use a simulated Gemini, so they test my code paths, not the real
model's behaviour on hostile input. The grounding checks are heuristics. The feedback constants (genre/mood weights, 0.30
like step, 0.15 dislike step) were chosen by hand and not tuned with listeners. The Streamlit app has been tested with
Streamlit's `AppTest` and a mocked Gemini, and a headless start-up check; I captured four screenshots of a real-Gemini session
through the app (Offline demo AI off; `docs/evidence/screenshots/01` to `04`), but no recording or transcript.

## 13. Limitations and risks specific to the AI feature

- **Misreading and hallucination.** Gemini may map a mood to the wrong labels or energy level. Validation guarantees
  the labels exist, not that they are right. The interpretation panel lets the user check and edit.
- **Prompt injection.** Defenses are layered (narrow input screening, delimited prompt, schema-constrained output,
  validation, explanation grounding), but none is complete. A reworded attack could pass screening and still produce only
  catalog labels, which limits the damage.
- **Bias in interpretation.** The model's idea of what "studying" or "heartbreak" sounds like reflects its training data and
  may not fit every culture or language. The 18-song catalog (15 genres, mostly one song each) also limits what can be
  recommended, and the Module 3 biases in section 5 still apply.
- **Unverifiable explanations.** The checks catch concrete false claims (other songs, scores, years) but cannot prove a vague
  sentence such as "perfect for rainy days".
- **Dependence on a third party.** During development the default model was retired for new users and the replacement was
  intermittently overloaded. The app depends on model availability, and model names change.
- **Session-only feedback.** Feedback is not saved and is not learned from across sessions.

## 14. Ethical considerations

- **Privacy.** Text typed into the app is sent to Google's Gemini API. Do not enter sensitive personal information.
  The app does not store text, and the reliability log excludes it.
- **Transparency and over-trust.** AI-written content is labelled, scoring reasons are always visible, and the interface says
  that feedback does not retrain the AI, so a user can see why a song was recommended.
- **Misuse.** Injection attempts are rejected with a clear message rather than silently ignored.
- **Fairness and scope.** This is not a music service. The tiny catalog cannot represent anyone's real taste, and a low score
  means only "does not match the labels".

## 15. AI collaboration reflection

I used Claude Code throughout development to help plan, implement and test MoodMix AI. MoodMix AI itself is not an agentic
application. I learned that AI suggestions still need careful review: some worked well, others had to change to fit my project.

**A suggestion I accepted.** My first real Gemini command only reported `llm_error`. Claude found that HTTP 400, 404 and
other errors fell through to one generic error class with no status code, and added separate error classes and a sanitized
diagnostic. The next run showed `HTTP 404 NOT_FOUND`: the default model was no longer available to new users. I looked up the
current model in Google AI Studio, chose `gemini-3.5-flash-lite`, and the real run worked. I trusted the fix because mocked
tests covered the classification and my live run confirmed the cause.

**A suggestion I rejected and had revised.** The Phase 3 plan logged a short hash of each request. I rejected that: reliability
logs hold only operational metadata (event, status, latency, input length), with no prompt text and no hashes, and tests check
this. I also narrowed the prompt-injection detector so ordinary requests such as "ignore distractions" still work.

**Testing an assumption.** My feedback evaluation expected a liked song to reach the top three. The results showed that
feedback raised its score and rank (#5 to #4) without guaranteeing a top-three position. Rather than change the recommendation
algorithm to satisfy the test, I revised the evaluation to measure the intended behavior and kept the original failure as a
documented finding (`H1-finding-top3-not-guaranteed`).

**What I took from this.** Testing assumptions, protecting existing functionality, and treating AI as a development assistant
rather than automatically correct. The full log is in `ai_interactions.md`. For my Module 3 notes on AI use, see section 9.

## 16. Intended and non-intended use (MoodMix AI)

- **Intended:** a classroom demonstration of combining an LLM interpretation step with a transparent rule-based
  recommender, with guardrails, fallbacks and feedback, over a tiny catalog.
- **Not intended for:** real music apps, any decision about people or artists, or handling sensitive text. Sections 7 and 13 apply.
