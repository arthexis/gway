from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gway.adapters.python import PythonAdapter
from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry


def test_python_optional_bool_uses_zero_arity_metadata(tmp_path: Path) -> None:
    project = Project(
        name="demo",
        path=tmp_path,
        adapter_type="python",
        adapter_config={"module": "unused"},
    )
    adapter = PythonAdapter(project)

    def command(*, enabled: bool | None = None) -> bool | None:
        return enabled

    parameter = adapter._parameter_metadata(command)[0]

    assert parameter.annotation is bool
    assert parameter.consumes_value is False
    assert parameter.option_arity == 0
    assert parameter.default is None


def test_registry_allows_existing_reserved_name_to_reregister(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    project_root = tmp_path / "legacy-store"
    project_root.mkdir()
    legacy = Project(
        name="store",
        path=project_root,
        adapter_type="python",
        adapter_config={"module": "legacy"},
        repository="arthexis/legacy-store",
        revision="old",
    )
    paths.data_dir.mkdir(parents=True)
    paths.state_file.write_text(
        json.dumps({"version": 1, "projects": {"store": legacy.to_record()}}),
        encoding="utf-8",
    )

    updated = replace(legacy, revision="new")
    registry = Registry(paths)

    assert registry.register(updated) == updated
    assert registry.require("store").revision == "new"


def test_registry_preserves_legacy_reserved_alias_across_rename(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    project_root = tmp_path / "legacy"
    project_root.mkdir()
    legacy = Project(
        name="legacy",
        aliases=("result",),
        path=project_root,
        adapter_type="python",
        adapter_config={"module": "legacy"},
        repository="arthexis/legacy",
    )
    paths.data_dir.mkdir(parents=True)
    paths.state_file.write_text(
        json.dumps({"version": 1, "projects": {"legacy": legacy.to_record()}}),
        encoding="utf-8",
    )

    renamed = replace(legacy, name="modern")
    registry = Registry(paths)

    assert registry.register(renamed) == renamed
    assert registry.require("result").name == "modern"
