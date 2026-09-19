"""Shared fixtures for managed-installation tests."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

import pytest

from gway.install import install_paths


@dataclass(frozen=True)
class InstallEnvironment:
    data: Path
    cache: Path
    bin: Path


@pytest.fixture
def make_project(tmp_path):
    """Create small installable GWAY projects without repeating manifest setup."""
    counter = {"value": 0}

    def make(name="demo", *, launcher=False, root=None):
        counter["value"] += 1
        base = tmp_path / "sources" if root is None else Path(root)
        project = base / f"{name}-{counter['value']}"
        project.mkdir(parents=True)

        manifest = [f"[project]\nname = {name!r}\n"]
        if launcher:
            manifest.append(
                f"\n[install.scripts]\n{name} = {f'{name}:main'!r}\n"
            )
        (project / "gway.toml").write_text(
            "".join(manifest),
            encoding="utf-8",
        )

        if launcher:
            package = project / name
            package.mkdir()
            (package / "__init__.py").write_text(
                "def main():\n"
                "    print('managed launcher works')\n"
                "    return 0\n",
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
        (source / "gway.toml").write_text(
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
