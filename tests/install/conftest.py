"""Shared fixtures for managed-installation tests."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from gway.install import InstallRequest, InstallState, install_paths
import gway.install.transaction as transaction
import gway.install.service.systemd as systemd


@dataclass(frozen=True)
class InstallEnvironment:
    data: Path
    cache: Path
    bin: Path


@pytest.fixture
def make_project(tmp_path):
    """Create small installable GWAY projects without repeating project metadata setup."""
    counter = {"value": 0}

    def make(name="demo", *, launcher=False, root=None):
        counter["value"] += 1
        base = tmp_path / "sources" if root is None else Path(root)
        project = base / f"{name}-{counter['value']}"
        project.mkdir(parents=True)

        metadata = [f"[project]\nname = {name!r}\n"]
        if launcher:
            metadata.append(f"\n[project.scripts]\n{name} = {f'{name}:main'!r}\n")
        (project / "pyproject.toml").write_text(
            "".join(metadata),
            encoding="utf-8",
        )

        if launcher:
            package = project / name
            package.mkdir()
            (package / "__init__.py").write_text(
                "def main():\n    print('managed launcher works')\n    return 0\n",
                encoding="utf-8",
            )
        else:
            (project / "module.py").write_text(
                "VALUE = 1\n",
                encoding="utf-8",
            )
        return project

    return make


@pytest.fixture
def git():
    """Run Git commands with failures surfaced as test setup errors."""

    def run(*args, cwd=None):
        result = subprocess.run(
            ["git", *map(str, args)],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()

    return run


@pytest.fixture
def make_git_repository(tmp_path, git):
    """Create a small working repository plus a bare origin."""
    counter = {"value": 0}

    def make(name="wire"):
        counter["value"] += 1
        source = tmp_path / f"git-source-{counter['value']}"
        source.mkdir()
        git("init", "-b", "main", cwd=source)
        git("config", "user.name", "GWAY Tests", cwd=source)
        git("config", "user.email", "gway@example.test", cwd=source)
        (source / "pyproject.toml").write_text(
            f"[project]\nname = {name!r}\n",
            encoding="utf-8",
        )
        (source / "module.py").write_text(
            "VALUE = 1\n",
            encoding="utf-8",
        )
        git("add", ".", cwd=source)
        git("commit", "-m", "initial", cwd=source)

        remote = tmp_path / f"{name}-{counter['value']}.git"
        git("clone", "--bare", source, remote)
        git("remote", "add", "origin", remote, cwd=source)
        return source, remote

    return make


@pytest.fixture
def install_environment(tmp_path, monkeypatch):
    """Isolate durable data, cache, and launcher activation for builtin tests."""
    environment = InstallEnvironment(
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        bin=tmp_path / "bin",
    )
    monkeypatch.setenv("GWAY_DATA_DIR", str(environment.data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(environment.cache))
    monkeypatch.setenv("GWAY_BIN_DIR", str(environment.bin))
    return environment


@pytest.fixture
def managed_paths(tmp_path):
    """Return explicit managed paths for direct transaction tests."""
    return install_paths(
        root=tmp_path / "data",
        environ={"GWAY_BIN_DIR": str(tmp_path / "bin")},
        platform=sys.platform,
        home=tmp_path / "home",
    )


@pytest.fixture
def fake_systemd(tmp_path, monkeypatch):
    """Capture systemctl calls while materializing units under tmp_path."""
    units = tmp_path / "units"
    calls = []
    active = set()
    monkeypatch.setattr(systemd, "unit_root", lambda **kwargs: units)

    def call(*args, system=False, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        calls.append((args, system, check))
        action = args[0] if args else None
        unit = args[-1] if len(args) > 1 else None
        if action in {"start", "restart"} and unit is not None:
            active.add((system, unit))
        elif action == "stop" and unit is not None:
            active.discard((system, unit))
        elif action == "disable" and "--now" in args and unit is not None:
            active.discard((system, unit))
        if action == "is-active" and unit is not None:
            return SimpleNamespace(returncode=0 if (system, unit) in active else 3)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd, "_systemctl", call)
    return units, calls


@pytest.fixture
def record_systemd_operations(monkeypatch):
    """Record structured systemd operations routed through the central runner."""
    observed = []

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        observed.append((operation.action, operation.unit, check, timeout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)
    return observed



@pytest.fixture
def installed_project(make_project, managed_paths):
    """Return one ordinary managed wire installation and its durable state."""
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    return SimpleNamespace(
        source=source,
        installed=installed,
        destination=installed.install_path,
        state=InstallState(managed_paths.state),
    )
