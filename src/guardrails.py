"""
Input and output guardrails for MoodMix AI.

  screen_input(text)      -> InputScreen   check/clean the user's text *before* any Gemini call
  detect_injection(text)  -> Optional[str] narrow prompt-injection detector (returns a category)
  screen_ai_text(text)    -> Optional[str] extra check on AI-written explanation text
  friendly_warnings(p)    -> List[str]     plain-language version of MoodPreferences.warnings

Design notes
  - The injection detector is deliberately NARROW. It only fires on clear attempts to override
    the assistant's instructions, reveal hidden prompts, impersonate system/developer roles, or
    bypass safeguards. Everyday music wording such as "ignore distractions", "forget my previous
    music preferences" or "developer mode coding playlist" must pass; tests cover both sides.
  - This is one layer. The prompt also fences user text as data, and all model output is
    validated (src/preferences.py, src/explain.py), so the detector is not the only defense.
  - Nothing here logs or stores the user's text.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, List, Optional

from src.llm import MAX_INPUT_CHARS
from src.preferences import MoodPreferences

MIN_LETTERS = 1
MIN_LETTER_RATIO = 0.3          # letters / non-space characters
MAX_RAW_CHARS = MAX_INPUT_CHARS * 4   # refuse absurd payloads before doing any processing

EXAMPLE_REQUEST = '"rainy Sunday, need to focus"'

# --- Messages (user-facing) ----------------------------------------------------

MESSAGES = {
    "not_text": "Please type a short description of your mood, activity, or the music you want.",
    "empty": "Please describe your mood, activity, or the music you want.",
    "too_long": f"That is too long. Please keep your description under {MAX_INPUT_CHARS} characters.",
    "no_letters": f"I couldn't find a description in that. Try words like {EXAMPLE_REQUEST}.",
    "spam": f"That looks like repeated characters. Try describing a mood or activity, like {EXAMPLE_REQUEST}.",
    "prompt_injection": (
        "That looks like an attempt to change how MoodMix works, so I didn't send it. "
        f"Describe a mood, activity or situation instead (for example {EXAMPLE_REQUEST}), "
        "or enter your preferences manually."
    ),
}


# --- Prompt-injection detector (narrow on purpose) -----------------------------

_FILLER = r"(?:(?:all|any|every|of|the|these|those|my|and|everything)\s+){0,3}"
_OBJECT = (r"(?:instructions?|prompts?|rules|guidelines|directives|programming|guardrails|"
           r"safeguards?|restrictions?|constraints)")
# A qualifier is required so "forget my previous MUSIC preferences" never matches.
_QUALIFIER = (r"(?:previous|prior|above|earlier|preceding|original|initial|system|developer|your|"
              r"safety|content)")

_INJECTION_PATTERNS = (
    ("override_instructions", re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|discard)\b\s+" + _FILLER + _QUALIFIER
        + r"\s+(?:\w+\s+)?" + _OBJECT + r"\b", re.IGNORECASE)),
    ("override_instructions", re.compile(
        r"\bforget\s+(?:everything|all)\s+(?:that\s+)?(?:you|you've|you\s+have)\s+"
        r"(?:were|been|was)?\s*(?:told|instructed|taught)\b", re.IGNORECASE)),
    ("reveal_prompt", re.compile(
        r"\b(?:reveal|show|print|display|repeat|output|leak|expose|tell\s+me|give\s+me)\b[^.\n]{0,25}?"
        r"\b(?:your|the)\s+(?:(?:system|hidden|initial|secret|original|developer)\s+)?"
        r"(?:prompt|instructions?|rules|guidelines)\b", re.IGNORECASE)),
    ("reveal_prompt", re.compile(
        r"\bwhat\s+(?:is|are|was|were)\s+your\s+(?:(?:system|hidden|initial|secret|original)\s+)?"
        r"(?:prompt|instructions?|rules)\b", re.IGNORECASE)),
    ("reveal_prompt", re.compile(
        r"\b(?:reveal|show|print|display|repeat|output|leak)\b[^.\n]{0,25}?"
        r"\b(?:system|hidden|initial|secret)\s+(?:prompt|instructions?|message)\b", re.IGNORECASE)),
    ("role_impersonation", re.compile(
        r"(?im)^\s*(?:system|developer|admin(?:istrator)?)\s*(?:prompt|message|override|instructions?)?"
        r"\s*:")),
    ("role_impersonation", re.compile(
        r"<\|[^|>]{1,20}\|>|\[/?(?:INST|SYS)\]|<</?SYS>>|</?\s*(?:system|assistant|user_input|"
        r"listener_request|facts)\s*>|^\s*#{2,}\s*(?:system|instructions?)\b", re.IGNORECASE | re.MULTILINE)),
    ("role_impersonation", re.compile(
        r"\byou\s+are\s+(?:now|no\s+longer)\b[^.\n]{0,40}?"
        r"\b(?:dan|jailbroken|unrestricted|unfiltered|without\s+(?:any\s+)?(?:rules|restrictions|filters))\b",
        re.IGNORECASE)),
    ("bypass_safeguards", re.compile(
        r"\b(?:bypass|disable|circumvent|turn\s+off|remove|evade)\b\s+(?:(?:your|the|all|any)\s+)+"
        r"(?:\w+\s+)?(?:safety|safeguards?|guardrails?|filters?|restrictions?|moderation|"
        r"content\s+polic(?:y|ies))\b", re.IGNORECASE)),
    ("bypass_safeguards", re.compile(
        r"\bdeveloper\s+mode\b[^.\n]{0,40}?\b(?:ignore|bypass|disable)\b\s+(?:\w+\s+){0,2}"
        r"(?:rules|restrictions|filters|guidelines|instructions|safety)\b", re.IGNORECASE)),
    ("bypass_safeguards", re.compile(
        r"\b(?:pretend|act|behave)\b[^.\n]{0,25}?\b(?:no|without)\s+(?:any\s+)?"
        r"(?:rules|restrictions|filters|guidelines|safeguards)\b", re.IGNORECASE)),
)


def detect_injection(text: str) -> Optional[str]:
    """Return the category of the first clear injection attempt found, or None."""
    for category, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return category
    return None


# --- Input screening -----------------------------------------------------------

@dataclass
class InputScreen:
    """Outcome of screen_input. `cleaned` is only meaningful when ok is True."""
    ok: bool
    cleaned: str = ""
    category: Optional[str] = None        # why it was rejected (see MESSAGES), None if ok
    message: Optional[str] = None         # user-facing explanation when rejected
    flags: List[str] = field(default_factory=list)   # categories only, never text


def _normalize(text: str) -> str:
    """NFKC-normalize, drop control/invisible characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    chars = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in "\n\r\t":
            chars.append("\n" if ch != "\t" else " ")
        elif category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            chars.append(ch)
    text = "".join(chars)
    text = re.sub(r"[  ]+", " ", text)
    text = re.sub(r" *\n[\s]*", "\n", text)
    return text.strip()


def _reject(category: str) -> InputScreen:
    return InputScreen(ok=False, category=category, message=MESSAGES[category], flags=[category])


def screen_input(text: Any) -> InputScreen:
    """Clean and check the user's request. Never raises; never logs or keeps the raw text."""
    if not isinstance(text, str):
        return _reject("not_text")
    if len(text) > MAX_RAW_CHARS:
        return _reject("too_long")

    cleaned = _normalize(text)
    if not cleaned:
        return _reject("empty")
    if len(cleaned) > MAX_INPUT_CHARS:
        return _reject("too_long")

    letters = sum(ch.isalpha() for ch in cleaned)
    non_space = sum(not ch.isspace() for ch in cleaned)
    if letters < MIN_LETTERS or letters / max(non_space, 1) < MIN_LETTER_RATIO:
        return _reject("no_letters")
    if re.search(r"(\S)\1{19,}", cleaned):
        return _reject("spam")
    if detect_injection(cleaned):
        return _reject("prompt_injection")
    return InputScreen(ok=True, cleaned=cleaned)


# --- AI output screening -------------------------------------------------------

_AI_TEXT_PATTERNS = (
    ("link", re.compile(r"https?://|\bwww\.|\[[^\]]*\]\([^)]*\)|!\[", re.IGNORECASE)),
    ("markup", re.compile(r"</?[a-zA-Z][^>]*>|```")),
)


def screen_ai_text(text: Any) -> Optional[str]:
    """Return a problem description if AI-written text carries links, markup or instructions."""
    if not isinstance(text, str):
        return "not text"
    for name, pattern in _AI_TEXT_PATTERNS:
        if pattern.search(text):
            return f"contains {name}"
    if detect_injection(text):
        return "contains instruction-like text"
    return None


# --- Friendly warnings ---------------------------------------------------------

_WARNING_RULES = (
    (re.compile(r"^dropped unknown (genre|mood): '?(.*?)'?$"),
     lambda m: f"I don't have the {m.group(1)} '{m.group(2)}' in this catalog, so I skipped it."),
    (re.compile(r"^clamped (target_)?(\w+) from ([\d.\-e+]+) to ([\d.]+)$"),
     lambda m: f"{m.group(2).title()} {m.group(3)} was outside 0 to 1, so I used {m.group(4)} instead."),
    (re.compile(r"^kept the first (\d+) (genres|moods)$"),
     lambda m: f"Only the first {m.group(1)} {m.group(2)} were used."),
    (re.compile(r"^target_energy missing; using neutral default ([\d.]+)$"),
     lambda m: f"No energy level was given, so I used a neutral {m.group(1)}."),
    (re.compile(r"^ignored (?:target_)?(energy|valence|acousticness): .*"),
     lambda m: f"I ignored an unusable {m.group(1)} value."),
    (re.compile(r"^(?:ignored|dropped non-text) (genres|moods)\b.*"),
     lambda m: f"I ignored an unreadable {m.group(1)} entry."),
)


def friendly_warnings(prefs: MoodPreferences) -> List[str]:
    """Plain-language notes about adjustments made to the AI's (or the user's) preferences."""
    notes: List[str] = []
    for warning in prefs.warnings:
        for pattern, render in _WARNING_RULES:
            match = pattern.match(warning)
            if match:
                notes.append(render(match))
                break
        # Anything unmatched (e.g. "ignored unknown keys") is internal detail and is not shown.
    return notes
