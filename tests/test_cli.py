from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import gway.cli as cli
from gway import __version__
from gway.cli import _render_result, main
from gway.registry import Registry

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


def test_install_sigils_uses_short_runtime_alias(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))

    assert main(["install", "sigils"]) == 0
    output = capsys.readouterr().out
    assert "status: installed" in output
    assert "name: sigils" in output
    assert "distribution: gway-sigils" in output

    assert main(["list"]) == 0
    assert capsys.readouterr().out == ""


def test_register_list_info_and_path(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))

    assert main(["register", str(project)]) == 0
    capsys.readouterr()

    assert main(["list"]) == 0
    listing = capsys.readouterr().out
    assert "name: wireguard" in listing
    assert "- wg" in listing

    assert main(["info", "wg"]) == 0
    info = capsys.readouterr().out
    assert "name: wireguard" in info
    assert "adapter: python" in info

    assert main(["path", "wireguard"]) == 0
    assert capsys.readouterr().out.strip() == str(project.resolve())


def test_global_json_applies_to_core_output(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))

    assert main(["register", str(project)]) == 0
    capsys.readouterr()

    assert main(["--json", "info", "wg"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["name"] == "wireguard"
    assert output["aliases"] == ["wg"]
    assert output["adapter"] == "python"


def test_pretty_output_indents_nested_values_and_supports_color(capsys) -> None:
    value = {
        "status": "ok",
        "device": {
            "online": True,
            "ports": [1, 2],
        },
    }

    _render_result(value, color=False)
    assert capsys.readouterr().out == (
        "status: ok\n"
        "device:\n"
        "  online: true\n"
        "  ports:\n"
        "    - 1\n"
        "    - 2\n"
    )

    _render_result(value, color=True)
    assert "\033[" in capsys.readouterr().out


def test_core_permission_failure_suggests_original_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project = tmp_path / "wireguard"
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "_can_suggest_sudo", lambda: True)

    def denied(self, path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(Registry, "register_path", denied)

    assert main(["register", str(project)]) == 2
    error = capsys.readouterr().err
    assert "Permission denied" in error
    assert f"sudo gway register {project}" in error


def test_unknown_project_returns_error(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    assert main(["info", "missing"]) == 2
    assert "project is not registered: missing" in capsys.readouterr().err
