from pathlib import Path

import pytest

from gway.security.controller import Controller


class _Gateway:
    def __init__(self):
        self.install = None
        self.uninstall = None
        self._project_path = None
        self.events = []

    def wrap(self, name, callable_):
        self.events.append(("wrap", name))
        return callable_

    def _install(self, source, **kwargs):
        self.events.append(("install", source, kwargs))
        return {"installed": source}

    def _uninstall(self, project, **kwargs):
        self.events.append(("uninstall", project, kwargs))
        return {"uninstalled": project}

    def converge_security_scopes(self):
        self.events.append(("converge",))
        return {"added": [], "updated": [], "retired": [], "unchanged": []}


def test_install_lifecycle_converges_after_success(monkeypatch):
    gateway = _Gateway()
    controller = Controller(gateway)
    monkeypatch.setattr(controller, "_refresh_publications", lambda: gateway.events.append(("refresh",)))

    result = gateway.install("demo", ref="main", upgrade=True)

    assert result == {"installed": "demo"}
    assert gateway.events[-2:] == [
        ("install", "demo", {"ref": "main", "upgrade": True, "force": False, "stash": False, "system": False}),
        ("refresh",),
    ]


def test_uninstall_lifecycle_refreshes_for_scope_retirement(monkeypatch):
    gateway = _Gateway()
    controller = Controller(gateway)
    monkeypatch.setattr(controller, "_refresh_publications", lambda: gateway.events.append(("refresh",)))

    result = gateway.uninstall("demo")

    assert result == {"uninstalled": "demo"}
    assert gateway.events[-2:] == [
        ("uninstall", "demo", {"system": False}),
        ("refresh",),
    ]


def test_convergence_failure_blocks_lifecycle_success(monkeypatch):
    gateway = _Gateway()
    controller = Controller(gateway)

    def fail():
        raise ValueError("unsafe published read scope")

    monkeypatch.setattr(controller, "_refresh_publications", fail)

    with pytest.raises(ValueError, match="unsafe published read scope"):
        gateway.install("demo")

    assert gateway.events[-1][0] == "install"


def test_refresh_rediscovers_publishers_before_convergence(monkeypatch):
    gateway = _Gateway()
    controller = Controller(gateway)

    import gway.config as config

    def discover(runtime):
        assert runtime is gateway
        gateway.events.append(("discover",))
        runtime._published_scopes = {}
        return {}

    monkeypatch.setattr(config, "discover_managed_projects", discover)

    report = controller._refresh_publications()

    assert report == {"added": [], "updated": [], "retired": [], "unchanged": []}
    assert gateway.events[-2:] == [("discover",), ("converge",)]


def test_refresh_republishes_active_local_project(monkeypatch, tmp_path):
    project = tmp_path / "pyproject.toml"
    project.write_text(
        """
[project]
name = "local-demo"

[tool.gway.scopes.local-read]
operations = []
environment = []
semantic_terms = ["local", "read"]
""".lstrip(),
        encoding="utf-8",
    )

    gateway = _Gateway()
    gateway._project_path = Path(project)
    controller = Controller(gateway)

    import gway.config as config

    monkeypatch.setattr(
        config,
        "discover_managed_projects",
        lambda runtime: setattr(runtime, "_published_scopes", {}),
    )

    published = []

    def publish(runtime, data, *, source):
        published.append((runtime, data, source))
        return {}, ()

    monkeypatch.setattr(config, "_publish_project_capabilities", publish)

    controller._refresh_publications()

    assert published[0][0] is gateway
    assert published[0][2] == "local-demo"
    assert gateway.events[-1] == ("converge",)
