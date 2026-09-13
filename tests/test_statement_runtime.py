from __future__ import annotations

import sys
from pathlib import Path

from gway.chain import run_chain, run_statement
from gway.chain_context import chain_context_scope, current_chain_context
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "statement-project"
    root.mkdir()
    (root / "statement_commands.py").write_text(
        """
def scalar() -> str:
    return "alpha"


def mapping() -> dict[str, str]:
    return {"name": "mapped", "status": "ready"}


def mapping_with_result() -> dict[str, str]:
    return {"name": "mapped", "result": "shadow"}


def nothing() -> None:
    return None


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("statement_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "statement_commands"},
        )
    )
    return Dispatcher(registry)


def test_run_statement_preserves_explicit_chain_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert run_statement(dispatcher, ["demo", "scalar", "-", "demo", "echo"]) == "alpha"


def test_run_chain_remains_compatible_wrapper(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    tokens = ["demo", "scalar", "-", "demo", "echo"]

    assert run_chain(dispatcher, tokens) == run_statement(dispatcher, tokens) == "alpha"


def test_caller_owned_context_survives_statement(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    result = run_statement(dispatcher, ["demo", "mapping"], context=context)

    assert result == {"name": "mapped", "status": "ready"}
    assert context["name"] == "mapped"
    assert context["status"] == "ready"
    assert context["result"] == result


def test_result_key_always_keeps_full_latest_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    result = run_statement(dispatcher, ["demo", "mapping-with-result"], context=context)

    assert result == {"name": "mapped", "result": "shadow"}
    assert context["result"] == result


def test_scalar_and_none_publish_only_reserved_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {"kept": "value"}

    assert run_statement(dispatcher, ["demo", "scalar"], context=context) == "alpha"
    assert context == {"kept": "value", "result": "alpha"}

    assert run_statement(dispatcher, ["demo", "nothing"], context=context) is None
    assert context == {"kept": "value", "result": None}


def test_statement_without_context_does_not_leak_state(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    run_statement(dispatcher, ["demo", "mapping"])

    assert current_chain_context() == {}


def test_nested_context_scope_restores_outer_context() -> None:
    outer: dict[str, object] = {"outer": True}
    inner: dict[str, object] = {"inner": True}

    with chain_context_scope(outer):
        assert current_chain_context() == {"outer": True}
        with chain_context_scope(inner):
            assert current_chain_context() == {"inner": True}
        assert current_chain_context() == {"outer": True}

    assert current_chain_context() == {}


def test_current_chain_context_returns_a_copy() -> None:
    context: dict[str, object] = {"name": "original"}

    with chain_context_scope(context):
        snapshot = current_chain_context()
        snapshot["name"] = "changed"

    assert context == {"name": "original"}


def test_explicit_empty_context_is_reused(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "scalar"], context=context)

    assert context == {"result": "alpha"}
