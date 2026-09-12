from __future__ import annotations

from gway.chain_context import chain_context_scope, current_chain_context, publish_chain_result


def test_caller_owned_context_is_updated_and_restored() -> None:
    context: dict[str, object] = {"existing": "kept"}

    with chain_context_scope(context):
        publish_chain_result({"name": "mapped"})
        assert current_chain_context() == {
            "existing": "kept",
            "name": "mapped",
            "result": {"name": "mapped"},
        }

    assert current_chain_context() == {}
    assert context == {
        "existing": "kept",
        "name": "mapped",
        "result": {"name": "mapped"},
    }
