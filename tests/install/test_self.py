import os
from pathlib import Path
import subprocess

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
