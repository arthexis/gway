import os
from pathlib import Path
import subprocess

import pytest

from gway.install import InstallState
import gway.install.source as install_source


def _self_remote(tmp_path, git):
    root = Path(__file__).resolve().parents[2]
    revision = git("rev-parse", "HEAD", cwd=root)
    remote = tmp_path / "gway.git"
    git("clone", "--bare", root, remote)
    git(
        f"--git-dir={remote}",
        "update-ref",
        "refs/heads/selftest",
        revision,
    )
    return root, remote, revision


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
    git,
    install_environment,
):
    root, remote, revision = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")

    assert installed.name == "gway"
    assert installed.source == remote.as_uri()
    assert installed.requested_ref == "selftest"
    assert installed.resolved_revision == revision
    assert installed.install_path == (
        install_environment.data / "projects" / "gway"
    ).resolve()
    assert installed.install_path != root.resolve()

    launcher = install_environment.bin / "gway"
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
    assert InstallState(
        install_environment.data / "state.sqlite"
    ).get("gway") == installed


    gateway,
    tmp_path,
    monkeypatch,
    git,
    install_environment,
):
    _, remote, _ = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)

    first = gateway("install gway --ref selftest")
    second = gateway("install gway --ref selftest")

    assert second == first


    gateway,
    tmp_path,
    monkeypatch,
    git,
    install_environment,
):
    _, remote, first_revision = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)

    first = gateway("install gway --ref selftest")
    assert first.resolved_revision == first_revision

    work = tmp_path / "work"
    git("clone", remote, work)
    git("checkout", "selftest", cwd=work)
    git("config", "user.name", "GWAY Self Tests", cwd=work)
    git("config", "user.email", "gway@example.test", cwd=work)
    (work / "SELFTEST_REVISION").write_text("second\n", encoding="utf-8")
    git("add", "SELFTEST_REVISION", cwd=work)
    git("commit", "-m", "advance selftest branch", cwd=work)
    git("push", "origin", "selftest", cwd=work)
    second_revision = git("rev-parse", "HEAD", cwd=work)

    held = gateway("install gway --ref selftest --no-upgrade")
    assert held == first
    assert not (held.install_path / "SELFTEST_REVISION").exists()

    upgraded = gateway("install gway --ref selftest")
    assert upgraded.resolved_revision == second_revision
    assert upgraded.resolved_revision != first.resolved_revision
    assert (upgraded.install_path / "SELFTEST_REVISION").read_text(
        encoding="utf-8"
    ) == "second\n"
    assert InstallState(
        install_environment.data / "state.sqlite"
    ).get("gway") == upgraded


@pytest.mark.parametrize("policy", ["force", "stash"])
    gateway,
    tmp_path,
    monkeypatch,
    git,
    install_environment,
    policy,
):
    _, remote, _ = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")
    custom = installed.install_path / "LOCAL_CUSTOMIZATION"
    custom.write_text("keep me\n", encoding="utf-8")

    repaired = gateway(f"install gway --ref selftest --{policy}")

    assert repaired.resolved_revision == installed.resolved_revision
    assert not custom.exists()

    if policy == "stash":
        stashes = list(
            (install_environment.data / "stashes" / "gway").iterdir()
        )
        assert len(stashes) == 1
        assert (stashes[0] / "tree" / "LOCAL_CUSTOMIZATION").read_text(
            encoding="utf-8"
        ) == "keep me\n"
    else:
        assert not (install_environment.data / "stashes").exists()


    gateway,
    tmp_path,
    monkeypatch,
    git,
    install_environment,
):
    _, remote, _ = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)

    installed = gateway("install gway --ref selftest")
    launcher = install_environment.bin / "gway"
    assert launcher.is_file()

    removed = gateway("uninstall gway")

    assert removed == installed
    assert not installed.install_path.exists()
    assert not launcher.exists()
    assert not (
        install_environment.data / "launchers" / "gway.json"
    ).exists()
    assert InstallState(
        install_environment.data / "state.sqlite"
    ).get("gway") is None
