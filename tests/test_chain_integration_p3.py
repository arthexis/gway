from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.transfer import TRANSFER_PREFIX, decode_transfer, encode_transfer, transfer_scope

DJANGO_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "django_project"


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "p3-python"
    root.mkdir()
    (root / "p3_commands.py").write_text(
        """from typing import Literal


def text_number() -> str:
    return "42"


def ready() -> str:
    return "ready"


def bracket_text() -> str:
    return "[cwd]"


def option_help() -> str:
    return "--help"


def option_unknown() -> str:
    return "--unknown"


def option_separator() -> str:
    return "--"


def accept_int(value: int) -> int:
    return value


def accept_ready(value: Literal["ready"]) -> str:
    return value


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("p3_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="p3",
            path=root,
            adapter_type="python",
            adapter_config={"module": "p3_commands"},
        )
    )
    registry.register_path(DJANGO_FIXTURE_ROOT)
    return Dispatcher(registry)


def test_transferred_string_is_converted_before_python_int_validation(
    tmp_path: Path, capsys
) -> None:
    dispatcher = _dispatcher(tmp_path)
    assert main(["p3", "text-number", "-", "p3", "accept-int"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "42\n"


def test_transferred_string_is_restored_before_literal_choice_validation(
    tmp_path: Path, capsys
) -> None:
    dispatcher = _dispatcher(tmp_path)
    assert main(["p3", "ready", "-", "p3", "accept-ready"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "ready\n"


def test_python_result_reaches_django_command_without_internal_token(
    tmp_path: Path, capsys
) -> None:
    dispatcher = _dispatcher(tmp_path)
    assert main(["p3", "bracket-text", "-", "django-fixture", "echo"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "[cwd]\n"


@pytest.mark.parametrize(
    ("producer", "value"),
    [
        ("option-help", "--help"),
        ("option-unknown", "--unknown"),
        ("option-separator", "--"),
    ],
)
def test_option_shaped_python_result_reaches_django_as_data(
    tmp_path: Path, capsys, producer: str, value: str
) -> None:
    dispatcher = _dispatcher(tmp_path)
    assert (
        main(
            ["p3", producer, "-", "django-fixture", "echo"],
            dispatcher=dispatcher,
        )
        == 0
    )
    assert capsys.readouterr().out == f"{value}\n"


def test_django_result_reaches_python_command(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    assert (
        main(
            ["django-fixture", "echo", "hello", "-", "p3", "echo"],
            dispatcher=dispatcher,
        )
        == 0
    )
    assert capsys.readouterr().out == "hello\n"


def test_predictable_old_token_shape_never_aliases_active_transfer() -> None:
    spoof = f"{TRANSFER_PREFIX}0"
    with transfer_scope():
        actual = encode_transfer("real")
        assert actual != spoof
        assert decode_transfer(spoof) == spoof
        assert decode_transfer(actual) == "real"
