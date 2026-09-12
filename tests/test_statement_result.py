from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_publishing_context_does_not_transform_result_value() -> None:
    value = ["one", "two"]
    context: dict[str, object] = {}

    with chain_context_scope(context):
        publish_chain_result(value)

    assert context["result"] is value
