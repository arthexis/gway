from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
import gway.runner as runner_module
from gway.project import LifecycleHooks, Project
from gway.runner import Runner


def _project(path: Path) -> Project:
    return Project(
        name="arthexis",
        path=path,
        adapter_type="django",
        adapter_config={},
    )


def test_install_forwards_unconsumed_arguments(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}
    project = _project(tmp_path)

    class FakeInstaller:
        def __init__(self, registry) -> None:
            captured["registry"] = registry

        def install(self, spec: str, *, arguments=()) -> Project:
            captured["spec"] = spec
            captured["arguments"] = list(arguments)
            return project

    registry = object()
    dispatcher = SimpleNamespace(registry=registry)
    monkeypatch.setattr(cli, "Installer", FakeInstaller)

    assert cli.main(
        ["install", "arthexis", "--role", "Control"],
        dispatcher=dispatcher,
    ) == 0
    capsys.readouterr()

    assert captured == {
        "registry": registry,
        "spec": "arthexis",
        "arguments": ["--role", "Control"],
    }


def test_upgrade_consumes_gway_flags_and_forwards_the_rest(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    captured: dict[str, object] = {}
    project = _project(tmp_path)

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            captured["registry"] = registry

        def project(self, name: str, *, force: bool = False, arguments=()) -> Project:
            captured["name"] = name
            captured["force"] = force
            captured["arguments"] = list(arguments)
            return project

    registry = object()
    dispatcher = SimpleNamespace(registry=registry)
    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)

    assert cli.main(
        ["upgrade", "arthexis", "--role", "Watchtower", "--force"],
        dispatcher=dispatcher,
    ) == 0
    capsys.readouterr()

    assert captured == {
        "registry": registry,
        "name": "arthexis",
        "force": True,
        "arguments": ["--role", "Watchtower"],
    }


def test_lifecycle_runner_appends_forwarded_arguments(monkeypatch, tmp_path) -> None:
    environment = tmp_path / "venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()

    project = Project(
        name="arthexis",
        path=tmp_path,
        adapter_type="django",
        adapter_config={},
        environment=environment,
        lifecycle_hooks=LifecycleHooks(install="example.lifecycle:install"),
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    Runner().run_lifecycle(project, "install", ["--role", "Satellite"])

    command = captured["command"]
    assert command[:4] == [
        str(python),
        "-c",
        runner_module._HOOK_SCRIPT,
        "example.lifecycle:install",
    ]
    assert command[4:] == ["--role", "Satellite"]
