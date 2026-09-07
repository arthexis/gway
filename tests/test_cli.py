from __future__ import annotations

import subprocess
import sys

import pytest

from gway import __version__
from gway.cli import main


def test_main_without_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Manage and dispatch GWAY/Arthexis projects." in output


def test_help_flag_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "usage: gway" in capsys.readouterr().out


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_module_entrypoint_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "gway", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: gway" in result.stdout


def test_legacy_projects_package_is_not_imported() -> None:
    assert "projects" not in sys.modules
