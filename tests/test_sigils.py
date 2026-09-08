from __future__ import annotations

from pathlib import Path

from sigils import Sigil

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.sigils import base_context, capture_cli_values, gway_context, resolve_cli_values


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


def _register_live_project(tmp_path: Path) -> GwayPaths:
    project_root = tmp_path / "health"
    project_root.mkdir()
    (project_root / "live_values.py").write_text(
        "_calls = 0\n"
        "\n"
        "def tick():\n"
        "    global _calls\n"
        "    _calls += 1\n"
        "    return _calls\n"
        "\n"
        "def one():\n"
        "    return 1\n"
        "\n"
        "def zero():\n"
        "    return 0\n"
        "\n"
        "def echo(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    Registry(paths).register(
        Project(
            name="health",
            path=project_root,
            adapter_type="python",
            adapter_config={"module": "live_values"},
            aliases=("h",),
        )
    )
    return paths


def test_gway_sigil_values_are_memoized_per_context(tmp_path: Path) -> None:
    paths = _register_live_project(tmp_path)

    first_render = gway_context(paths)
    assert Sigil("[health.tick]-[health.tick]-[h.tick]").solve(first_render) == "1-1-1"

    second_render = gway_context(paths)
    assert Sigil("[health.tick]").solve(second_render) == "2"


def test_gway_sigil_values_do_not_supply_arguments(tmp_path: Path) -> None:
    paths = _register_live_project(tmp_path)

    assert Sigil("[health.echo]").solve(gway_context(paths)) == "[health.echo]"


def test_gway_sigil_values_support_loose_and_strict_fallbacks(tmp_path: Path) -> None:
    paths = _register_live_project(tmp_path)

    assert Sigil("[health.zero|:offline]").solve(gway_context(paths)) == "offline"
    assert Sigil("[health.zero||:offline]").solve(gway_context(paths)) == "0"
    assert Sigil("[health.echo||health.one||:offline]").solve(gway_context(paths)) == "1"
