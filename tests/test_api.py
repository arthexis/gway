from pathlib import Path

import pytest

from gway import Gway, gw, gway


def test_public_gway_facade_is_stable_singleton():
    assert isinstance(gway, Gway)
    assert gw is gway


def test_facade_reads_shared_registry(tmp_path: Path, monkeypatch):
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(
        '[project]\nname = "wireguard"\naliases = ["wg"]\n\n[adapter]\ntype = "python"\nmodule = "example.gway"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    gway.registry.register_path(project)

    assert gway.project("wg").name == "wireguard"
    assert [item.name for item in gway.projects()] == ["wireguard"]


def test_managed_namespace_is_reserved_until_dispatcher_exists(tmp_path: Path, monkeypatch):
    project = tmp_path / "wireguard"
    project.mkdir()
    (project / "gway.toml").write_text(
        '[project]\nname = "wireguard"\n\n[adapter]\ntype = "python"\nmodule = "example.gway"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    gway.registry.register_path(project)

    with pytest.raises(AttributeError, match="managed command dispatch"):
        _ = gway.wireguard
