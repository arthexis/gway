from __future__ import annotations

from pathlib import Path

from gway.adapters import AdapterRegistry
from gway.chain import run_chain
from gway.command import Command, Parameter
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.registry import Registry


class SignatureAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (
            Command(("produce",)),
            Command(("zero",)),
            Command(
                ("required",),
                parameters=(Parameter("value", required=True, positional=True),),
            ),
            Command(
                ("optional",),
                parameters=(Parameter("value", required=False, positional=True),),
            ),
            Command(
                ("variadic",),
                parameters=(Parameter("values", required=False, positional=True),),
            ),
        )

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        if path == ("produce",):
            return 42
        return list(argv)


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "signature-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        '''[project]
name = "signature"

[adapter]
type = "signature-test"
''',
        encoding="utf-8",
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(root)
    adapters = AdapterRegistry()
    adapters.register("signature-test", SignatureAdapter)
    return Dispatcher(registry, adapters)


def test_transfer_is_omitted_for_target_without_positionals(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["signature", "produce", "-", "signature", "zero"],
    )

    assert result == []


def test_required_positional_still_receives_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["signature", "produce", "-", "signature", "required"],
    )

    assert result == ["42"]


def test_optional_positional_still_receives_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["signature", "produce", "-", "signature", "optional"],
    )

    assert result == ["42"]


def test_variadic_positional_still_receives_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["signature", "produce", "-", "signature", "variadic"],
    )

    assert result == ["42"]


def test_transfer_omission_is_visible_in_explain_trace(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    with explain_scope() as trace:
        result = run_chain(
            dispatcher,
            ["signature", "produce", "-", "signature", "zero"],
        )

    assert result == []
    omitted = next(step for step in trace if step.kind == "transfer.omit")
    assert omitted.data["incoming"] == [42]
    assert omitted.data["reason"] == "target accepts no positional parameters"
