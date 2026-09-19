import os
from pathlib import Path
import subprocess

import pytest

from gway.install import InstallState
import gway.install.source as install_source


def _git(*args, cwd=None):
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


def _self_remote(tmp_path):
    root = Path(__file__).resolve().parents[2]
    revision = _git("rev-parse", "HEAD", cwd=root)
    remote = tmp_path / "gway.git"
    _git("clone", "--bare", root, remote)
    _git(
        f"--git-dir={remote}",
        "update-ref",
        "refs/heads/selftest",
        revision,
    )
    return root, remote, revision


def _environment(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache))
    monkeypatch.setenv("GWAY_BIN_DIR", str(bin_dir))
    return data, cache, bin_dir


def _route_gway_to(remote, monkeypatch):
    original = install_source.named_source

    def resolve(value):
        if str(value).strip() == "gway":
            return remote.as_uri()
        return original(value)

    monkeypatch.setattr(install_source, "named_source", resolve)


def test_gway_can_install_itself_and_run_outside_source_checkout(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, remote, revision = _self_remote(tmp_path)
    data, _, bin_dir = _environment(tmp_path, monkeypatch)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")

    assert installed.name == "gway"
    assert installed.source == remote.as_uri()
    assert installed.requested_ref == "selftest"
    assert installed.resolved_revision == revision
    assert installed.install_path == (data / "projects" / "gway").resolve()
    assert installed.install_path != root.resolve()

    launcher = bin_dir / "gway"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)

    outside = tmp_path / "outside"
    outside.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(launcher), "--help"],
        cwd=outside,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "GWAY command-dispatch and composition core" in result.stdout
    assert str(installed.install_path) in launcher.read_text(encoding="utf-8")
    assert InstallState(data / "state.sqlite").get("gway") == installed


def test_repeated_self_install_is_noop(
    gateway,
    tmp_path,
    monkeypatch,
):
    _, remote, _ = _self_remote(tmp_path)
    _environment(tmp_path, monkeypatch)
    _route_gway_to(remote, monkeypatch)

    first = gateway("install gway --ref selftest")
    second = gateway("install gway --ref selftest")

    assert second == first


def test_self_install_tracks_branch_movement_and_honors_no_upgrade(
    gateway,
    tmp_path,
    monkeypatch,
):
    _, remote, first_revision = _self_remote(tmp_path)
    data, _, _ = _environment(tmp_path, monkeypatch)
    _route_gway_to(remote, monkeypatch)

    first = gateway("install gway --ref selftest")
    assert first.resolved_revision == first_revision

    work = tmp_path / "work"
    _git("clone", remote, work)
    _git("checkout", "selftest", cwd=work)
    _git("config", "user.name", "GWAY Self Tests", cwd=work)
    _git("config", "user.email", "gway@example.test", cwd=work)
    (work / "SELFTEST_REVISION").write_text("second\n", encoding="utf-8")
    _git("add", "SELFTEST_REVISION", cwd=work)
    _git("commit", "-m", "advance selftest branch", cwd=work)
    _git("push", "origin", "selftest", cwd=work)
    second_revision = _git("rev-parse", "HEAD", cwd=work)

    held = gateway("install gway --ref selftest --no-upgrade")
    assert held == first
    assert not (held.install_path / "SELFTEST_REVISION").exists()

    upgraded = gateway("install gway --ref selftest")
    assert upgraded.resolved_revision == second_revision
    assert upgraded.resolved_revision != first.resolved_revision
    assert (upgraded.install_path / "SELFTEST_REVISION").read_text(
        encoding="utf-8"
    ) == "second\n"
    assert InstallState(data / "state.sqlite").get("gway") == upgraded


@pytest.mark.parametrize("policy", ["force", "stash"])
def test_self_install_handles_dirty_managed_copy(
    gateway,
    tmp_path,
    monkeypatch,
    policy,
):
    _, remote, _ = _self_remote(tmp_path)
    data, _, _ = _environment(tmp_path, monkeypatch)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")
    custom = installed.install_path / "LOCAL_CUSTOMIZATION"
    custom.write_text("keep me\n", encoding="utf-8")

    repaired = gateway(f"install gway --ref selftest --{policy}")

    assert repaired.resolved_revision == installed.resolved_revision
    assert not custom.exists()

    if policy == "stash":
        stashes = list((data / "stashes" / "gway").iterdir())
        assert len(stashes) == 1
        assert (stashes[0] / "tree" / "LOCAL_CUSTOMIZATION").read_text(
            encoding="utf-8"
        ) == "keep me\n"
    else:
        assert not (data / "stashes").exists()


def test_self_uninstall_removes_managed_copy_launcher_and_state(
    gateway,
    tmp_path,
    monkeypatch,
):
    _, remote, _ = _self_remote(tmp_path)
    data, _, bin_dir = _environment(tmp_path, monkeypatch)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")
    launcher = bin_dir / "gway"
    assert launcher.is_file()

    removed = gateway("uninstall gway")

    assert removed == installed
    assert not installed.install_path.exists()
    assert not launcher.exists()
    assert not (data / "launchers" / "gway.json").exists()
    assert InstallState(data / "state.sqlite").get("gway") is None
