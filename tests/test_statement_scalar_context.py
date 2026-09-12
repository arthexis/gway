from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_scalar_result_only_updates_reserved_result_key() -> None:
    context: dict[str, object] = {"name": "kept"}

    with chain_context_scope(context):
        publish_chain_result("alpha")

    assert context == {"name": "kept", "result": "alpha"}
