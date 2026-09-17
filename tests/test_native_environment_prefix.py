from __future__ import annotations

from pathlib import Path

import pytest
from sigils import Sigil

from gway.config import GwayPaths
from gway.project import ManifestError, Project
from gway.sigils import project_context, project_environment_name


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(tmp_path / "config", tmp_path / "data")


def _arthexis_project(tmp_path: Path) -> Project:
    return Project(
        name="arthexis",
        path=tmp_path,
        adapter_type="python",
        adapter_config={},
        environment_prefix="arthexis",
        variables={
            "arthexis": {
                "data": ".arthexis/data",
                "cache": {"root": ".arthexis/cache"},
            },
            "repo": {"endpoint": "https://repo.example.com"},
        },
    )


def test_project_environment_name_strips_owner_namespace_once(tmp_path: Path) -> None:
    project = _arthexis_project(tmp_path)

    assert project.environment_prefix == "ARTHEXIS"
    assert project_environment_name(project, ("arthexis", "data")) == "ARTHEXIS_DATA"
    assert (
        project_environment_name(project, ("arthexis", "cache", "root"))
        == "ARTHEXIS_CACHE_ROOT"
    )


def test_native_environment_wins_over_gway_and_manifest(tmp_path: Path, monkeypatch) -> None:
    project = _arthexis_project(tmp_path)
    monkeypatch.setenv("GWAY_ARTHEXIS_DATA", "/gway/data")
    monkeypatch.setenv("ARTHEXIS_DATA", "/native/data")

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert Sigil("[arthexis.data]").solve(context) == "/native/data"


def test_gway_environment_remains_fallback_when_native_missing(
    tmp_path: Path, monkeypatch
) -> None:
    project = _arthexis_project(tmp_path)
    monkeypatch.delenv("ARTHEXIS_DATA", raising=False)
    monkeypatch.setenv("GWAY_ARTHEXIS_DATA", "/gway/data")

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert Sigil("[arthexis.data]").solve(context) == "/gway/data"


def test_manifest_value_remains_default_when_environment_missing(
    tmp_path: Path, monkeypatch
) -> None:
    project = _arthexis_project(tmp_path)
    monkeypatch.delenv("ARTHEXIS_DATA", raising=False)
    monkeypatch.delenv("GWAY_ARTHEXIS_DATA", raising=False)

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert Sigil("[arthexis.data]").solve(context) == ".arthexis/data"


def test_runtime_context_wins_over_native_environment(tmp_path: Path, monkeypatch) -> None:
    project = _arthexis_project(tmp_path)
    monkeypatch.setenv("ARTHEXIS_DATA", "/native/data")

    context = project_context(
        project,
        ("show",),
        paths=_paths(tmp_path),
        extra_context={"arthexis": {"data": "/runtime/data"}},
    )

    assert Sigil("[arthexis.data]").solve(context) == "/runtime/data"


def test_unrelated_namespace_does_not_use_project_native_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    project = _arthexis_project(tmp_path)
    monkeypatch.setenv("ARTHEXIS_REPO_ENDPOINT", "https://wrong.example.com")
    monkeypatch.setenv("GWAY_REPO_ENDPOINT", "https://gway.example.com")

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert project_environment_name(project, ("repo", "endpoint")) is None
    assert Sigil("[repo.endpoint]").solve(context) == "https://gway.example.com"


def test_alias_does_not_establish_native_namespace(tmp_path: Path, monkeypatch) -> None:
    project = Project(
        name="arthexis",
        aliases=("energy",),
        path=tmp_path,
        adapter_type="python",
        adapter_config={},
        environment_prefix="ARTHEXIS",
        variables={"energy": {"data": "manifest"}},
    )
    monkeypatch.setenv("ARTHEXIS_DATA", "native")
    monkeypatch.setenv("GWAY_ENERGY_DATA", "generic")

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert project_environment_name(project, ("energy", "data")) is None
    assert Sigil("[energy.data]").solve(context) == "generic"


def test_project_without_prefix_keeps_gway_only_behavior(tmp_path: Path, monkeypatch) -> None:
    project = Project(
        name="arthexis",
        path=tmp_path,
        adapter_type="python",
        adapter_config={},
        variables={"arthexis": {"data": "manifest"}},
    )
    monkeypatch.setenv("ARTHEXIS_DATA", "native")
    monkeypatch.setenv("GWAY_ARTHEXIS_DATA", "generic")

    context = project_context(project, ("show",), paths=_paths(tmp_path))

    assert project_environment_name(project, ("arthexis", "data")) is None
    assert Sigil("[arthexis.data]").solve(context) == "generic"


def test_manifest_parses_and_round_trips_environment_prefix(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "arthexis"
environment_prefix = "arthexis"

[adapter]
type = "python"
module = "commands"

[variables.arthexis]
data = ".arthexis/data"
""",
        encoding="utf-8",
    )

    project = Project.from_path(root)
    restored = Project.from_record(project.to_record())

    assert project.environment_prefix == "ARTHEXIS"
    assert restored.environment_prefix == "ARTHEXIS"


@pytest.mark.parametrize("value", ["", " ", "_ARTHEXIS", "ARTHEXIS_", "ARTHEXIS-DATA", "9ARTHEXIS"])
def test_manifest_rejects_invalid_environment_prefix(tmp_path: Path, value: str) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "gway.toml").write_text(
        f"""[project]
name = "arthexis"
environment_prefix = {value!r}

[adapter]
type = "python"
module = "commands"
""",
        encoding="utf-8",
    )

    with pytest.raises((ManifestError, Exception)):
        Project.from_path(root)
