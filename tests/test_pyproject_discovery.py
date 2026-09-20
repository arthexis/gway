from types import SimpleNamespace

import pytest

from gway.config import _valid_installation, find_manifest, project_entrypoints
from gway.install.ops import _local_intent
from gway.install.activation import scripts as activation_scripts
from gway.install.source import project_name
from gway.project import project_scripts, scripts


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


def test_project_scripts_reads_standard_python_entrypoints(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[project.scripts]\n'
        'hello = "demo:main"\n',
        encoding="utf-8",
    )

    assert project_scripts(tmp_path) == {"hello": "demo:main"}
    assert activation_scripts(tmp_path) == {"hello": "demo:main"}


def test_standard_project_scripts_override_legacy_duplicates(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[project.scripts]\n'
        'hello = "demo:new_main"\n',
        encoding="utf-8",
    )
    (tmp_path / "gway.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[install.scripts]\n'
        'hello = "demo:old_main"\n'
        'legacy = "demo:legacy_main"\n',
        encoding="utf-8",
    )

    with pytest.warns(DeprecationWarning, match=r"\[install\.scripts\]"):
        discovered = scripts(tmp_path)

    assert discovered == {
        "hello": "demo:new_main",
        "legacy": "demo:legacy_main",
    }


def test_gateway_bootstrap_exposes_project_script_as_operation(tmp_path, monkeypatch):
    package = tmp_path / "demo.py"
    package.write_text(
        'def main(name="world"):\n'
        '    return f"hello {name}"\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[project.scripts]\n'
        'hello = "demo:main"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime("hello Ada") == "hello Ada"
    assert runtime("demo hello Ada") == "hello Ada"
