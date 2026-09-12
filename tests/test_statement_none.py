from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_none_result_is_still_published_as_latest_result() -> None:
    context: dict[str, object] = {"name": "kept"}

    with chain_context_scope(context):
        publish_chain_result(None)

    assert context == {"name": "kept", "result": None}
