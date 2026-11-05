"""Shared test safety: no real API key and no network access in any test."""

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_api_key_and_no_network(monkeypatch):
    """Tests must never read a real Gemini key or reach the live API."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("network access is blocked during tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
