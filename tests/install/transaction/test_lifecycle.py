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
    assert (destination / "pyproject.toml").is_file()
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert InstallState(managed_paths.state).get("wire") == installed


def test_local_install_does_not_modify_source_tree(
    make_project,
    managed_paths,
):
    source = make_project()
    before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))

    transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    after = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
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
    installed_project,
    managed_paths,
):
    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed_project.installed
    assert installed_project.source.is_dir()
    assert not installed_project.destination.exists()
    assert installed_project.state.get("wire") is None


def test_uninstall_is_idempotent_when_project_is_absent(managed_paths):
    assert (
        transaction.uninstall_local(
            UninstallRequest("missing"),
            paths=managed_paths,
        )
        is None
    )
    assert not managed_paths.root.exists()


def test_uninstall_reconciles_stale_record_when_managed_copy_is_missing(
    installed_project,
    managed_paths,
):
    transaction._remove_path(installed_project.destination)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=managed_paths,
    )

    assert removed == installed_project.installed
    assert installed_project.state.get("wire") is None


def test_project_install_does_not_touch_service_installation(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")

    def unexpected_backend(name):
        raise AssertionError("project install must not resolve service backends")

    monkeypatch.setattr("gway.install.service.get", unexpected_backend)

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
    )

    assert installed.name == "wire"
    assert installed.install_path.is_dir()


def test_install_recovery_restores_previous_project_when_launcher_rollback_fails(
    installed_project,
    managed_paths,
    monkeypatch,
):
    source = installed_project.source
    installed = installed_project.installed
    destination = installed_project.destination
    real_state = installed_project.state
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    class FailingState:
        def get(self, name, scope=None):
            return real_state.get(name, scope=scope)

        def put(self, record):
            raise OSError("state write failed")

        def remove(self, name, scope=None):
            return real_state.remove(name, scope=scope)

    class FailingLauncher:
        def rollback(self):
            raise RuntimeError("launcher rollback failed")

        def commit(self):
            raise AssertionError("failed install must not commit launchers")

    monkeypatch.setattr(
        transaction,
        "activate_project",
        lambda name, project, paths: FailingLauncher(),
    )

    with pytest.raises(OSError, match="state write failed") as raised:
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
            state=FailingState(),
        )

    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert real_state.get("wire") == installed
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []
    assert any(
        "launcher rollback" in note and "launcher rollback failed" in note
        for note in getattr(raised.value, "__notes__", ())
    )
