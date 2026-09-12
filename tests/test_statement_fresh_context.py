from __future__ import annotations

from gway.chain_context import chain_context_scope, current_chain_context, publish_chain_result


def test_default_context_scope_remains_fresh_and_isolated() -> None:
    with chain_context_scope():
        publish_chain_result({"name": "temporary"})
        assert current_chain_context()["name"] == "temporary"

    with chain_context_scope():
        assert "name" not in current_chain_context()
