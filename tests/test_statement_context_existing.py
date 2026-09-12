from __future__ import annotations

from gway.chain_context import chain_context_scope, publish_chain_result


def test_result_publication_preserves_unrelated_named_context() -> None:
    context: dict[str, object] = {"device": "gway-004"}

    with chain_context_scope(context):
        publish_chain_result({"token": "abc"})

    assert context["device"] == "gway-004"
    assert context["token"] == "abc"
