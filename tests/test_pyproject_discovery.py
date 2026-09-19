from types import SimpleNamespace

import pytest

from gway.config import _valid_installation, find_manifest, project_entrypoints
from gway.install.ops import _local_intent
from gway.install.source import project_name
from gway.service.discovery import declares_services


def test_project_name_uses_pyproject_without_gway_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    assert project_name(tmp_path) == "demo"


def test_project_name_keeps_legacy_gway_toml_during_deprecation(tmp_path):
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    with pytest.warns(DeprecationWarning, match="gway.toml is deprecated"):
        assert project_name(tmp_path) == "legacy"


def test_find_manifest_prefers_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    assert find_manifest(tmp_path) == pyproject


def test_local_intent_recognizes_pyproject_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    assert _local_intent(str(tmp_path)) is True


def test_managed_installation_accepts_pyproject_without_gway_toml(tmp_path):
    projects = tmp_path / "projects"
    installed = projects / "demo"
    installed.mkdir(parents=True)
    (installed / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    record = SimpleNamespace(name="demo", install_path=installed)
    paths = SimpleNamespace(projects=projects)

    assert _valid_installation(record, paths) is True


def test_optional_legacy_metadata_helpers_tolerate_missing_gway_toml(tmp_path):
    assert project_entrypoints(tmp_path / "gway.toml") == ()
    assert declares_services(tmp_path / "gway.toml") is False
