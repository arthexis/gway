from gway.install import InstallState


def test_install_builtin_records_git_ref_and_revision(
    gateway,
    git,
    make_git_repository,
    install_environment,
):
    source, remote = make_git_repository()
    expected = git("rev-parse", "HEAD", cwd=source)

    installed = gateway(f"install {remote.as_uri()} --ref main")

    assert installed.name == "wire"
    assert installed.source == remote.as_uri()
    assert installed.requested_ref == "main"
    assert installed.resolved_revision == expected
    assert installed.install_path == (
        install_environment.data / "projects" / "wire"
    ).resolve()
    assert (installed.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (installed.install_path / ".git").exists()
    assert InstallState(
        install_environment.data / "state.sqlite"
    ).get("wire") == installed


def test_install_builtin_upgrades_when_git_branch_moves(
    gateway,
    git,
    make_git_repository,
    install_environment,
):
    source, remote = make_git_repository()
    first = gateway(f"install {remote.as_uri()} --ref main")

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    git("add", "module.py", cwd=source)
    git("commit", "-m", "second", cwd=source)
    git("push", "origin", "main", cwd=source)
    second_revision = git("rev-parse", "HEAD", cwd=source)

    second = gateway(f"install {remote.as_uri()} --ref main")

    assert second.resolved_revision == second_revision
    assert second.resolved_revision != first.resolved_revision
    assert second.fingerprint != first.fingerprint
    assert (second.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_no_upgrade_keeps_installed_git_revision_when_branch_moves(
    gateway,
    git,
    make_git_repository,
    install_environment,
):
    source, remote = make_git_repository()
    first = gateway(f"install {remote.as_uri()} --ref main")

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    git("add", "module.py", cwd=source)
    git("commit", "-m", "second", cwd=source)
    git("push", "origin", "main", cwd=source)

    second = gateway(
        f"install {remote.as_uri()} --ref main --no-upgrade"
    )

    assert second == first
    assert (second.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert InstallState(
        install_environment.data / "state.sqlite"
    ).get("wire") == first


def test_reinstalling_pinned_git_commit_is_noop(
    gateway,
    git,
    make_git_repository,
    install_environment,
):
    source, remote = make_git_repository()
    revision = git("rev-parse", "HEAD", cwd=source)

    first = gateway(f"install {remote.as_uri()} --ref {revision}")
    second = gateway(f"install {remote.as_uri()} --ref {revision}")

    assert second == first
    assert second.resolved_revision == revision


def test_git_install_uses_cache_outside_managed_project(
    gateway,
    make_git_repository,
    install_environment,
):
    _, remote = make_git_repository()

    installed = gateway(f"install {remote.as_uri()} --ref main")

    snapshots = list(
        (install_environment.cache / "git").glob("*/snapshots/*")
    )
    assert snapshots
    assert installed.install_path.is_relative_to(install_environment.data)
    assert not installed.install_path.is_relative_to(install_environment.cache)


def test_github_shorthand_routes_through_git_materialization(
    gateway,
    tmp_path,
    monkeypatch,
    install_environment,
):
    import gway.install.git as git_source

    materialized = tmp_path / "materialized"
    materialized.mkdir()
    (materialized / "pyproject.toml").write_text(
        "[project]\nname = 'gway'\n",
        encoding="utf-8",
    )
    (materialized / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    seen = {}

    def fake_materialize(source, *, ref=None, cache=None):
        seen["source"] = source
        seen["ref"] = ref
        return git_source.GitArtifact(
            source="https://github.com/arthexis/gway.git",
            requested_ref=ref,
            resolved_revision="a" * 40,
            path=materialized,
        )

    monkeypatch.setattr(git_source, "materialize", fake_materialize)

    installed = gateway("install arthexis/gway --ref gateway-rebuild")

    assert seen == {
        "source": "arthexis/gway",
        "ref": "gateway-rebuild",
    }
    assert installed.source == "https://github.com/arthexis/gway.git"
    assert installed.requested_ref == "gateway-rebuild"
    assert installed.resolved_revision == "a" * 40
