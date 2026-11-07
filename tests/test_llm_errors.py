"""Gemini HTTP error classification and safe diagnostics. Mocked only: no network, no real key."""

import logging

import pytest

from src.llm import (
    GeminiClient, LLMAuthError, LLMBadRequestError, LLMError, LLMModelNotFoundError,
    LLMRateLimitError, LLMUnavailableError, classify_error, interpret_preferences, sanitize_detail,
)
from src.pipeline import recommend_from_text
from src.preferences import catalog_vocabulary
from src.recommender import load_songs
from fakes import FakeClient

SECRET = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE12345"


class SDKStyleError(Exception):
    """Shaped like google.genai.errors.ClientError: code, status, message."""

    def __init__(self, code, status=None, message=""):
        super().__init__(f"{code} {status}. leaked-in-str: {SECRET}")
        self.code, self.status, self.message = code, status, message


@pytest.fixture
def songs():
    return load_songs("data/songs.csv")


def run(error, songs):
    gem = GeminiClient(client=FakeClient(interpret=error), sleep=lambda _s: None)
    return recommend_from_text("I'm studying for finals", songs, client=gem)


@pytest.mark.parametrize("code,status,cls", [
    (400, "INVALID_ARGUMENT", LLMBadRequestError),
    (401, "UNAUTHENTICATED", LLMAuthError),
    (403, "PERMISSION_DENIED", LLMAuthError),
    (404, "NOT_FOUND", LLMModelNotFoundError),
    (429, "RESOURCE_EXHAUSTED", LLMRateLimitError),
    (503, "UNAVAILABLE", LLMUnavailableError),
])
def test_each_http_status_gets_its_own_class_and_code(code, status, cls):
    err = classify_error(SDKStyleError(code, status, "boom"))
    assert type(err) is cls
    assert err.status_code == code and err.api_status == status
    assert err.diagnostic.startswith(f"HTTP {code} {status}")


def test_unlisted_4xx_stays_generic_but_keeps_its_code():
    err = classify_error(SDKStyleError(418, "TEAPOT", "x"))
    assert type(err) is LLMError and err.status_code == 418


def test_rate_limit_is_still_retryable_unavailable():
    assert isinstance(classify_error(SDKStyleError(429)), LLMUnavailableError)


@pytest.mark.parametrize("code", [400, 404])
def test_bad_request_and_model_not_found_are_not_retried(code):
    fake = FakeClient(interpret=SDKStyleError(code, "X_Y_Z", "m"))
    gem = GeminiClient(client=fake, sleep=lambda _s: None)
    with pytest.raises(LLMError):
        interpret_preferences("studying", catalog_vocabulary(load_songs("data/songs.csv")), gem)
    assert len(fake.calls) == 1


def test_diagnostics_never_contain_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "my-real-looking-key-9999")
    msg = (f"Bad key {SECRET}; Authorization: Bearer abc.def.ghi; x-goog-api-key: zzz; "
           "see https://x.googleapis.com/v1?key=hunter2&a=1 and my-real-looking-key-9999")
    err = classify_error(SDKStyleError(400, "INVALID_ARGUMENT", msg))
    text = err.diagnostic + str(err)
    for bad in (SECRET, "abc.def.ghi", "zzz", "hunter2", "my-real-looking-key-9999", "https://"):
        assert bad not in text
    assert "REDACTED" in text


def test_detail_is_truncated_and_non_strings_ignored():
    assert len(sanitize_detail("a " * 500)) <= 200
    assert sanitize_detail(None) is None and sanitize_detail("   ") is None


def test_exception_str_is_not_used(songs):
    err = classify_error(SDKStyleError(400, "INVALID_ARGUMENT", ""))
    assert SECRET not in str(err) and SECRET not in err.diagnostic


@pytest.mark.parametrize("code,status,kind", [
    (400, "INVALID_ARGUMENT", "bad_request"), (404, "NOT_FOUND", "model_not_found"),
    (429, "RESOURCE_EXHAUSTED", "unavailable"), (401, "UNAUTHENTICATED", "auth"),
    (403, "PERMISSION_DENIED", "auth"),
])
def test_pipeline_reports_kind_and_diagnostic(songs, code, status, kind):
    result = run(SDKStyleError(code, status, f"detail {SECRET}"), songs)
    assert not result.ok and result.error_kind == kind
    assert f"HTTP {code}" in result.error and SECRET not in result.error


def test_logs_carry_status_and_model_but_no_secret(songs, caplog):
    with caplog.at_level(logging.WARNING):
        run(SDKStyleError(404, "NOT_FOUND", f"models/x is not found {SECRET}"), songs)
    log = caplog.text
    assert "HTTP 404 NOT_FOUND" in log and "model=" in log and SECRET not in log


def test_real_sdk_client_error_is_classified():
    from google.genai import errors
    body = {"error": {"code": 404, "status": "NOT_FOUND", "message": "models/nope is not found"}}
    err = classify_error(errors.ClientError(404, body))
    assert type(err) is LLMModelNotFoundError
    assert err.status_code == 404 and "not found" in err.diagnostic


def test_timeout_default_and_env_override(monkeypatch):
    monkeypatch.delenv("GEMINI_TIMEOUT_S", raising=False)
    assert GeminiClient(client=object()).timeout_s == 45.0
    monkeypatch.setenv("GEMINI_TIMEOUT_S", "90")
    assert GeminiClient(client=object()).timeout_s == 90.0
    for bad in ("abc", "0", "9999"):
        monkeypatch.setenv("GEMINI_TIMEOUT_S", bad)
        assert GeminiClient(client=object()).timeout_s == 45.0
    assert GeminiClient(client=object(), timeout_s=5).timeout_s == 5


def test_504_is_unavailable_with_diagnostic():
    err = classify_error(SDKStyleError(504, "DEADLINE_EXCEEDED", "Deadline expired"))
    assert isinstance(err, LLMUnavailableError) and "HTTP 504 DEADLINE_EXCEEDED" in err.diagnostic
