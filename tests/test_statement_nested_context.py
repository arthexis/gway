from __future__ import annotations

from gway.chain_context import chain_context_scope, current_chain_context


def test_nested_caller_owned_context_restores_outer_context() -> None:
    outer = {"scope": "outer"}
    inner = {"scope": "inner"}

    with chain_context_scope(outer):
        assert current_chain_context() == outer
        with chain_context_scope(inner):
            assert current_chain_context() == inner
        assert current_chain_context() == outer

    assert current_chain_context() == {}
