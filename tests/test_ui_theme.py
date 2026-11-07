"""Tests for the visual layer: helpers, escaping, theme contrast and the redesigned cards (mock Gemini only)."""

import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import ui_theme as ui
from src.recommender import MAX_SCORE, STRATEGIES, load_songs
from test_app_ui import APP, STUDY, find, like_ids, new_app, no_error, state, texts

ROOT = Path(__file__).resolve().parent.parent
GENRES = sorted({s["genre"] for s in load_songs(str(ROOT / "data" / "songs.csv"))})


def test_every_catalog_genre_has_an_icon_and_a_deterministic_gradient():
    for genre in GENRES:
        assert genre in ui.GENRE_ICONS
        assert ui.genre_gradient(genre) == ui.genre_gradient(genre)
    assert ui.genre_icon("unknown") == ui.DEFAULT_ICON


def test_score_bar_has_aria_text_and_clamps():
    html = ui.score_bar_html(3.85, 4.0)
    assert 'role="progressbar"' in html and "3.85 / 4.00" in html and 'aria-valuenow="3.85"' in html
    assert "width:96.2%" in ui.score_bar_html(3.85, 4.0)
    assert "width:100.0%" in ui.score_bar_html(9, 4.0) and "width:0.0%" in ui.score_bar_html(-1, 4.0)
    assert "width:0.0%" in ui.score_bar_html(1, 0)


def test_dynamic_text_is_escaped_in_every_html_helper():
    evil = '<script>alert(1)</script>"&'
    for html in (ui.song_head_html(1, evil, evil, evil), ui.chips_html([(evil, evil)]),
                 ui.score_bar_html(1, 4, label=evil)):
        assert "<script>" not in html and "&lt;script&gt;" in html
    assert ui.esc(None) == "" and ui.esc("<b>") == "&lt;b&gt;"


def test_theme_config_is_valid_dark_and_readable():
    theme = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["theme"]
    assert theme["base"] == "dark"
    bg, panel, text = theme["backgroundColor"], theme["secondaryBackgroundColor"], theme["textColor"]
    assert ui.contrast_ratio(text, bg) >= 7 and ui.contrast_ratio(text, panel) >= 7
    assert ui.contrast_ratio(ui.MUTED, panel) >= 4.5 and ui.contrast_ratio(ui.MUTED, bg) >= 4.5
    assert ui.contrast_ratio(theme["primaryColor"], bg) >= 3
    assert ui.contrast_ratio(ui.PINK, bg) >= 4.5


def test_css_avoids_generated_class_names():
    assert "emotion" not in ui.CSS and "css-" not in ui.CSS


def test_empty_state_then_cards_show_all_content_and_distinct_labels():
    at, mock = new_app()
    no_error(at)
    assert any("How it works" in t for t in texts(at))
    find(at)
    no_error(at)
    joined = "\n".join(texts(at))
    assert "How it works" not in joined
    recs = state(at).outcome.result.recommendations
    assert len(recs) == 5
    for rec in recs:
        assert rec.song["title"] in joined and rec.song["artist"] in joined
        assert f"{rec.score:.2f} / {MAX_SCORE:.2f}" in joined
    assert joined.count("Why it scored this (rule-based engine)") == 5
    assert joined.count("AI explanation (written by Gemini") >= 1
    assert "Why it scored this (rule-based engine)" != "AI explanation (written by Gemini"


def test_feedback_panel_counts_and_no_api_calls_for_ui_actions():
    at, mock = new_app()
    find(at)
    calls = len(mock.calls)
    ids = like_ids(at)
    at.button(key=f"like_{ids[0]}").click().run()
    at.button(key=f"dislike_{ids[1]}").click().run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Liked"] == "1" and metrics["Disliked"] == "1" and metrics["Excluded now"] == "1"
    for name in STRATEGIES:
        at.selectbox(key="strategy_select").set_value(name).run()
        no_error(at)
    at.slider(key="w_energy").set_value(0.9).run()
    at.slider(key="k_slider").set_value(8).run()
    at.run()
    assert len(mock.calls) == calls


def test_demo_mode_and_manual_mode_render_without_errors():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.checkbox(key="demo_mode").check().run()
    find(at)
    no_error(at)
    assert any("demo" in c.value.lower() for c in at.sidebar.caption)
    at.radio(key="mode_radio").set_value("manual").run()
    no_error(at)
