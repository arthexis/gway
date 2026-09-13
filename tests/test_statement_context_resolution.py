from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.chain import run_statement
from gway.command import Command, Parameter
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.arguments import _fill_context_options
from gway.explain import explain_scope
from gway.expression import STRUCTURED_KWARG_PREFIX
from gway.project import Project
from gway.registry import Registry
from gway.transfer import transfer_scope


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "context-project"
    root.mkdir()
    (root / "context_commands.py").write_text(
        """def publish() -> dict[str, object]:
    return {"token": "context-token", "enabled": True, "count": 7}


def publish_disabled() -> dict[str, bool]:
    return {"enabled": False}


def consume(*, token: str, enabled: bool = False, count: int = 0) -> dict[str, object]:
    return {"token": token, "enabled": enabled, "count": count}


def enabled(*, enabled: bool = True) -> bool:
    return enabled


def named_result(*, result: str = "default") -> str:
    return result
""",
        encoding="utf-8",
    )
    sys.modules.pop("context_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "context_commands"},
        )
    )
    return Dispatcher(registry)


def test_shared_context_fills_missing_named_options(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "publish"], context=context)

    assert run_statement(dispatcher, ["demo", "consume"], context=context) == {
        "token": "context-token",
        "enabled": True,
        "count": 7,
    }


def test_explicit_option_wins_over_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "publish"], context=context)

    result = run_statement(
        dispatcher,
        ["demo", "consume", "--token", "explicit"],
        context=context,
    )
    assert result["token"] == "explicit"
    assert result["enabled"] is True
    assert result["count"] == 7


def test_false_boolean_context_uses_negative_option(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "publish-disabled"], context=context)

    assert run_statement(dispatcher, ["demo", "enabled"], context=context) is False


def test_result_is_reserved_from_implicit_argument_fill(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "publish"], context=context)

    assert run_statement(dispatcher, ["demo", "named-result"], context=context) == "default"


def test_context_is_applied_before_interactive_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}
    run_statement(dispatcher, ["demo", "publish"], context=context)

    def unexpected_prompt(_prompt: str) -> str:
        pytest.fail("interactive prompt should not run for context-satisfied values")

    monkeypatch.setattr("builtins.input", unexpected_prompt)
    result = run_statement(
        dispatcher,
        ["demo", "consume"],
        context=context,
        interactive=True,
    )
    assert result["token"] == "context-token"


def test_context_fill_emits_explain_event(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}
    run_statement(dispatcher, ["demo", "publish"], context=context)

    with explain_scope() as trace:
        run_statement(dispatcher, ["demo", "consume"], context=context)

    steps = [step for step in trace if step.kind == "arguments.context"]
    assert len(steps) == 1
    assert steps[0].data["values"] == {
        "token": "context-token",
        "enabled": True,
        "count": 7,
    }


def test_fill_context_options_ignores_positional_parameters() -> None:
    command = Command(
        path=("consume",),
        parameters=(Parameter(name="value", positional=True, required=True),),
    )

    with transfer_scope():
        argv, filled = _fill_context_options(command, [], {"value": "implicit"})

    assert argv == []
    assert filled == {}


def test_structured_keyword_counts_as_explicit_argument() -> None:
    command = Command(
        path=("consume",),
        parameters=(Parameter(name="token", options=("--token",)),),
    )
    argv = [f"{STRUCTURED_KWARG_PREFIX}token=explicit"]

    with transfer_scope():
        resolved, filled = _fill_context_options(command, argv, {"token": "context"})

    assert resolved == argv
    assert filled == {}


def test_context_options_are_inserted_before_literal_separator() -> None:
    command = Command(
        path=("consume",),
        parameters=(Parameter(name="token", options=("--token",)),),
    )

    with transfer_scope():
        argv, filled = _fill_context_options(command, ["--", "literal"], {"token": "context"})

    assert argv == ["--token", "context", "--", "literal"]
    assert filled == {"token": "context"}
