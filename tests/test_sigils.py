from __future__ import annotations

from pathlib import Path

from gway.config import GwayPaths
from gway.project import Project
from gway.sigils import base_context, capture_cli_values, resolve_cli_values


def test_eager_values_capture_before_lazy_resolution(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")

    monkeypatch.chdir(first)
    templates = capture_cli_values(["%[cwd]", "[cwd]"], paths=paths)

    monkeypatch.chdir(second)
    context = base_context(paths)
    resolved = [template.solve(context) for template in templates]

    assert resolved == [str(first), str(second)]


def test_lazy_context_exposes_project_and_command(tmp_path: Path) -> None:
    project_root = tmp_path / "demo"
    project_root.mkdir()
    project = Project(
        name="demo",
        path=project_root,
        adapter_type="python",
        adapter_config={"module": "demo.gway"},
        aliases=("d",),
        repository="arthexis/demo",
        revision="abc123",
    )
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")

    resolved = resolve_cli_values(
        [
            "[project.name]",
            "[project.path]",
            "[project.adapter]",
            "[project.repository]",
            "[project.revision]",
            "[command.name]",
            "[command.path]",
            "[gway.data_dir]",
        ],
        project,
        ("peer", "add"),
        paths=paths,
    )

    assert resolved == [
        "demo",
        str(project_root),
        "python",
        "arthexis/demo",
        "abc123",
        "add",
        "peer add",
        str(paths.data_dir),
    ]
