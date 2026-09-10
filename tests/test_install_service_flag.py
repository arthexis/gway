from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
from gway.project import Project


class _Installer:
    project: Project

    def __init__(self, registry) -> None:
        self.registry = registry

    def install(self, spec: str, *, arguments=()) -> Project:
        return self.project


def _project(tmp_path: Path, manifest: str) -> Project:
    (tmp_path / "gway.toml").write_text(manifest, encoding="utf-8")
    return Project(
        name="demo",
        path=tmp_path,
        adapter_type="python",
        adapter_config={},
    )


def test_install_service_installs_manifest_service(tmp_path, monkeypatch, capsys) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "demo"

[adapter]
type = "python"
module = "demo"

[service]
command = ["demo"]
""",
    )
    _Installer.project = project
    monkeypatch.setattr(cli, "Installer", _Installer)

    installed: list[str] = []

    class _ServiceManager:
        def __init__(self, selected: Project) -> None:
            assert selected is project

        def install(self):
            installed.append("demo")
            return Path("/etc/systemd/system/gway-demo.service")

    monkeypatch.setattr(cli, "ServiceManager", _ServiceManager)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["install", "demo", "--service"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out
    assert installed == ["demo"]
    assert "service:" in output
    assert "status: installed" in output
    assert "gway-demo.service" in output


def test_install_service_explains_when_project_has_no_service(
    tmp_path, monkeypatch, capsys
) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "demo"

[adapter]
type = "python"
module = "demo"
""",
    )
    _Installer.project = project
    monkeypatch.setattr(cli, "Installer", _Installer)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["install", "demo", "--service"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out
    assert "status: not-provided" in output
    assert "demo does not provide a service" in output
