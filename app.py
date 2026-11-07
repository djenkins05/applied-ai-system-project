"""
MoodMix AI: Streamlit front end.

Run from the repository root:   streamlit run app.py

This file is UI only: widgets, layout and session state. All logic lives in src/app_controller.py
(actions), src/feedback.py (like/dislike rules) and the existing pipeline/recommender. Gemini is
contacted only by "Find music" and by the explicit "Ask Gemini to explain" button; voting, editing
preferences, changing the ranking mode or the number of songs never call the API.
"""

import os
from pathlib import Path
from typing import Any

import streamlit as st

from src.app_controller import (
    MAX_K, MIN_K, MODE_AI, MODE_MANUAL, ORIGIN_AI, ORIGIN_EDITED, ORIGIN_MANUAL,
    AppController, AppState, prefs_to_manual,
)
from src.fallback import ManualPreferences
from src.feedback import DISLIKE, HOW_FEEDBACK_WORKS, LIKE
from src.guardrails import friendly_warnings
from src.llm import API_KEY_ENV, MAX_INPUT_CHARS, GeminiClient
from src.mock_llm import MockGemini
from src.recommender import MAX_SCORE, STRATEGIES, load_songs
from src.ui_theme import CSS, chips_html, hero_html, score_bar_html, song_head_html

SONGS_CSV = Path(__file__).resolve().parent / "data" / "songs.csv"
EXAMPLES = ("I'm studying for finals", "I need motivation to work out", "Rainy night, feeling reflective")
MODE_LABELS = {MODE_AI: "Describe it (Gemini AI)", MODE_MANUAL: "Manual preferences"}
STRATEGY_BLURBS = {
    "balanced": "No single signal outweighs the others (default).",
    "classic": "The original formula: genre counts double.",
    "genre_first": "Genre matters most.",
    "mood_first": "Mood matters most.",
    "energy_focused": "Energy closeness matters most.",
}

st.set_page_config(page_title="MoodMix AI", page_icon="🎵", layout="wide")


# --- Setup helpers ---------------------------------------------------------------

@st.cache_data
def load_catalog():
    return load_songs(str(SONGS_CSV))


def get_state() -> AppState:
    if "app" not in st.session_state:
        st.session_state["app"] = AppState()
    return st.session_state["app"]


def get_client() -> Any:
    """Test client if injected, else the offline demo mock, else real Gemini (cached per session)."""
    ss = st.session_state
    if ss.get("_test_client") is not None:
        return ss["_test_client"]
    if ss.get("demo_mode"):
        if "_demo_client" not in ss:
            ss["_demo_client"] = GeminiClient(client=MockGemini(), model="demo-mock")
        return ss["_demo_client"]
    if "_gemini_client" not in ss:
        ss["_gemini_client"] = GeminiClient()     # reads GEMINI_API_KEY lazily; never displayed
    return ss["_gemini_client"]


def sync_widget_keys(state: AppState) -> None:
    """
    Keep widget values stable across reruns. Streamlit forgets a widget's value when it is not
    rendered (e.g. in the other mode), so any missing key is restored from AppState, and all keys
    reload when the controller bumps prefs_version (new interpretation, restore, reset).
    """
    ss = st.session_state
    force = ss.get("_loaded_version") != state.prefs_version
    manual = prefs_to_manual(state.base_prefs) if state.base_prefs else ManualPreferences()
    defaults = {
        "w_text": state.draft_text,
        "w_genres": manual.genres,
        "w_moods": manual.moods,
        "w_energy": 0.5 if manual.energy is None else manual.energy,
        "w_use_valence": manual.valence is not None,
        "w_valence": 0.5 if manual.valence is None else manual.valence,
        "w_use_acoustic": manual.acousticness is not None,
        "w_acoustic": 0.5 if manual.acousticness is None else manual.acousticness,
    }
    for key, value in defaults.items():
        if force or key not in ss:
            ss[key] = value
    for key, value in (("mode_radio", state.mode), ("strategy_select", state.strategy),
                       ("k_slider", state.k)):
        if force or key not in ss:
            ss[key] = value
    ss["_loaded_version"] = state.prefs_version


def widgets_to_manual() -> ManualPreferences:
    ss = st.session_state
    return ManualPreferences(
        genres=list(ss["w_genres"]), moods=list(ss["w_moods"]),
        energy=round(float(ss["w_energy"]), 2),
        valence=round(float(ss["w_valence"]), 2) if ss["w_use_valence"] else None,
        acousticness=round(float(ss["w_acoustic"]), 2) if ss["w_use_acoustic"] else None,
    )


def same_prefs(a: ManualPreferences, b: ManualPreferences) -> bool:
    return (sorted(a.genres), sorted(a.moods), a.energy, a.valence, a.acousticness) == \
           (sorted(b.genres), sorted(b.moods), b.energy, b.valence, b.acousticness)


# --- Callbacks (run before the script reruns, so widget keys may be set here) --------------

def cb_take_manual(ctl: AppController, state: AppState) -> None:
    ctl.switch_mode(state, MODE_MANUAL)
    st.session_state["mode_radio"] = MODE_MANUAL


def cb_reset_all(ctl: AppController, state: AppState) -> None:
    ctl.reset_all(state)


def cb_example(state: AppState, text: str) -> None:
    st.session_state["w_text"] = text
    state.draft_text = text


# --- Page sections ------------------------------------------------------------------------------

def render_sidebar(ctl: AppController, state: AppState) -> None:
    ss = st.session_state
    with st.sidebar:
        st.title("🎵 MoodMix AI")
        st.radio("How do you want to choose?", [MODE_AI, MODE_MANUAL],
                 format_func=MODE_LABELS.get, key="mode_radio")
        st.selectbox("Ranking mode", list(STRATEGIES), key="strategy_select",
                     format_func=lambda s: s.replace("_", " "))
        weights = STRATEGIES[ss["strategy_select"]]
        st.caption(STRATEGY_BLURBS[ss["strategy_select"]] + " Points: " +
                   ", ".join(f"{name} {w:g}" for name, w in weights.items() if w))
        st.slider("Songs to show", MIN_K, ctl.max_k, key="k_slider")
        with st.expander("AI and demo settings"):
            st.checkbox("Include Gemini explanations with each new request", value=True, key="explain_toggle")
            st.checkbox("Offline demo AI (canned answers, not real Gemini)", value=False, key="demo_mode")
        st.divider()
        st.button("Reset feedback", key="reset_feedback", on_click=ctl.reset_feedback, args=(state,),
                  disabled=len(state.feedback) == 0, help="Clears likes/dislikes and restores all songs.")
        st.button("Reset everything", key="reset_all", on_click=cb_reset_all, args=(ctl, state))
        st.divider()
        if ss.get("_test_client") is not None or ss.get("demo_mode"):
            st.caption("AI source: offline demo / test client (no Gemini call).")
        else:
            client = get_client()
            found = "found" if os.environ.get(API_KEY_ENV) else "missing"
            st.caption(f"Gemini API key: {found}. Model: {client.model}.")


def render_pref_controls(ctl: AppController) -> None:
    st.multiselect("Genres", ctl.options["genres"], key="w_genres")
    st.multiselect("Moods", ctl.options["moods"], key="w_moods")
    st.slider("Energy (0 calm, 1 intense)", 0.0, 1.0, step=0.01, key="w_energy")
    col_a, col_b = st.columns(2)
    with col_a:
        st.checkbox("Use positivity (valence)", key="w_use_valence")
        st.slider("Valence (0 sad, 1 joyful)", 0.0, 1.0, step=0.01, key="w_valence",
                  disabled=not st.session_state["w_use_valence"])
    with col_b:
        st.checkbox("Use acousticness", key="w_use_acoustic")
        st.slider("Acousticness (0 electronic, 1 acoustic)", 0.0, 1.0, step=0.01, key="w_acoustic",
                  disabled=not st.session_state["w_use_acoustic"])


def render_error(ctl: AppController, state: AppState) -> None:
    err = state.error
    if err is None:
        return
    lines = [line.strip() for line in (err.error or "").split("\n") if line.strip()]
    headline = lines[0] if lines else "Something went wrong."
    if err.error_kind == "input":
        st.warning(headline)
    else:
        st.error(headline)
    details = [line for line in lines[1:] if line.startswith("Diagnostic:")]
    extras = [line for line in lines[1:] if not line.startswith("Diagnostic:")
              and not line.startswith("You can still")]
    for line in extras:
        st.caption(line)
    if details:
        with st.expander("Technical details (sanitized)"):
            st.code("\n".join(details))
    if err.fallback_available and state.mode == MODE_AI:
        st.button("Use manual preferences instead", key="use_manual_fallback",
                  on_click=cb_take_manual, args=(ctl, state))


def render_interpretation(ctl: AppController, state: AppState) -> None:
    prefs = state.base_prefs
    if prefs is None:
        return
    if state.origin == ORIGIN_MANUAL:
        st.subheader("Your preferences")
    else:
        st.subheader("How I read your request")
        badge = ":orange-badge[AI-generated: please check it]" if state.origin == ORIGIN_AI \
            else ":blue-badge[AI-generated, edited by you]"
        st.markdown(f"{badge}  Gemini inferred these preferences; you can change them below.")

    def value(number):
        return "not set" if number is None else f"{number:.2f}"
    st.markdown(chips_html([
        ("Genres", ", ".join(prefs.genres) or "none"), ("Moods", ", ".join(prefs.moods) or "none"),
        ("Energy", value(prefs.target_energy)), ("Valence", value(prefs.target_valence)),
        ("Acousticness", value(prefs.target_acousticness))]), unsafe_allow_html=True)
    notes = friendly_warnings(prefs)
    if notes:
        st.info("\n".join(f"- {note}" for note in notes))
    with st.expander("Edit these preferences (results update instantly, no AI call)", expanded=True):
        render_pref_controls(ctl)
        if state.ai_prefs is not None and state.origin != ORIGIN_AI:
            if st.button("Restore Gemini's original reading", key="restore_ai"):
                ctl.reset_to_ai(state)
                st.rerun()


def render_results(ctl: AppController, state: AppState, client: Any) -> None:
    outcome = state.outcome
    if outcome is None:
        return
    recs = outcome.result.recommendations
    st.subheader(f"Top {len(recs)} picks")
    st.caption(f"Ranking mode: {state.strategy.replace('_', ' ')}. "
               "Scores come from the rule-based engine, out of 4.00. Most songs in the catalog are real; "
               "their energy, valence and acousticness values are approximate estimates, not Spotify data.")
    if outcome.message:
        st.warning(outcome.message)
    if state.notice:
        st.caption(state.notice)

    for rec in recs:
        song_id = rec.song["id"]
        vote = state.feedback.get(song_id)
        with st.container(border=True, key=f"card_{song_id}"):
            st.markdown(song_head_html(rec.rank, rec.song["title"], rec.song["artist"], rec.song["genre"]),
                        unsafe_allow_html=True)
            liked = "  :green-badge[you liked this]" if vote == LIKE else ""
            st.markdown(f":gray-badge[{rec.song['genre']}] :gray-badge[{rec.song['mood']}]{liked}")
            st.markdown(score_bar_html(rec.score, MAX_SCORE), unsafe_allow_html=True)
            like_col, dislike_col, _ = st.columns([2, 2, 5])
            like_col.button("👍 Liked" if vote == LIKE else "👍 Like", key=f"like_{song_id}",
                            on_click=ctl.vote, args=(state, song_id, LIKE),
                            type="primary" if vote == LIKE else "secondary",
                            help=f"Like {rec.song['title']}", use_container_width=True)
            dislike_col.button("👎 Disliked" if vote == DISLIKE else "👎 Dislike", key=f"dislike_{song_id}",
                               on_click=ctl.vote, args=(state, song_id, DISLIKE),
                               help=f"Dislike {rec.song['title']}", use_container_width=True)
            with st.container(key=f"engine_{song_id}"):
                st.markdown("**Why it scored this (rule-based engine):**\n" +
                            "\n".join(f"- {reason}" for reason in rec.reasons))
            why = state.ai_why.get(song_id)
            if why:
                with st.container(key=f"aiwhy_{song_id}"):
                    st.markdown(f"🤖 *AI explanation (written by Gemini, checked against the data):* {why}")

    if state.mode == MODE_AI and state.request_text:
        if st.button("Ask Gemini to explain these picks", key="explain_now"):
            with st.spinner("Asking Gemini for explanations…"):
                ctl.request_explanations(state, client)
            st.rerun()

    if outcome.excluded:
        st.markdown("**Removed for you (disliked this session):**")
        for song in outcome.excluded:
            c1, c2 = st.columns([8, 2])
            c1.write(f"{song['title']}, {song['artist']}")
            c2.button("Undo", key=f"undo_{song['id']}", on_click=ctl.undo, args=(state, song["id"]))

    with st.expander("What your feedback changed", expanded=len(state.feedback) > 0):
        st.caption(HOW_FEEDBACK_WORKS)
        if len(state.feedback) == 0:
            st.write("No feedback yet. Like or dislike a song to see how the preferences shift.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Liked", len(state.feedback.liked_ids))
            m2.metric("Disliked", len(state.feedback.disliked_ids))
            m3.metric("Excluded now", len(outcome.excluded))
            for note in outcome.adjusted.notes:
                st.write(f"- {note}")
            if outcome.excluded:
                st.write(f"- Excluding {len(outcome.excluded)} disliked song(s) from the results.")
            if not outcome.adjusted.notes and not outcome.excluded:
                st.write("Your votes did not change any preference yet.")
            st.write("Without your feedback the top picks would be: " + ", ".join(outcome.baseline_titles))


def render_empty_state() -> None:
    with st.container(border=True, key="hero_empty"):
        st.markdown("**How it works**")
        st.markdown("1. Describe your mood, or pick manual preferences in the sidebar.\n"
                    "2. Check how the request was read, and edit it if needed.\n"
                    "3. Like or dislike songs and watch the picks adapt.")
        st.caption("On a phone, open the sidebar (top left) for ranking mode and settings. "
                   "Nothing is recommended until you ask.")


def render_about() -> None:
    with st.expander("About this app: how AI is used, and its limits"):
        st.markdown(
            "- **What the AI does:** Gemini turns your text into preferences and can write a short "
            "explanation per song. Parts of this page are AI-generated and are labelled.\n"
            "- **What it does not do:** it does not rank songs. A transparent rule-based engine "
            "scores every song; its reasons are always shown.\n"
            "- **Checks:** your text is screened before it is sent; Gemini's answer is validated "
            "against the catalog; AI explanations that mention anything not in the data are dropped.\n"
            "- **Limits:** the catalog has 68 songs and 15 genres (18 from my Module 3 project plus 50 real "
            "songs whose ratings are approximate estimates, not Spotify data), matching is label-based, "
            "there is no listening history, and the AI can misread a mood. This is a class project, not a "
            "music service.")


# --- Main ------------------------------------------------------------------------------------------------

def main() -> None:
    state = get_state()
    ctl = AppController(st.session_state.get("_test_songs") or load_catalog())
    sync_widget_keys(state)
    # Widget values are already in session_state when the script starts, so apply live edits first:
    # the summary, the badge and the results below then all reflect the same preferences.
    if state.base_prefs is not None:
        edited = widgets_to_manual()
        if not same_prefs(edited, prefs_to_manual(state.base_prefs)):
            ctl.apply_edit(state, edited)
    render_sidebar(ctl, state)

    ss = st.session_state
    ctl.switch_mode(state, ss["mode_radio"])
    ctl.change_strategy(state, ss["strategy_select"])
    ctl.set_k(state, ss["k_slider"])
    client = get_client()

    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(hero_html(), unsafe_allow_html=True)
    st.caption("A rule-based engine picks the songs. Gemini (AI) only reads your text and writes "
               "optional explanations. Everything AI-written is labelled.")

    if state.mode == MODE_AI:
        st.text_area("Describe your mood, activity or situation", key="w_text", max_chars=MAX_INPUT_CHARS,
                     height=90, placeholder="e.g. rainy Sunday, need to focus")
        state.draft_text = ss["w_text"]
        example_cols = st.columns(len(EXAMPLES))
        for i, (col, text) in enumerate(zip(example_cols, EXAMPLES)):
            col.button(text, key=f"example_{i}", on_click=cb_example, args=(state, text))
        if st.button("Find music", type="primary", key="find_music"):
            with st.spinner("Asking Gemini to interpret your request…"):
                ctl.submit_text(state, ss["w_text"], client, explain=ss["explain_toggle"])
            st.rerun()
        render_error(ctl, state)
        render_interpretation(ctl, state)
    else:
        render_error(ctl, state)
        if state.base_prefs is None:
            st.subheader("Choose your preferences")
            st.caption("Genres and moods come from the song catalog. Nothing is recommended until you ask.")
            render_pref_controls(ctl)
            if st.button("Get recommendations", type="primary", key="manual_go"):
                ctl.submit_manual(state, widgets_to_manual())
                st.rerun()
        else:
            render_interpretation(ctl, state)

    if state.outcome is None and state.base_prefs is None and state.error is None:
        render_empty_state()
    render_results(ctl, state, client)
    render_about()


main()
