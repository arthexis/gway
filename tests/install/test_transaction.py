import pytest

from gway.install import InstallRequest, InstallState, UninstallRequest, install_paths
import gway.install.transaction as transaction


def _project(tmp_path, name="demo"):
    root = tmp_path / "source" / name
    root.mkdir(parents=True)
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def test_local_install_stages_copy_and_records_managed_project(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")

    installed = transaction.install_local(
        InstallRequest(str(source)),
        paths=paths,
    )

    destination = paths.projects / "wire"
    assert installed.name == "wire"
    assert installed.source == str(source.resolve())
    assert installed.install_path == destination
    assert installed.fingerprint.startswith("sha256:")
    assert installed.installed_at is not None
    assert (destination / "gway.toml").is_file()
    assert (destination / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert InstallState(paths.state).get("wire") == installed


def test_local_install_does_not_modify_source_tree(tmp_path):
    source = _project(tmp_path)
    before = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )
    paths = install_paths(root=tmp_path / "data")

    transaction.install_local(InstallRequest(str(source)), paths=paths)

    after = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
    )
    assert after == before
    assert source != paths.projects / "demo"


def test_repeated_unchanged_local_install_is_noop(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    request = InstallRequest(str(source))

    first = transaction.install_local(request, paths=paths)
    second = transaction.install_local(request, paths=paths)

    assert second == first
    assert len(InstallState(paths.state).all()) == 1


def test_changed_local_source_requires_reconciliation_when_upgrade_enabled(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    transaction.install_local(InstallRequest(str(source)), paths=paths)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="replacement reconciliation"):
        transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert (paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_no_upgrade_leaves_existing_installation_unchanged(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    first = transaction.install_local(InstallRequest(str(source)), paths=paths)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = transaction.install_local(
        InstallRequest(str(source), upgrade=False),
        paths=paths,
    )

    assert second == first
    assert (paths.projects / "wire" / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_local_install_ref_is_rejected_until_git_source_support(tmp_path):
    source = _project(tmp_path)

    with pytest.raises(ValueError, match="not supported for local"):
        transaction.install_local(
            InstallRequest(str(source), ref="main"),
            paths=install_paths(root=tmp_path / "data"),
        )


def test_installation_root_cannot_live_inside_source_tree(tmp_path):
    source = _project(tmp_path)

    with pytest.raises(ValueError, match="cannot be stored inside"):
        transaction.install_local(
            InstallRequest(str(source)),
            paths=install_paths(root=source / ".gway-data"),
        )


def test_unmanaged_destination_is_never_overwritten(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    destination = paths.projects / "wire"
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(RuntimeError, match="without installation state"):
        transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_install_failure_removes_staging_directory(tmp_path, monkeypatch):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")

    def fail_copy(source, stage):
        (stage / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("copy failed")

    monkeypatch.setattr(transaction, "_copy_project", fail_copy)

    with pytest.raises(RuntimeError, match="copy failed"):
        transaction.install_local(InstallRequest(str(source)), paths=paths)

    assert not (paths.projects / "wire").exists()
    assert list(paths.projects.glob(".wire.stage-*")) == []
    assert not paths.state.exists()


def test_uninstall_removes_managed_copy_and_state_but_not_source(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(InstallRequest(str(source)), paths=paths)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=paths,
    )

    assert removed == installed
    assert source.is_dir()
    assert not installed.install_path.exists()
    assert InstallState(paths.state).get("wire") is None


def test_uninstall_is_idempotent_when_project_is_absent(tmp_path):
    paths = install_paths(root=tmp_path / "data")

    assert transaction.uninstall_local(
        UninstallRequest("missing"),
        paths=paths,
    ) is None
    assert not paths.root.exists()


def test_uninstall_reconciles_stale_record_when_managed_copy_is_missing(tmp_path):
    source = _project(tmp_path, "wire")
    paths = install_paths(root=tmp_path / "data")
    installed = transaction.install_local(InstallRequest(str(source)), paths=paths)
    transaction._remove_path(installed.install_path)

    removed = transaction.uninstall_local(
        UninstallRequest("wire"),
        paths=paths,
    )

    assert removed == installed
    assert InstallState(paths.state).get("wire") is None
