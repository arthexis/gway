from __future__ import annotations

import os
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


def _multi_project(tmp_path: Path) -> Project:
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

[services.first]
command = ["{{python}}", "-m", "demo"]
user = "first-account"
writable_paths = ["{{project}}/shared"]

[services.second]
command = ["{{python}}", "-m", "demo"]
user = "second-account"
writable_paths = ["{{project}}/shared/nested"]
""",
        encoding="utf-8",
    )
    return Project.from_path(checkout)


def _completed(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _current_identity() -> SimpleNamespace:
    return SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())


def test_install_prepares_writable_paths_for_service_account(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path, "{project}/.locks")
    target = project.path / ".locks"

    monkeypatch.setattr(systemd, "_systemctl", lambda *args, **kwargs: _completed(*args))
    assert systemd.pwd is not None
    monkeypatch.setattr(systemd.pwd, "getpwnam", lambda user: _current_identity())

    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")
    manager.install(user="service-account")

    assert target.is_dir()
    stat_result = target.stat()
    assert stat_result.st_uid == os.getuid()
    assert stat_result.st_gid == os.getgid()


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


def test_missing_service_account_fails_before_unit_replacement(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path, "{project}/.locks")
    calls: list[tuple[str, ...]] = []
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    unit_path = unit_directory / "gway-demo.service"
    unit_path.write_text("existing-unit\n", encoding="utf-8")

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return _completed(*args)

    monkeypatch.setattr(systemd, "_systemctl", fake_systemctl)
    assert systemd.pwd is not None

    def missing_user(user: str):
        raise KeyError(user)

    monkeypatch.setattr(systemd.pwd, "getpwnam", missing_user)
    manager = ServiceManager(project, unit_directory=unit_directory)

    with pytest.raises(ServiceError, match="service user does not exist"):
        manager.install(user="missing-account")

    assert unit_path.read_text(encoding="utf-8") == "existing-unit\n"
    assert calls == []


def test_symlink_component_cannot_escape_managed_root(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path, "{project}/escape/nested")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    (project.path / "escape").symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(systemd, "_systemctl", lambda *args, **kwargs: _completed(*args))
    assert systemd.pwd is not None
    monkeypatch.setattr(systemd.pwd, "getpwnam", lambda user: _current_identity())

    manager = ServiceManager(project, unit_directory=tmp_path / "systemd")
    with pytest.raises(ServiceError, match="not a safe directory"):
        manager.install(user="service-account")

    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert not (outside / "nested").exists()


def test_created_writable_ancestors_are_traversable_under_restrictive_umask(
    tmp_path, monkeypatch
) -> None:
    project = _project(tmp_path, "{project}/runtime/locks")
    monkeypatch.setattr(systemd, "_systemctl", lambda *args, **kwargs: _completed(*args))
    assert systemd.pwd is not None
    monkeypatch.setattr(systemd.pwd, "getpwnam", lambda user: _current_identity())

    previous = os.umask(0o077)
    try:
        ServiceManager(project, unit_directory=tmp_path / "systemd").install(
            user="service-account"
        )
    finally:
        os.umask(previous)

    runtime = project.path / "runtime"
    locks = runtime / "locks"
    assert runtime.is_dir() and locks.is_dir()
    assert runtime.stat().st_mode & 0o777 == 0o755
    assert locks.stat().st_mode & 0o777 == 0o755


def test_conflicting_overlapping_writable_owners_fail_before_unit_changes(
    tmp_path, monkeypatch
) -> None:
    project = _multi_project(tmp_path)
    calls: list[tuple[str, ...]] = []

    def identity(user: str):
        if user == "first-account":
            return SimpleNamespace(pw_uid=1001, pw_gid=1001)
        if user == "second-account":
            return SimpleNamespace(pw_uid=1002, pw_gid=1002)
        raise KeyError(user)

    assert systemd.pwd is not None
    monkeypatch.setattr(systemd.pwd, "getpwnam", identity)
    monkeypatch.setattr(
        systemd,
        "_systemctl",
        lambda *args, **kwargs: calls.append(args) or _completed(*args),
    )
    unit_directory = tmp_path / "systemd"
    manager = ServiceManager(project, all_services=True, unit_directory=unit_directory)

    with pytest.raises(ServiceError, match="conflicting service owners"):
        manager.install()

    assert not unit_directory.exists()
    assert calls == []
