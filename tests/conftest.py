"""Shared test safety: no real API key and no network access in any test."""

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_api_key_and_no_network(monkeypatch):
    """Tests must never read a real Gemini key or reach the live API."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    # Never read the developer's real .env during tests. Tests that verify .env loading
    # remove this variable themselves and point ENV_PATH at a temporary file.
    monkeypatch.setenv("MOODMIX_DISABLE_DOTENV", "1")

    def blocked(*args, **kwargs):
        raise AssertionError("network access is blocked during tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
