from __future__ import annotations

from pathlib import Path

import pytest

from gway.adapters import AdapterRegistry
from gway.chain_context import chain_context_scope
from gway.command import Command, Parameter
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher, DispatchError, InvocationArgumentError
from gway.expression import MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT
from gway.project import Project
from gway.registry import Registry


class InvokeFixtureAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (
            Command(
                ("echo",),
                parameters=(
                    Parameter("value", required=True, positional=True, annotation=str),
                ),
            ),
            Command(
                ("nested", "status"),
                parameters=(
                    Parameter("depth", annotation=int, default=2),
                    Parameter(
                        "enabled",
                        annotation=bool,
                        default=True,
                        consumes_value=False,
                        negative_options=("--no-enabled",),
                    ),
                    Parameter(
                        "include_impact",
                        annotation=bool,
                        default=True,
                        consumes_value=False,
                        negative_options=("--no-include-impact",),
                    ),
                ),
            ),
        )

    def describe(self, path: tuple[str, ...]) -> Command:
        return next(command for command in self.commands() if command.path == path)

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        return {"path": path, "argv": argv}


def _fixture_dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "fixture"
aliases = { fx = ["--mode", "alias"] }

[adapter]
type = "invoke-fixture"
""",
        encoding="utf-8",
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(root)
    adapters = AdapterRegistry()
    adapters.register("invoke-fixture", InvokeFixtureAdapter)
    return Dispatcher(registry, adapters)


def _python_dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "python-fixture"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "pyapi"

[adapter]
type = "python"
module = "api_fixture"
""",
        encoding="utf-8",
    )
    (root / "api_fixture.py").write_text(
        """def typed(
    number: int,
    ratio: float = 1.5,
    enabled: bool = True,
    template: str = "[project.name]",
):
    return {
        "number": number,
        "ratio": ratio,
        "enabled": enabled,
        "template": template,
    }


def fails():
    raise ValueError("private application detail")
""",
        encoding="utf-8",
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(root)
    return Dispatcher(registry)


def test_invoke_maps_named_required_positional_argument(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    result = dispatcher.invoke("fixture", ("echo",), {"value": "hello"})

    assert result == {"path": ("echo",), "argv": ["hello"]}


def test_invoke_maps_optional_and_boolean_arguments(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    result = dispatcher.invoke(
        "fixture",
        ("nested", "status"),
        {"depth": "3", "enabled": "false", "include-impact": "true"},
    )

    assert result == {
        "path": ("nested", "status"),
        "argv": ["--depth", "3", "--no-enabled", "--include-impact"],
    }


def test_invoke_preserves_alias_bound_arguments(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    result = dispatcher.invoke("FX", ("echo",), {"value": "hello"})

    assert result == {
        "path": ("echo",),
        "argv": ["--mode", "alias", "hello"],
    }


def test_invoke_treats_sigil_looking_values_as_literal(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    result = dispatcher.invoke("fixture", ("echo",), {"value": "[project.name]"})

    assert result["argv"] == ["[project.name]"]


def test_invoke_does_not_fill_arguments_from_chain_context(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    with chain_context_scope({"value": "from-context"}):
        with pytest.raises(InvocationArgumentError, match="missing required arguments: value"):
            dispatcher.invoke("fixture", ("echo",))


def test_invoke_rejects_unknown_and_non_string_arguments(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    with pytest.raises(InvocationArgumentError, match="unknown argument"):
        dispatcher.invoke("fixture", ("echo",), {"other": "value"})
    with pytest.raises(InvocationArgumentError, match="must be a string"):
        dispatcher.invoke("fixture", ("echo",), {"value": 3})  # type: ignore[dict-item]


def test_invoke_requires_exactly_one_command_path(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    with pytest.raises(DispatchError, match="exactly one command"):
        dispatcher.invoke("fixture", ("nested", "status", "extra"))


def test_invoke_rejects_managed_program_projects(tmp_path: Path) -> None:
    dispatcher = _fixture_dispatcher(tmp_path)

    for project in (MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT):
        with pytest.raises(DispatchError, match="does not support managed programs"):
            dispatcher.invoke(project, ("anything",))


def test_invoke_reuses_python_adapter_type_conversion_and_defaults(tmp_path: Path) -> None:
    dispatcher = _python_dispatcher(tmp_path)

    result = dispatcher.invoke(
        "pyapi",
        ("typed",),
        {"number": "7", "ratio": "2.5", "enabled": "false"},
    )

    assert result == {
        "number": 7,
        "ratio": 2.5,
        "enabled": False,
        "template": "[project.name]",
    }


def test_invoke_classifies_python_type_conversion_as_argument_error(tmp_path: Path) -> None:
    dispatcher = _python_dispatcher(tmp_path)

    with pytest.raises(InvocationArgumentError) as exc_info:
        dispatcher.invoke("pyapi", ("typed",), {"number": "not-an-int"})

    assert "number" in str(exc_info.value)


def test_invoke_preserves_callable_value_errors(tmp_path: Path) -> None:
    dispatcher = _python_dispatcher(tmp_path)

    with pytest.raises(ValueError) as exc_info:
        dispatcher.invoke("pyapi", ("fails",))

    assert type(exc_info.value) is ValueError
    assert str(exc_info.value) == "private application detail"
