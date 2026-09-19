import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest
import gway.install.transaction as transaction


def test_local_install_stages_copy_and_records_managed_project(
    make_project,
    managed_paths,
):
    source = make_project("wire")

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    destination = managed_paths.projects / "wire"
    assert installed.name == "wire"
    assert installed.source == str(source.resolve())
    assert installed.install_path == destination
    assert installed.fingerprint.startswith("sha256:")
    assert installed.installed_at is not None
    assert (destination / "gway.toml").is_file()
    assert (destination / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert InstallState(managed_paths.state).get("wire") == installed


def test_local_install_does_not_modify_source_tree(
    make_project,
    managed_paths,
):
    source = make_project()
    before = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )

    transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    after = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )
    assert after == before
    assert source != managed_paths.projects / "demo"


def test_repeated_unchanged_local_install_is_noop(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    request = InstallRequest(str(source))

    first = transaction.install_local(request, paths=managed_paths)
    second = transaction.install_local(request, paths=managed_paths)

    assert second == first
    assert len(InstallState(managed_paths.state).all()) == 1


def test_local_install_rejects_ref(make_project, managed_paths):
    source = make_project()

    with pytest.raises(ValueError, match="not supported for local"):
        transaction.install_local(
            InstallRequest(str(source), ref="main"),
            paths=managed_paths,
        )


def test_uninstall_removes_managed_copy_and_state_but_not_source(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed
    assert source.is_dir()
    assert not installed.install_path.exists()
    assert InstallState(managed_paths.state).get("wire") is None


def test_uninstall_is_idempotent_when_project_is_absent(managed_paths):
    assert transaction.uninstall_local(
        UninstallRequest("missing"),
        paths=managed_paths,
    ) is None
    assert not managed_paths.root.exists()


def test_uninstall_reconciles_stale_record_when_managed_copy_is_missing(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )
    transaction._remove_path(installed.install_path)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed
    assert InstallState(managed_paths.state).get("wire") is None
