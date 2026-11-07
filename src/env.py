"""
Load local settings (like GEMINI_API_KEY) from the repository's .env file.

- The path is anchored to this file, not the current directory, so it works the same for
  `python -m src.moodmix_cli` and `streamlit run app.py` from any working directory.
- Variables that are already set in the environment always win (override=False).
- Returns only whether a file was loaded. Values are never returned, printed or logged.
- Set MOODMIX_DISABLE_DOTENV to any value to skip loading (the test suite does this).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DISABLE_ENV_VAR = "MOODMIX_DISABLE_DOTENV"


def load_env(path: Path = None) -> bool:
    """Load `path` (default: <repo root>/.env) without overriding existing variables."""
    if os.environ.get(DISABLE_ENV_VAR):
        return False
    return bool(load_dotenv(path if path is not None else ENV_PATH, override=False))
