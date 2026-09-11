from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gway.bootstrap import main
from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry


def write_manifest(path: Path, *, name: str, aliases: tuple[str, ...] = ()) -> None:
    path.mkdir(parents=True, exist_ok=True)
    alias_text = ", ".join(f'"{alias}"' for alias in aliases)
    (path / "gway.toml").write_text(
        f'[project]\nname = "{name}"\naliases = [{alias_text}]\n\n'
        '[adapter]\ntype = "python"\nmodule = "example.gway"\n',
        encoding="utf-8",
    )


def test_base_uninstall_command_removes_renamed_project(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_HOME", str(data))
    monkeypatch.setenv("GWAY_CONFIG_HOME", str(tmp_path / "config"))
    paths = GwayPaths(tmp_path / "config", data)
    registry = Registry(paths)
    checkout = paths.projects_dir / "arthexis" / "gway-wire"
    environment = paths.environments_dir / "wireguard"

    write_manifest(checkout, name="wireguard", aliases=("wg",))
    environment.mkdir(parents=True)
    registry.register(
        replace(
            Project.from_path(checkout),
            repository="arthexis/gway-wire",
            environment=environment,
        )
    )
    write_manifest(checkout, name="wire", aliases=("wireguard", "wg"))

    assert main(["uninstall", "wire"]) == 0
    output = capsys.readouterr().out
    assert "status: uninstalled" in output
    assert "name: wireguard" in output
    assert registry.get("wireguard") is None
    assert not checkout.exists()
    assert not environment.exists()


def test_base_uninstall_supports_json(tmp_path: Path, monkeypatch, capsys) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_HOME", str(data))
    monkeypatch.setenv("GWAY_CONFIG_HOME", str(tmp_path / "config"))
    paths = GwayPaths(tmp_path / "config", data)
    registry = Registry(paths)
    checkout = tmp_path / "local"
    write_manifest(checkout, name="local")
    registry.register_path(checkout)

    assert main(["--json", "uninstall", "local"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "uninstalled"
    assert checkout.exists()


def test_base_uninstall_help(capsys) -> None:
    assert main(["uninstall", "--help"]) == 0
    assert "usage: gway uninstall" in capsys.readouterr().out
