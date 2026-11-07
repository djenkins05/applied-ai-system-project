"""
Reliability logging for MoodMix AI: structured, privacy-preserving operational events.

Each event is one JSON line on the "moodmix.reliability" logger. Only ALLOWED_FIELDS are kept,
so a stray argument can never leak into the log. The log NEVER contains:
  - the user's text (raw or in part) or any hash/fingerprint of it,
  - API keys, authorization headers, or model/response text.
It records: event type, error category, HTTP status, API status word, model id, guardrail
category, latency, input length (characters), and whether the manual fallback was used.

Logging to a file is opt-in (configure_reliability_log, --log-file, or MOODMIX_LOG_FILE).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.llm import sanitize_detail

LOG_FILE_ENV = "MOODMIX_LOG_FILE"
LOGGER_NAME = "moodmix.reliability"
MAX_VALUE_CHARS = 60

ALLOWED_FIELDS = (
    "error_kind", "status_code", "api_status", "model", "guardrail",
    "latency_ms", "input_chars", "used_fallback", "source", "dropped_explanations",
)

logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(logging.INFO)
_file_handler: Optional[logging.Handler] = None


def _clean_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(value, 1) if isinstance(value, float) else value
    if isinstance(value, str):
        cleaned = sanitize_detail(value)
        return cleaned[:MAX_VALUE_CHARS] if cleaned else None
    return None


def build_event(event: str, **fields: Any) -> Dict[str, Any]:
    """Return the sanitized record for an event (unit-testable without any handler)."""
    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": _clean_value(event),
    }
    for name in ALLOWED_FIELDS:
        if name in fields:
            record[name] = _clean_value(fields[name])
    return record


def log_event(event: str, **fields: Any) -> Dict[str, Any]:
    """Emit one reliability event and return the record that was logged."""
    record = build_event(event, **fields)
    logger.info(json.dumps(record, sort_keys=True))
    return record


def configure_reliability_log(path: Union[str, Path, None] = None) -> Optional[Path]:
    """
    Append reliability events to a file. `path` falls back to the MOODMIX_LOG_FILE variable;
    with neither, nothing is configured. Returns the path in use, or None.
    """
    global _file_handler
    target = path or os.environ.get(LOG_FILE_ENV)
    if not target:
        return None
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    reset_reliability_log()
    _file_handler = logging.FileHandler(target, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_file_handler)
    return target


def reset_reliability_log() -> None:
    """Detach and close the file handler, if any."""
    global _file_handler
    if _file_handler is not None:
        logger.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None
