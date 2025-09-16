"""Tests for the redacted builtin."""

from gway.gateway import gw


def test_redacted_replaces_sigils():
    text = "Hello [name] and [other]!"
    assert gw.redacted(text) == "Hello [REDACTED] and [REDACTED]!"


def test_redacted_without_sigils_returns_placeholder():
    assert gw.redacted("No placeholders here") == "[REDACTED]"


def test_redacted_without_arguments():
    assert gw.redacted() == "[REDACTED]"
