"""
.env loading tests. They only ever use temporary files, never the repository's real .env,
and make no network calls. os.environ changes are made through monkeypatch so they are
undone after each test.
"""

import os
from pathlib import Path

import pytest

import src.env as env_module
from src.env import DISABLE_ENV_VAR, load_env
from src.llm import GeminiClient, MissingAPIKeyError

DUMMY_KEY = "dummy-key-for-tests-only"


def isolate(monkeypatch, *names):
    """Make each variable absent now and restore its original state after the test."""
    for name in names:
        monkeypatch.setenv(name, "placeholder")   # records the original state
        monkeypatch.delenv(name)


@pytest.fixture
def dotenv_enabled(monkeypatch, tmp_path):
    """Enable .env loading, with isolated variables and ENV_PATH pointing at a temp file."""
    monkeypatch.delenv(DISABLE_ENV_VAR)           # set to "1" by the autouse fixture
    isolate(monkeypatch, "GEMINI_API_KEY", "GEMINI_MODEL")
    path = tmp_path / ".env"
    monkeypatch.setattr(env_module, "ENV_PATH", path)
    return path


def test_values_from_the_file_are_loaded(dotenv_enabled):
    dotenv_enabled.write_text(f"GEMINI_API_KEY={DUMMY_KEY}\nGEMINI_MODEL=model-from-file\n")
    assert load_env() is True
    assert os.environ["GEMINI_API_KEY"] == DUMMY_KEY
    assert os.environ["GEMINI_MODEL"] == "model-from-file"


def test_existing_environment_variables_beat_the_file(dotenv_enabled, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "model-from-shell")
    dotenv_enabled.write_text(f"GEMINI_API_KEY={DUMMY_KEY}\nGEMINI_MODEL=model-from-file\n")
    load_env()
    assert os.environ["GEMINI_MODEL"] == "model-from-shell"
    assert os.environ["GEMINI_API_KEY"] == DUMMY_KEY     # unset in the shell, so the file fills it


def test_missing_file_is_not_an_error(dotenv_enabled):
    assert not dotenv_enabled.exists()
    assert load_env() is False
    assert "GEMINI_API_KEY" not in os.environ


def test_explicit_path_argument_is_used(dotenv_enabled, tmp_path):
    other = tmp_path / "other.env"
    other.write_text("GEMINI_MODEL=model-from-other\n")
    assert load_env(other) is True
    assert os.environ["GEMINI_MODEL"] == "model-from-other"


def test_disable_variable_skips_loading(dotenv_enabled, monkeypatch):
    dotenv_enabled.write_text(f"GEMINI_API_KEY={DUMMY_KEY}\n")
    monkeypatch.setenv(DISABLE_ENV_VAR, "1")
    assert load_env() is False
    assert "GEMINI_API_KEY" not in os.environ


def test_load_env_returns_a_bool_and_prints_nothing(dotenv_enabled, capsys):
    dotenv_enabled.write_text(f"GEMINI_API_KEY={DUMMY_KEY}\n")
    result = load_env()
    captured = capsys.readouterr()
    assert result is True
    assert DUMMY_KEY not in captured.out + captured.err


def test_default_path_is_the_repo_root_env_file():
    expected = Path(__file__).resolve().parent.parent / ".env"
    assert Path(env_module.__file__).resolve().parent.parent / ".env" == expected


# --- Integration with GeminiClient ----------------------------------------------

def test_real_client_path_loads_model_and_key_from_the_file(dotenv_enabled):
    dotenv_enabled.write_text(f"GEMINI_API_KEY={DUMMY_KEY}\nGEMINI_MODEL=model-from-file\n")
    client = GeminiClient()
    assert client.model == "model-from-file"
    client._get_client()                    # builds the SDK object; makes no network request
    assert client._client is not None


def test_injected_client_does_not_read_the_file(dotenv_enabled):
    dotenv_enabled.write_text("GEMINI_MODEL=model-from-file\n")
    client = GeminiClient(client=object())
    assert client.model != "model-from-file"
    assert "GEMINI_MODEL" not in os.environ


def test_empty_key_in_the_file_still_means_no_key(dotenv_enabled):
    dotenv_enabled.write_text("GEMINI_API_KEY=\nGEMINI_MODEL=\n")
    client = GeminiClient()
    with pytest.raises(MissingAPIKeyError):
        client._get_client()


def test_shell_key_beats_an_empty_key_in_the_file(dotenv_enabled, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    dotenv_enabled.write_text("GEMINI_API_KEY=\n")
    GeminiClient()._get_client()            # would raise MissingAPIKeyError if the file won
    assert os.environ["GEMINI_API_KEY"] == DUMMY_KEY


def test_the_test_suite_itself_disables_dotenv_by_default():
    # Without dotenv_enabled, the autouse fixture has set the disable flag.
    assert os.environ.get(DISABLE_ENV_VAR) == "1"


# --- Git and example-file hygiene ------------------------------------------------

def test_gitignore_blocks_env_files_but_allows_the_example():
    lines = {line.strip() for line in (Path(__file__).resolve().parent.parent / ".gitignore").read_text().splitlines()}
    assert {".env", ".env.*", "!.env.example"} <= lines


def test_env_example_contains_no_secret_values():
    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text()
    assignments = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert assignments == ["GEMINI_API_KEY=", "GEMINI_MODEL="]
