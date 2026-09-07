from pathlib import Path

from gway import Gway, gw, gway

MANIFEST = """[project]
name = "wireguard"
aliases = ["wg"]

[adapter]
type = "python"
module = "example.gway"
"""


def test_public_gway_facade_is_stable_singleton():
    assert isinstance(gway, Gway)
    assert gw is gway


def test_facade_reads_shared_registry(tmp_path: Path, monkeypatch):
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    gway.registry.register_path(project)

    assert gway.project("wg").name == "wireguard"
    assert [item.name for item in gway.projects()] == ["wireguard"]
