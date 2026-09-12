from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_empty_caller_context_is_used_in_place() -> None:
    context: dict[str, object] = {}

    with chain_context_scope(context) as active:
        assert active is context
        publish_chain_result({"ready": True})

    assert context["ready"] is True
