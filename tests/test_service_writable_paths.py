from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.project import Project
from gway.service import ServiceError, ServiceManager, systemd


def _project(tmp_path: Path, writable: str) -> Project:
    root = tmp_path / "managed"
    checkout = root / "app"
    checkout.mkdir(parents=True)
    (checkout / "gway.toml").write_text(
        f"""[project]
name = "demo"

[adapter]
type = "python"
module = "demo"

[install]
root = {str(root)!r}
checkout = "app"
environment = ".venv"

[service]
command = ["{{python}}", "-m", "demo"]
writable_paths = [{writable!r}]
""",
        encoding="utf-8",
    )
    return Project.from_path(checkout)


def _completed(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_install_prepares_writable_paths_for_service_account(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path, "{project}/.locks")
    target = project.path / ".locks"
    ownership: list[tuple[Path, int, int]] = []

    monkeypatch.setattr(systemd, "_systemctl", lambda *args, **kwargs: _completed(*args))
    assert systemd.pwd is not None
    monkeypatch.setattr(
        systemd.pwd,
        "getpwnam",
        lambda user: SimpleNamespace(pw_uid=1234, pw_gid=5678),
    )
    monkeypatch.setattr(
        systemd,
        "_chown_tree",
        lambda path, uid, gid: ownership.append((path, uid, gid)),
    )

    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")
    manager.install(user="service-account")

    assert target.is_dir()
    assert ownership == [(target.resolve(), 1234, 5678)]


def test_writable_path_cannot_escape_managed_install_root(tmp_path) -> None:
    project = _project(tmp_path, "/etc")
    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")

    with pytest.raises(ServiceError, match="must stay below managed root"):
        manager.render(user="service-account")


def test_writable_path_cannot_take_ownership_of_managed_root(tmp_path) -> None:
    root = tmp_path / "managed"
    project = _project(tmp_path, str(root))
    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")

    with pytest.raises(ServiceError, match="must stay below managed root"):
        manager.render(user="service-account")


def test_missing_service_account_fails_before_restart(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path, "{project}/.locks")
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return _completed(*args)

    monkeypatch.setattr(systemd, "_systemctl", fake_systemctl)
    assert systemd.pwd is not None

    def missing_user(user: str):
        raise KeyError(user)

    monkeypatch.setattr(systemd.pwd, "getpwnam", missing_user)
    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")

    with pytest.raises(ServiceError, match="service user does not exist"):
        manager.install(user="missing-account")

    assert not any(call and call[0] == "restart" for call in calls)
