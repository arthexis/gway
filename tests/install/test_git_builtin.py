import subprocess

from gway.install import InstallState


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


def _repository(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-b", "main", cwd=source)
    _git("config", "user.name", "GWAY Tests", cwd=source)
    _git("config", "user.email", "gway@example.test", cwd=source)
    (source / "gway.toml").write_text(
        "[project]\nname = 'wire'\n",
        encoding="utf-8",
    )
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "initial", cwd=source)

    remote = tmp_path / "wire.git"
    _git("clone", "--bare", source, remote)
    _git("remote", "add", "origin", remote, cwd=source)
    return source, remote


def test_install_builtin_records_git_ref_and_revision(
    gateway,
    tmp_path,
    monkeypatch,
):
    source, remote = _repository(tmp_path)
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache))
    expected = _git("rev-parse", "HEAD", cwd=source)

    installed = gateway(f"install {remote.as_uri()} --ref main")

    assert installed.name == "wire"
    assert installed.source == remote.as_uri()
    assert installed.requested_ref == "main"
    assert installed.resolved_revision == expected
    assert installed.install_path == (data / "projects" / "wire").resolve()
    assert (installed.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (installed.install_path / ".git").exists()
    assert InstallState(data / "state.sqlite").get("wire") == installed


def test_install_builtin_upgrades_when_git_branch_moves(
    gateway,
    tmp_path,
    monkeypatch,
):
    source, remote = _repository(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))

    first = gateway(f"install {remote.as_uri()} --ref main")

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "module.py", cwd=source)
    _git("commit", "-m", "second", cwd=source)
    _git("push", "origin", "main", cwd=source)
    second_revision = _git("rev-parse", "HEAD", cwd=source)

    second = gateway(f"install {remote.as_uri()} --ref main")

    assert second.resolved_revision == second_revision
    assert second.resolved_revision != first.resolved_revision
    assert second.fingerprint != first.fingerprint
    assert (second.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_no_upgrade_keeps_installed_git_revision_when_branch_moves(
    gateway,
    tmp_path,
    monkeypatch,
):
    source, remote = _repository(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))

    first = gateway(f"install {remote.as_uri()} --ref main")

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "module.py", cwd=source)
    _git("commit", "-m", "second", cwd=source)
    _git("push", "origin", "main", cwd=source)

    second = gateway(
        f"install {remote.as_uri()} --ref main --no-upgrade"
    )

    assert second == first
    assert (second.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert InstallState(data / "state.sqlite").get("wire") == first


def test_reinstalling_pinned_git_commit_is_noop(
    gateway,
    tmp_path,
    monkeypatch,
):
    source, remote = _repository(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(tmp_path / "cache"))
    revision = _git("rev-parse", "HEAD", cwd=source)

    first = gateway(f"install {remote.as_uri()} --ref {revision}")
    second = gateway(f"install {remote.as_uri()} --ref {revision}")

    assert second == first
    assert second.resolved_revision == revision


def test_git_install_uses_cache_outside_managed_project(
    gateway,
    tmp_path,
    monkeypatch,
):
    _, remote = _repository(tmp_path)
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_CACHE_DIR", str(cache))

    installed = gateway(f"install {remote.as_uri()} --ref main")

    snapshots = list((cache / "git").glob("*/snapshots/*"))
    assert snapshots
    assert installed.install_path.is_relative_to(data)
    assert not installed.install_path.is_relative_to(cache)
