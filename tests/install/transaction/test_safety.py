import pytest

from gway.install import InstallRequest, Installation, InstallState, UninstallRequest
import gway.install.transaction as transaction


def test_installation_root_cannot_live_inside_source_tree(
    make_project,
    tmp_path,
):
    source = make_project()
    from gway.install import install_paths

    with pytest.raises(ValueError, match="cannot be stored inside"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=install_paths(root=source / ".gway-data"),
        )


def test_unmanaged_destination_is_never_overwritten(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    destination = managed_paths.projects / "wire"
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(RuntimeError, match="without installation state"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
        )

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_install_failure_removes_staging_directory(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")

    def fail_copy(source, stage):
        (stage / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("copy failed")

    monkeypatch.setattr(transaction, "_copy_project", fail_copy)

    with pytest.raises(RuntimeError, match="copy failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
        )

    assert not (managed_paths.projects / "wire").exists()
    assert list(managed_paths.projects.glob(".wire.stage-*")) == []
    assert not managed_paths.state.exists()


def test_install_rolls_back_activation_when_state_write_fails(
    make_project,
    managed_paths,
):
    source = make_project("wire")

    class FailingState:
        def get(self, name, *, scope="user"):
            return None

        def put(self, installation):
            raise RuntimeError("state write failed")

    with pytest.raises(RuntimeError, match="state write failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
            state=FailingState(),
        )

    assert not (managed_paths.projects / "wire").exists()
    assert list(managed_paths.projects.glob(".wire.stage-*")) == []


def test_uninstall_restores_live_directory_when_state_remove_fails(
    make_project,
    managed_paths,
    monkeypatch,
):
    source = make_project("wire")
    state = InstallState(managed_paths.state)
    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
        state=state,
    )

    def fail_remove(name, *, scope="user"):
        raise RuntimeError("state remove failed")

    monkeypatch.setattr(state, "remove", fail_remove)

    with pytest.raises(RuntimeError, match="state remove failed"):
        transaction.uninstall_local(
            UninstallRequest("wire"),
            paths=managed_paths,
            state=state,
        )

    assert installed.install_path.is_dir()
    assert (installed.install_path / "module.py").is_file()
    assert state.get("wire") == installed


def test_uninstall_refuses_registry_path_outside_managed_projects(
    managed_paths,
    tmp_path,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("safe", encoding="utf-8")
    state = InstallState(managed_paths.state)
    state.put(
        Installation(
            name="wire",
            source=str(tmp_path / "source"),
            install_path=outside,
        )
    )

    with pytest.raises(RuntimeError, match="outside the managed"):
        transaction.uninstall_local(
            UninstallRequest("wire"),
            paths=managed_paths,
            state=state,
        )

    assert marker.read_text(encoding="utf-8") == "safe"


def test_changed_source_replacement_rolls_back_on_state_failure(
    make_project,
    managed_paths,
):
    source = make_project("wire")
    state = InstallState(managed_paths.state)
    first = transaction.install_local(
        InstallRequest(str(source)),
        paths=managed_paths,
        state=state,
    )
    original_fingerprint = first.fingerprint
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    class FailingReplacementState:
        def get(self, name, *, scope="user"):
            return state.get(name, scope=scope)

        def put(self, installation):
            raise RuntimeError("replacement state write failed")

    with pytest.raises(RuntimeError, match="replacement state write failed"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=managed_paths,
            state=FailingReplacementState(),
        )

    assert (managed_paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert state.get("wire").fingerprint == original_fingerprint
    assert list(managed_paths.projects.glob(".wire.replace-*")) == []
    assert list(managed_paths.projects.glob(".wire.stage-*")) == []
