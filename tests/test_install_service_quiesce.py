from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import gway.runtime as runtime_module
from gway.project import Project
from gway.runtime import GwayRuntime


def _project(tmp_path: Path, revision: str = "old-revision") -> Project:
    return Project(
        name="arthexis",
        path=tmp_path / "arthexis",
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        repository="arthexis/arthexis",
        revision=revision,
    )


def test_reinstall_with_service_quiesces_existing_units_before_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = _project(tmp_path)
    refreshed = _project(tmp_path, "new-revision")
    events: list[object] = []

    class Registry:
        def get(self, name: str):
            assert name == "arthexis"
            return previous

    class FakeInstaller:
        def __init__(self, registry) -> None:
            assert isinstance(registry, Registry)

        def install(self, name: str, **kwargs):
            events.append(("install", name, kwargs))
            return refreshed

    monkeypatch.setattr(runtime_module, "Installer", FakeInstaller)
    monkeypatch.setattr(
        runtime_module,
        "_quiesce_project_services",
        lambda selected: events.append(("quiesce", selected.revision)) or ("web-local", "worker"),
    )
    monkeypatch.setattr(
        runtime_module,
        "_install_project_service",
        lambda selected, profile=None: events.append(
            ("service", selected.revision, profile)
        )
        or {"status": "installed"},
    )

    runtime = GwayRuntime(SimpleNamespace(registry=Registry()))  # type: ignore[arg-type]
    result = runtime._run_install(
        ["arthexis", "--service", "--service-profile", "Watchtower", "--role", "Watchtower"]
    )

    assert result["status"] == "installed"
    assert events[0] == ("quiesce", "old-revision")
    assert events[1][0:2] == ("install", "arthexis")  # type: ignore[index]
    assert events[2] == ("service", "new-revision", "Watchtower")


def test_reinstall_failure_restores_previously_active_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = _project(tmp_path)
    events: list[object] = []

    class Registry:
        def get(self, name: str):
            assert name == "arthexis"
            return previous

    class FakeInstaller:
        def __init__(self, registry) -> None:
            assert isinstance(registry, Registry)

        def install(self, name: str, **kwargs):
            events.append(("install", name, kwargs))
            raise RuntimeError("lifecycle failed")

    monkeypatch.setattr(runtime_module, "Installer", FakeInstaller)
    monkeypatch.setattr(
        runtime_module,
        "_quiesce_project_services",
        lambda selected: events.append(("quiesce", selected.revision)) or ("web-local", "worker"),
    )
    monkeypatch.setattr(
        runtime_module,
        "_restore_project_services",
        lambda selected, services: events.append(
            ("restore", selected.revision, tuple(services))
        ),
    )

    runtime = GwayRuntime(SimpleNamespace(registry=Registry()))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="lifecycle failed"):
        runtime._run_install(["arthexis", "--service", "--role", "Watchtower"])

    assert events == [
        ("quiesce", "old-revision"),
        ("install", "arthexis", {"arguments": ["--role", "Watchtower"]}),
        ("restore", "old-revision", ("web-local", "worker")),
    ]
