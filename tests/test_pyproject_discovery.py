from types import SimpleNamespace

import pytest

from gway.config import _valid_installation, find_project_file
from gway.install.ops import _local_intent
from gway.install.source import project_name
from gway.project import project_scripts


def test_project_name_uses_pyproject_without_gway_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    assert project_name(tmp_path) == "demo"


def test_project_name_rejects_gway_toml_only_project(tmp_path):
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires pyproject.toml"):
        project_name(tmp_path)


def test_find_project_file_prefers_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (tmp_path / "gway.toml").write_text(
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )

    assert find_project_file(tmp_path) == pyproject


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


def test_project_scripts_reads_standard_python_entrypoints(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[project.scripts]\n'
        'hello = "demo:main"\n',
        encoding="utf-8",
    )

    assert project_scripts(tmp_path) == {"hello": "demo:main"}


def test_standard_project_scripts_ignore_gway_toml(tmp_path):
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
        'legacy = "demo:legacy_main"\n',
        encoding="utf-8",
    )

    assert project_scripts(tmp_path) == {"hello": "demo:new_main"}


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


def test_pyproject_semantic_variables_are_available_to_sigils(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[tool.gway.variables]\n'
        'region = "local"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime.resolve("[region]") == "local"


def test_environment_overrides_pyproject_semantic_variables(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        '[tool.gway.variables]\n'
        'region = "local"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REGION", "production")
    monkeypatch.chdir(tmp_path)

    from gway.gateway import Gateway

    runtime = Gateway()

    assert runtime.resolve("[region]") == "production"
