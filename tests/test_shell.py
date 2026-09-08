from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
import gway.shell as shell
from gway.cli import main


def test_install_status_and_uninstall_are_idempotent(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path), "SHELL": "/bin/bash"}
    bashrc = tmp_path / ".bashrc"
    original = "export EXAMPLE=1\n"
    bashrc.write_text(original, encoding="utf-8")

    first = shell.install_shell("bash", environ=env)
    assert first["status"] == "installed"
    assert first["changed"] is True
    assert bashrc.read_text(encoding="utf-8").count(shell.BEGIN_MARKER) == 1
    assert shell.ALIAS_LINE in bashrc.read_text(encoding="utf-8")

    second = shell.install_shell("bash", environ=env)
    assert second["changed"] is False
    assert bashrc.read_text(encoding="utf-8").count(shell.BEGIN_MARKER) == 1
    assert shell.shell_status("bash", environ=env)["status"] == "installed"

    removed = shell.uninstall_shell("bash", environ=env)
    assert removed["status"] == "uninstalled"
    assert removed["changed"] is True
    assert bashrc.read_text(encoding="utf-8") == original

    missing = shell.uninstall_shell("bash", environ=env)
    assert missing["status"] == "not-installed"
    assert missing["changed"] is False


def test_zsh_uses_zdotdir(tmp_path: Path) -> None:
    zdotdir = tmp_path / "zsh"
    env = {
        "HOME": str(tmp_path),
        "SHELL": "/bin/zsh",
        "ZDOTDIR": str(zdotdir),
    }

    result = shell.install_shell("zsh", environ=env)

    assert result["path"] == str(zdotdir / ".zshrc")
    assert shell.ALIAS_LINE in (zdotdir / ".zshrc").read_text(encoding="utf-8")


def test_launch_bash_sources_existing_rc_and_adds_alias(tmp_path: Path, monkeypatch) -> None:
    env = {"HOME": str(tmp_path), "SHELL": "/bin/bash"}
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("export FROM_USER_RC=1\n", encoding="utf-8")
    observed: dict[str, object] = {}

    monkeypatch.setattr(shell, "_shell_executable", lambda name, environ: "/bin/bash")

    def fake_run(command, *, env, check):
        observed["command"] = command
        observed["env"] = env
        observed["startup"] = Path(command[2]).read_text(encoding="utf-8")
        assert check is False
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(shell.subprocess, "run", fake_run)

    assert shell.launch_shell("bash", environ=env) == 7
    assert observed["command"][1] == "--rcfile"
    assert f". {bashrc}" in observed["startup"]
    assert shell.ALIAS_LINE in observed["startup"]
    assert "export GWAY_SHELL=1" in observed["startup"]


def test_launch_zsh_uses_temporary_zdotdir(tmp_path: Path, monkeypatch) -> None:
    env = {"HOME": str(tmp_path), "SHELL": "/bin/zsh"}
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("export FROM_USER_RC=1\n", encoding="utf-8")
    observed: dict[str, object] = {}

    monkeypatch.setattr(shell, "_shell_executable", lambda name, environ: "/bin/zsh")

    def fake_run(command, *, env, check):
        observed["command"] = command
        observed["env"] = env
        temporary_rc = Path(env["ZDOTDIR"]) / ".zshrc"
        observed["startup"] = temporary_rc.read_text(encoding="utf-8")
        assert check is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(shell.subprocess, "run", fake_run)

    assert shell.launch_shell("zsh", environ=env) == 0
    assert observed["command"] == ["/bin/zsh", "-i"]
    assert observed["env"]["ZDOTDIR"] != str(tmp_path)
    assert f". {zshrc}" in observed["startup"]
    assert shell.ALIAS_LINE in observed["startup"]


def test_cli_shell_print_is_raw(capsys, monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")
    dispatcher = SimpleNamespace(registry=object())

    assert main(["shell", "print"], dispatcher=dispatcher) == 0

    assert capsys.readouterr().out == shell.integration_snippet("bash")


def test_cli_bare_shell_returns_child_status(monkeypatch) -> None:
    dispatcher = SimpleNamespace(registry=object())
    called: list[str | None] = []

    def fake_launch(shell_name: str | None = None) -> int:
        called.append(shell_name)
        return 13

    monkeypatch.setattr(cli, "launch_shell", fake_launch)

    assert main(["shell", "--shell", "bash"], dispatcher=dispatcher) == 13
    assert called == ["bash"]
