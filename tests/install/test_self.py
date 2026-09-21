import json
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


def test_gway_self_install_crosses_git_install_activation_and_runtime_boundaries(
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
    assert installed.fingerprint
    assert installed.scope == "user"
    assert (
        installed.install_path
        == (install_environment.data / "projects" / "gway").resolve()
    )
    assert installed.install_path != root.resolve()
    assert installed.install_path.is_dir()
    assert not (installed.install_path / ".git").exists()

    snapshots = list((install_environment.cache / "git").glob("*/snapshots/*"))
    assert snapshots
    assert all(path.is_relative_to(install_environment.cache) for path in snapshots)
    assert not installed.install_path.is_relative_to(install_environment.cache)

    state = InstallState(install_environment.data / "state.sqlite")
    assert state.get("gway") == installed

    launcher = install_environment.bin / "gway"
    launcher_record = install_environment.data / "launchers" / "gway.json"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert launcher_record.is_file()
    assert str(installed.install_path) in launcher.read_text(encoding="utf-8")

    metadata = json.loads(launcher_record.read_text(encoding="utf-8"))
    assert metadata["project"] == "gway"
    assert metadata["scripts"]["gway"] == "gway:cli_main"

    outside = tmp_path / "outside"
    outside.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    help_result = subprocess.run(
        [str(launcher), "--help"],
        cwd=outside,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "GWAY command-dispatch and composition core" in help_result.stdout

    command_result = subprocess.run(
        [
            str(launcher),
            "--expression",
            "[site]",
            "--site",
            "MTY",
        ],
        cwd=outside,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert command_result.returncode == 0
    assert command_result.stdout.strip() == "MTY"



def test_gway_reload_crosses_real_managed_process_boundary(
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

    recipe = tmp_path / "reload-acceptance.rx"
    companion = tmp_path / "reload-acceptance.py"
    events = tmp_path / "events.txt"

    companion.write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"_events = Path({str(events)!r})\n"
        "def before():\n"
        "    with _events.open('a', encoding='utf-8') as stream:\n"
        "        stream.write(f'before:{os.getpid()}\\n')\n"
        "    return 'before'\n"
        "def after():\n"
        "    with _events.open('a', encoding='utf-8') as stream:\n"
        "        stream.write(f'after:{os.getpid()}\\n')\n"
        "    return 'after'\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "reload-acceptance before\n"
        "reload\n"
        "reload-acceptance after\n",
        encoding="utf-8",
    )

    outside = tmp_path / "outside-reload"
    outside.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [str(launcher), "--recipe", str(recipe)],
        cwd=outside,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    lines = events.read_text(encoding="utf-8").splitlines()
    assert [line.split(":", 1)[0] for line in lines] == ["before", "after"]
    before_pid = int(lines[0].split(":", 1)[1])
    after_pid = int(lines[1].split(":", 1)[1])
    assert before_pid != after_pid
    assert installed.install_path.is_dir()


def test_gway_reload_real_successor_failure_rolls_back_adopted_journal(
    gateway,
    tmp_path,
    monkeypatch,
    git,
    install_environment,
):
    _, remote, _ = _self_remote(tmp_path, git)
    _route_gway_to(remote, monkeypatch)
    gateway("install gway --ref selftest")
    launcher = install_environment.bin / "gway"

    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    recipe = tmp_path / "reload-rollback.rx"
    companion = tmp_path / "reload-rollback.py"
    source.write_text("replacement", encoding="utf-8")

    companion.write_text(
        "def fail():\n"
        "    raise RuntimeError('successor acceptance failure')\n",
        encoding="utf-8",
    )
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "reload\n"
        "reload-rollback fail\n",
        encoding="utf-8",
    )

    outside = tmp_path / "outside-rollback"
    outside.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [str(launcher), "--recipe", str(recipe)],
        cwd=outside,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "successor acceptance failure" in result.stderr
    assert not destination.exists()
