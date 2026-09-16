from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import gway.runtime as runtime_module
from gway.project import Project
from gway.runtime import GwayRuntime


def _project(tmp_path: Path) -> Project:
    return Project(
        name="arthexis",
        path=tmp_path / "arthexis",
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        repository="arthexis/arthexis",
        revision="old-revision",
    )


def test_quiesce_stops_only_active_services_in_reverse_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    calls: list[tuple[str, str | None]] = []

    class FakeServiceManager:
        def __init__(
            self,
            selected: Project,
            *,
            service: str | None = None,
            all_services: bool = False,
            profile: str | None = None,
        ) -> None:
            assert selected is project
            self.service = service
            self.all_services = all_services
            self.profile = profile

        def status(self):
            assert self.all_services is True
            return [
                {"service": "web-local", "active": True},
                {"service": "web-edge", "active": False},
                {"service": "worker", "active": True},
                {"service": "beat", "active": True},
            ]

        def stop(self) -> None:
            calls.append(("stop", self.service))

        def start(self) -> None:
            calls.append(("start", self.service))

    monkeypatch.setattr(runtime_module._base, "ServiceManager", FakeServiceManager)

    active = runtime_module._quiesce_project_services(project)
    runtime_module._restore_project_services(project, active)

    assert active == ("web-local", "worker", "beat")
    assert calls == [
        ("stop", "beat"),
        ("stop", "worker"),
        ("stop", "web-local"),
        ("start", "web-local"),
        ("start", "worker"),
        ("start", "beat"),
    ]


def test_upgrade_service_failure_restores_previous_active_units_after_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    events: list[object] = []

    class Registry:
        def get(self, name: str):
            assert name == "arthexis"
            return project

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            assert isinstance(registry, Registry)

        def project_result(self, name: str, **kwargs):
            events.append(("upgrade", name, kwargs))
            raise RuntimeError("lifecycle failed after rollback")

    monkeypatch.setattr(runtime_module, "Upgrader", FakeUpgrader)
    monkeypatch.setattr(
        runtime_module,
        "_quiesce_project_services",
        lambda selected: events.append(("quiesce", selected.name)) or ("web-local", "worker"),
    )
    monkeypatch.setattr(
        runtime_module,
        "_restore_project_services",
        lambda selected, services: events.append(("restore", selected.name, tuple(services))),
    )

    dispatcher = SimpleNamespace(registry=Registry())
    runtime = GwayRuntime(dispatcher)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="lifecycle failed after rollback"):
        runtime._run_upgrade(
            ["arthexis", "--service", "--service-profile", "Watchtower", "--role", "Watchtower"]
        )

    assert events[0] == ("quiesce", "arthexis")
    assert events[1][0:2] == ("upgrade", "arthexis")  # type: ignore[index]
    assert events[2] == ("restore", "arthexis", ("web-local", "worker"))


def test_upgrade_service_profile_is_used_for_successful_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    refreshed = Project(
        name=project.name,
        path=project.path,
        adapter_type=project.adapter_type,
        adapter_config=project.adapter_config,
        repository=project.repository,
        revision="new-revision",
    )
    calls: list[object] = []

    class Registry:
        def get(self, name: str):
            assert name == "arthexis"
            return project

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def project_result(self, name: str, **kwargs):
            calls.append(("upgrade", name, kwargs))
            return SimpleNamespace(
                project=refreshed,
                changed=True,
                installed=False,
                force_used=False,
                force_error_type=None,
                force_error=None,
                dirty_files=(),
            )

    monkeypatch.setattr(runtime_module, "Upgrader", FakeUpgrader)
    monkeypatch.setattr(runtime_module, "_quiesce_project_services", lambda selected: ())

    def install_service(selected: Project, *, profile: str | None = None):
        calls.append(("service", selected.revision, profile))
        return {"status": "installed", "profile": profile}

    monkeypatch.setattr(runtime_module, "_install_project_service", install_service)

    runtime = GwayRuntime(SimpleNamespace(registry=Registry()))  # type: ignore[arg-type]
    result = runtime._run_upgrade(
        ["arthexis", "--service", "--service-profile", "Watchtower", "--role", "Watchtower"]
    )

    assert result["status"] == "upgraded"
    assert result["service"] == {"status": "installed", "profile": "Watchtower"}
    assert calls[-1] == ("service", "new-revision", "Watchtower")


def test_service_profile_requires_service_flag(tmp_path: Path) -> None:
    runtime = GwayRuntime(SimpleNamespace(registry=SimpleNamespace()))  # type: ignore[arg-type]

    with pytest.raises(Exception, match="--service-profile requires --service"):
        runtime._run_upgrade(["arthexis", "--service-profile", "Watchtower"])
