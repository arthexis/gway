from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_mapping_result_key_does_not_replace_full_result() -> None:
    context: dict[str, object] = {}
    value = {"name": "mapped", "result": "shadow"}

    with chain_context_scope(context):
        publish_chain_result(value)

    assert context["name"] == "mapped"
    assert context["result"] is value
