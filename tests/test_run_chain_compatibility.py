from __future__ import annotations

from inspect import signature

from gway.chain import run_chain, run_statement


def test_run_chain_keeps_public_call_shape() -> None:
    parameters = signature(run_chain).parameters

    assert list(parameters) == ["dispatcher", "tokens", "interactive", "prompt"]
    assert parameters["interactive"].default is False
    assert parameters["prompt"].default is None


def test_statement_adds_context_without_changing_run_chain_surface() -> None:
    assert "context" in signature(run_statement).parameters
    assert "context" not in signature(run_chain).parameters
