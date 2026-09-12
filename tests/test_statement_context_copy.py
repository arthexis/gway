from __future__ import annotations

from gway.chain_context import chain_context_scope, current_chain_context


def test_current_context_returns_a_copy() -> None:
    context: dict[str, object] = {"name": "mapped"}

    with chain_context_scope(context):
        snapshot = current_chain_context()
        snapshot["name"] = "changed"

    assert context["name"] == "mapped"
