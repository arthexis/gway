import json
from pathlib import Path

from gway.cli import main


MANIFEST = """[project]
name = "wireguard"
aliases = ["wg"]

[adapter]
type = "python"
module = "example.gway"
"""


def _register_project(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    assert main(["register", str(project)]) == 0
    capsys.readouterr()


def test_list_is_names_only_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    _register_project(tmp_path, monkeypatch, capsys)

    assert main(["list"]) == 0
    assert capsys.readouterr().out == "- wireguard\n"


def test_list_detail_preserves_project_metadata(tmp_path: Path, monkeypatch, capsys) -> None:
    _register_project(tmp_path, monkeypatch, capsys)

    assert main(["list", "--detail"]) == 0
    output = capsys.readouterr().out
    assert "name: wireguard" in output
    assert "adapter: python" in output
    assert "aliases:" in output
    assert "- wg" in output


def test_json_list_respects_detail_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    _register_project(tmp_path, monkeypatch, capsys)

    assert main(["--json", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == ["wireguard"]

    assert main(["--json", "list", "--detail"]) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert detailed[0]["name"] == "wireguard"
    assert detailed[0]["adapter"] == "python"
