from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_mapping_publication_updates_named_context() -> None:
    context: dict[str, object] = {}
    with chain_context_scope(context):
        publish_chain_result({"status": "ready"})
    assert context["status"] == "ready"
