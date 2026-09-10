from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
from gway.project import Project


def _project(name: str, root: Path) -> Project:
    return Project(
        name=name,
        path=root / name,
        adapter_type="python",
        adapter_config={"module": f"{name}.gway"},
        repository=f"arthexis/{name}",
        revision="abc123",
    )


def test_upgrade_gway_target_uses_self_upgrade(monkeypatch, tmp_path, capsys) -> None:
    calls: list[tuple[object, ...]] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            calls.append(("init", registry))

        def upgrade_self(self) -> None:
            calls.append(("self",))

    registry = object()
    dispatcher = SimpleNamespace(registry=registry)
    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)

    assert cli.main(["upgrade", "gway"], dispatcher=dispatcher) == 0
    capsys.readouterr()
    assert calls == [("init", registry), ("self",)]


def test_upgrade_accepts_self_and_managed_targets(monkeypatch, tmp_path, capsys) -> None:
    calls: list[tuple[object, ...]] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            calls.append(("init", registry))

        def upgrade_self(self) -> None:
            calls.append(("self",))

        def project_result(
            self,
            name: str,
            *,
            force: bool = False,
            reload: bool = False,
            arguments=(),
        ):
            calls.append(("project", name, force, reload, tuple(arguments)))
            return SimpleNamespace(project=_project(name, tmp_path), changed=True)

    registry = object()
    dispatcher = SimpleNamespace(registry=registry)
    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)

    assert cli.main(["upgrade", "gway", "arthexis"], dispatcher=dispatcher) == 0
    capsys.readouterr()
    assert calls == [
        ("init", registry),
        ("self",),
        ("project", "arthexis", False, False, ()),
    ]


def test_upgrade_accepts_multiple_managed_targets(monkeypatch, tmp_path, capsys) -> None:
    calls: list[str] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def project_result(
            self,
            name: str,
            *,
            force: bool = False,
            reload: bool = False,
            arguments=(),
        ):
            del force, reload, arguments
            calls.append(name)
            return SimpleNamespace(project=_project(name, tmp_path), changed=True)

    dispatcher = SimpleNamespace(registry=object())
    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)

    assert cli.main(["upgrade", "arthexis", "sigils"], dispatcher=dispatcher) == 0
    capsys.readouterr()
    assert calls == ["arthexis", "sigils"]


def test_upgrade_deduplicates_explicit_targets(monkeypatch, tmp_path, capsys) -> None:
    calls: list[str] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def upgrade_self(self) -> None:
            calls.append("gway")

        def project_result(
            self,
            name: str,
            *,
            force: bool = False,
            reload: bool = False,
            arguments=(),
        ):
            del force, reload, arguments
            calls.append(name)
            return SimpleNamespace(project=_project(name, tmp_path), changed=True)

    dispatcher = SimpleNamespace(registry=object())
    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)

    assert (
        cli.main(
            ["upgrade", "gway", "arthexis", "gway", "arthexis"],
            dispatcher=dispatcher,
        )
        == 0
    )
    capsys.readouterr()
    assert calls == ["gway", "arthexis"]
