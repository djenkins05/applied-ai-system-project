"""
UI-only styling helpers for MoodMix AI (no scoring or app logic).

Colours live in .streamlit/config.toml (native theme). This module adds a small, stable layer:
 - CSS that targets only our own `st-key-*` container classes (created from `st.container(key=...)`),
 - decorative genre icons/gradients (illustrative only, never real album art),
 - a score bar and chips built as HTML, where every dynamic string is escaped.
"""

from html import escape

PINK = "#F472B6"
VIOLET = "#A78BFA"
DEEP_VIOLET = "#7C3AED"
BG = "#0F1020"
PANEL = "#1A1B33"
TEXT = "#F3F1FF"
MUTED = "#B8B5D6"

GENRE_ICONS = {
    "EDM": "⚡", "R&B": "🎙️", "ambient": "🌌", "classical": "🎻", "disco": "🪩", "hip-hop": "🎤",
    "indie pop": "🌈", "jazz": "🎷", "lofi": "☕", "metal": "🤘", "pop": "⭐", "rap": "🎧",
    "rock": "🎸", "synthwave": "🌆", "trap": "🔊",
}
DEFAULT_ICON = "🎵"
_GRADIENTS = (
    ("#7C3AED", "#DB2777"), ("#4F46E5", "#7C3AED"), ("#9333EA", "#EC4899"),
    ("#6D28D9", "#2563EB"), ("#BE185D", "#6D28D9"), ("#5B21B6", "#DB2777"),
)

CSS = f"""
<style>
.mm-hero {{ padding: .4rem 0 .8rem 0; }}
.mm-hero h1 {{ font-size: 2.4rem; margin: 0; line-height: 1.15; color: {TEXT};
  background: linear-gradient(90deg, {VIOLET}, {PINK}); -webkit-background-clip: text;
  background-clip: text; -webkit-text-fill-color: transparent; }}
.mm-hero p {{ color: {MUTED}; margin: .25rem 0 0 0; font-size: 1.05rem; }}
.mm-tile {{ width: 3.2rem; height: 3.2rem; border-radius: .9rem; display: flex; align-items: center;
  justify-content: center; font-size: 1.6rem; flex: none; }}
.mm-head {{ display: flex; gap: .8rem; align-items: center; }}
.mm-title {{ font-size: 1.15rem; font-weight: 700; color: {TEXT}; line-height: 1.25; }}
.mm-artist {{ color: {MUTED}; font-size: .95rem; }}
.mm-bar-row {{ display: flex; align-items: center; gap: .7rem; margin: .5rem 0 .2rem 0; }}
.mm-bar {{ flex: 1; height: .6rem; background: #2A2C52; border-radius: 999px; overflow: hidden; }}
.mm-bar > span {{ display: block; height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, {DEEP_VIOLET}, {PINK}); }}
.mm-score {{ font-weight: 700; color: {TEXT}; white-space: nowrap; }}
[class*="st-key-engine_"] {{ border-left: 4px solid #64748B; background: #15162B; padding: .4rem .8rem;
  border-radius: .6rem; }}
[class*="st-key-aiwhy_"] {{ border-left: 4px solid {PINK}; background: #2A1730; padding: .4rem .8rem;
  border-radius: .6rem; }}
.mm-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .3rem 0; }}
.mm-chip {{ background: #2A2C52; color: {TEXT}; border-radius: 999px; padding: .15rem .7rem; font-size: .88rem; }}
.mm-chip b {{ color: {MUTED}; font-weight: 600; margin-right: .3rem; }}
[class*="st-key-card_"] {{ border-radius: 1rem; }}
[class*="st-key-hero_empty"] {{ border-radius: 1rem; }}
@media (max-width: 640px) {{
  .mm-hero h1 {{ font-size: 1.8rem; }}
  .mm-title {{ font-size: 1.05rem; }}
  .block-container {{ padding-left: 1rem !important; padding-right: 1rem !important; }}
}}
</style>
"""


def esc(value) -> str:
    """Escape any dynamic text before it is placed in HTML."""
    return escape("" if value is None else str(value), quote=True)


def genre_icon(genre: str) -> str:
    return GENRE_ICONS.get(genre, DEFAULT_ICON)


def genre_gradient(genre: str) -> tuple[str, str]:
    """Deterministic (not hash()-based, so stable across runs) gradient for a genre."""
    index = sum(ord(ch) for ch in str(genre)) % len(_GRADIENTS)
    return _GRADIENTS[index]


def hero_html() -> str:
    return ('<div class="mm-hero"><h1>MoodMix AI</h1>'
            "<p>Tell me your mood. A transparent rule-based engine picks the music.</p></div>")


def tile_html(genre: str) -> str:
    start, end = genre_gradient(genre)
    return (f'<div class="mm-tile" aria-hidden="true" title="Decorative icon, not album art" '
            f'style="background:linear-gradient(135deg,{start},{end})">{genre_icon(genre)}</div>')


def song_head_html(rank: int, title: str, artist: str, genre: str) -> str:
    return (f'<div class="mm-head">{tile_html(genre)}<div>'
            f'<div class="mm-title">{esc(rank)}. {esc(title)}</div>'
            f'<div class="mm-artist">{esc(artist)}</div></div></div>')


def score_bar_html(score: float, max_score: float, label: str = "Match score") -> str:
    """Accessible bar: ARIA progressbar plus the number as text (colour is never the only signal)."""
    fraction = 0.0 if max_score <= 0 else min(1.0, max(0.0, score / max_score))
    text = f"{score:.2f} / {max_score:.2f}"
    return (f'<div class="mm-bar-row"><div class="mm-bar" role="progressbar" aria-label="{esc(label)}" '
            f'aria-valuemin="0" aria-valuemax="{max_score:g}" aria-valuenow="{score:.2f}" '
            f'aria-valuetext="{esc(text)}"><span style="width:{fraction * 100:.1f}%"></span></div>'
            f'<div class="mm-score">{esc(text)}</div></div>')


def chips_html(pairs) -> str:
    chips = "".join(f'<span class="mm-chip"><b>{esc(k)}</b>{esc(v)}</span>' for k, v in pairs)
    return f'<div class="mm-chips">{chips}</div>'


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2 contrast ratio between two #RRGGBB colours."""
    def lum(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)
