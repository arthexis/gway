from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from gway import __version__
from gway.cli import main

MANIFEST = """[project]
name = "wireguard"
aliases = ["wg"]

[adapter]
type = "python"
module = "example.gway"
"""


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


def test_install_sigils_uses_short_runtime_alias(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "sigils"]) == 0
    output = capsys.readouterr().out.strip()
    assert output.startswith("installed sigils\tgway-sigils@")


def test_register_list_info_and_path(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))

    assert main(["register", str(project)]) == 0
    capsys.readouterr()

    assert main(["list"]) == 0
    assert "wireguard (wg)" in capsys.readouterr().out

    assert main(["info", "wg"]) == 0
    info = capsys.readouterr().out
    assert "name: wireguard" in info
    assert "adapter: python" in info

    assert main(["path", "wireguard"]) == 0
    assert capsys.readouterr().out.strip() == str(project.resolve())


def test_unknown_project_returns_error(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    assert main(["info", "missing"]) == 2
    assert "project is not registered: missing" in capsys.readouterr().err
